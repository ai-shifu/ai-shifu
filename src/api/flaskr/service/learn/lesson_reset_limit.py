"""Limit successful learner resets without changing the SQL schema.

SQL commits before Redis accounting. A process interruption or unavailable Redis
after that commit can miss a use; this is a cost-control guard, not a billing ledger.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import threading
import uuid
from typing import TYPE_CHECKING, Self

from flaskr.dao import get_redis_client
from flaskr.dao.uow import app_context_scope
from flaskr.service.common.models import raise_error
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from redis import ConnectionPool, Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

if TYPE_CHECKING:
    from types import TracebackType

    from flask import Flask

_LOCK_SECONDS = 60
_WRITE_STATE = """
if redis.call('GET', KEYS[2]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2])
return 1
"""


def is_course_reset_exempt(app: Flask, course_id: str, user_id: str) -> bool:
    """Exempt the current owner and active collaborators, including read-only."""
    with app_context_scope(app):
        # Match current course ownership: newest draft, then published fallback.
        for model in (DraftShifu, PublishedShifu):
            course = (
                model.query.filter_by(shifu_bid=course_id, deleted=0)
                .order_by(model.id.desc())
                .first()
            )
            if course and course.created_user_bid:
                if course.created_user_bid == user_id:
                    return True
                break
        return (
            AiCourseAuth.query.filter_by(
                course_id=course_id, user_id=user_id, status=1
            ).first()
            is not None
        )


def require_reset_lesson(course_id: str, lesson_id: str) -> None:
    """Reject a lesson from another course before touching progress or counters."""
    for model in (PublishedOutlineItem, DraftOutlineItem):
        if model.query.filter_by(
            shifu_bid=course_id, outline_item_bid=lesson_id, deleted=0
        ).first():
            return
    raise_error("server.shifu.lessonNotFoundInCourse")


def normalize_reset_request_id(value: str | None) -> str:
    """Bound retry receipts without restricting existing callers' trace-ID format."""
    return hashlib.sha256((value or uuid.uuid4().hex).encode()).hexdigest()


class LessonResetGuard:
    """Hold one learner/lesson guard until SQL commits and accounting finishes."""

    def __init__(
        self, app: Flask, course_id: str, lesson_id: str, user_id: str, request_id: str
    ) -> None:
        """Bind a counter and operation lock to existing deployment Redis scope."""
        self.app = app
        prefix = str(app.config.get("REDIS_KEY_PREFIX", "ai-shifu:"))
        self.key = f"{prefix}lesson_reset:{user_id}:{course_id}:{lesson_id}"
        self.request_id = request_id
        self.limit = int(app.config.get("LESSON_RESET_LIMIT", 9999))
        self.state = {"count": 0, "requests": []}
        self.duplicate = False
        self.client = None
        self.pool = None
        self.lock = None
        self.token = uuid.uuid4().hex
        self.stop = threading.Event()
        self.lost = threading.Event()
        self.renewer = None

    def __enter__(self) -> Self:
        """Serialize admission, retain successful retry receipts and check quota."""
        try:
            self.client = get_redis_client()
            if self.client is None:
                raise_error("server.learn.resetUnavailable")
            source_pool = getattr(self.client, "connection_pool", None)
            if source_pool is not None:
                self.pool = ConnectionPool(
                    connection_class=source_pool.connection_class,
                    **{
                        **source_pool.connection_kwargs,
                        "socket_connect_timeout": 1,
                        "socket_timeout": 1,
                        "retry": Retry(NoBackoff(), 0),
                        "retry_on_error": [],
                    },
                )
                self.client = Redis(connection_pool=self.pool)
            self.lock = self.client.lock(
                self.key + ":lock",
                timeout=_LOCK_SECONDS,
                blocking_timeout=3,
                thread_local=False,
            )
            if not self.lock.acquire(token=self.token):
                raise_error("server.learn.resetUnavailable")
            self.renewer = threading.Thread(
                target=self._renew, daemon=True, name="lesson-reset-lock-renewer"
            )
            self.renewer.start()
            raw = self.client.get(self.key)
            if raw is not None:
                state = json.loads(raw)
                if (
                    not isinstance(state, dict)
                    or type(state.get("count")) is not int
                    or state["count"] < 0
                    or not isinstance(state.get("requests"), list)
                    or not all(isinstance(item, str) for item in state["requests"])
                    or len(state["requests"]) != state["count"]
                ):
                    raise_error("server.learn.resetUnavailable")
                self.state = state
            self.duplicate = self.request_id in self.state["requests"]
        except Exception:
            self._release()
            raise_error("server.learn.resetUnavailable")
        if not self.duplicate and self.state["count"] >= self.limit:
            self._release()
            raise_error("server.learn.resetLimitReached")
        return self

    def _renew(self) -> None:
        """Keep slow SQL work from outliving the lock lease during normal operation."""
        while not self.stop.wait(_LOCK_SECONDS / 3):
            try:
                if not self.lock.extend(_LOCK_SECONDS, replace_ttl=True):
                    self.lost.set()
                    return
            except Exception:
                self.lost.set()
                return

    def check_before_commit(self) -> None:
        """Abort SQL work if this request has already lost its admission guard."""
        try:
            valid = not self.lost.is_set() and self.lock.extend(
                _LOCK_SECONDS, replace_ttl=True
            )
        except Exception:
            valid = False
        if not valid:
            raise_error("server.learn.resetUnavailable")

    def record_success(self) -> None:
        """Write count and retry receipt together, only after a durable SQL reset."""
        updated = {
            "count": self.state["count"] + 1,
            "requests": [*self.state["requests"], self.request_id],
        }
        recorded = self.client.eval(
            _WRITE_STATE,
            2,
            self.key,
            self.key + ":lock",
            self.token,
            json.dumps(updated),
        )
        if not recorded:
            message = "Reset committed after its guard was lost"
            raise RuntimeError(message)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release the guard after commit callbacks, or after a SQL rollback."""
        self._release()

    def _release(self) -> None:
        """Stop lease renewal and release only this request's lock."""
        self.stop.set()
        if self.renewer is not None:
            self.renewer.join(timeout=1)
        if self.lock is not None:
            with contextlib.suppress(Exception):
                self.lock.release()
        if self.pool is not None:
            with contextlib.suppress(Exception):
                self.pool.disconnect()


def get_lesson_reset_status(
    app: Flask,
    course_id: str,
    lesson_id: str,
    user_id: str,
    *,
    preview_mode: bool = False,
) -> dict[str, bool]:
    """Expose availability without revealing an allowance or remaining count."""
    with app_context_scope(app):
        require_reset_lesson(course_id, lesson_id)
        if preview_mode or is_course_reset_exempt(app, course_id, user_id):
            return {"can_reset": True}
        try:
            with LessonResetGuard(app, course_id, lesson_id, user_id, uuid.uuid4().hex):
                return {"can_reset": True}
        except Exception as exc:
            from flaskr.service.common.models import ERROR_CODE, AppError

            if (
                isinstance(exc, AppError)
                and exc.code == ERROR_CODE["server.learn.resetLimitReached"]
            ):
                return {"can_reset": False}
            raise
