"""Application-facing retake contracts; HTTP callers enforce course permissions."""

from functools import partial
from typing import Never

from flask import Flask
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common import raise_error
from flaskr.service.learn.preview_permissions import has_course_collaboration_permission
from flaskr.service.learn.retake_ledger import (
    ensure_default_policy,
    get_allowance,
    reserve_attempt,
)
from flaskr.service.learn.retake_models import LessonRetakeRun
from flaskr.service.learn.retake_policy import RetakeRuleError, RetakeState
from flaskr.service.learn.retake_recovery import stage_reset_records
from flaskr.service.learn.retake_rollout import (
    configured_retake_namespace,
    retake_namespace,
)
from flaskr.service.learn.retake_run_guard import pending_lesson_attempt
from flaskr.service.shifu.api import get_shifu_creator_bid


def raise_retake_error(error: RetakeRuleError) -> Never:
    """Expose stable localized outcomes rather than internal rule identifiers."""
    key = {
        "retake_reload_not_supported": "server.learn.retakeUseChapter",
        "retake_limit_reached": "server.learn.retakeLimitReached",
        "retake_in_progress": "server.learn.retakeInProgress",
        "attempt_not_reserved": "server.learn.retakeInProgress",
        "nothing_to_retake": "server.learn.retakeNotStarted",
        "previous_attempt_released": "server.learn.retakePreviousFailed",
        "invalid_identity": "server.learn.retakeInvalidRequest",
        "invalid_limit": "server.learn.retakeInvalidRequest",
    }.get(str(error), "server.learn.retakeUnavailable")
    raise_error(key)


def read_policy(app: Flask, shifu_bid: str) -> dict:
    """Compatibility response: teacher configuration is no longer available."""
    _ = (app, shifu_bid)  # Preserve the retired route contract for old clients.
    return {"available": False, "configured": False, "limit": None}


def update_policy(app: Flask, shifu_bid: str, limit: object) -> dict:
    """Reject old clients instead of accepting an ineffective teacher setting."""
    _ = (app, shifu_bid, limit)  # Old settings must not override the platform rule.
    raise_error("server.learn.retakeUnavailable")


def read_status(
    app: Flask,
    *,
    shifu_bid: str,
    user_bid: str,
    outline_bid: str,
    preview_mode: bool = False,
) -> dict:
    """Read this learner's balance; this response never grants admission."""
    namespace = None if preview_mode else retake_namespace(shifu_bid)
    result = {
        "available": False,
        "allowed": True,
        "in_progress": False,
        "quota_exempt": False,
    }
    if namespace is None:
        if not preview_mode:
            candidate = configured_retake_namespace()
            if candidate is not None:
                with app_context_scope(app):
                    if pending_lesson_attempt(
                        namespace=candidate,
                        shifu_bid=shifu_bid,
                        user_bid=user_bid,
                        outline_bid=outline_bid,
                    ):
                        return {
                            **result,
                            "available": True,
                            "allowed": False,
                            "in_progress": True,
                            "quota_exempt": has_course_collaboration_permission(
                                app, user_bid, shifu_bid
                            ),
                        }
        return result
    with app_context_scope(app), unit_of_work():
        ensure_default_policy(app, namespace=namespace, shifu_bid=shifu_bid)
        quota_exempt = bool(user_bid) and (
            get_shifu_creator_bid(app, shifu_bid) == user_bid
            or has_course_collaboration_permission(app, user_bid, shifu_bid)
        )
        balance = get_allowance(
            app,
            namespace=namespace,
            shifu_bid=shifu_bid,
            user_bid=user_bid,
            outline_bid=outline_bid,
            quota_exempt=quota_exempt,
        )
        if balance is None:
            return result
        busy = (
            LessonRetakeRun.query.filter_by(
                namespace=namespace,
                shifu_bid=shifu_bid,
                user_bid=user_bid,
                outline_bid=outline_bid,
                finished_at=None,
            ).first()
            is not None
        )
        return {
            "available": True,
            "allowed": balance.allowed and not busy and not balance.reserved,
            "in_progress": busy or bool(balance.reserved),
            "quota_exempt": quota_exempt,
        }


def try_limited_reset(
    app: Flask,
    *,
    shifu_bid: str,
    user_bid: str,
    outline_bid: str,
    request_id: str | None,
) -> bool:
    """Handle an opted-in reset atomically; False selects the legacy path."""
    namespace = retake_namespace(shifu_bid)
    if namespace is None:
        candidate = configured_retake_namespace()
        if candidate is not None:
            with app_context_scope(app):
                if pending_lesson_attempt(
                    namespace=candidate,
                    shifu_bid=shifu_bid,
                    user_bid=user_bid,
                    outline_bid=outline_bid,
                ):
                    raise_error("server.learn.retakeInProgress")
        return False
    with app_context_scope(app), unit_of_work():
        ensure_default_policy(app, namespace=namespace, shifu_bid=shifu_bid)
        # Resolve course-specific staff access, never a client/global role flag.
        quota_exempt = bool(user_bid) and (
            get_shifu_creator_bid(app, shifu_bid) == user_bid
            or has_course_collaboration_permission(app, user_bid, shifu_bid)
        )
        try:
            _, state = reserve_attempt(
                app,
                namespace=namespace,
                shifu_bid=shifu_bid,
                user_bid=user_bid,
                outline_bid=outline_bid,
                request_id=request_id,
                quota_exempt=quota_exempt,
                stage_reset=partial(
                    stage_reset_records,
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    outline_bid=outline_bid,
                ),
            )
        except RetakeRuleError as exc:
            raise_retake_error(exc)
        if state == RetakeState.RELEASED:
            raise_error("server.learn.retakePreviousFailed")
    return True
