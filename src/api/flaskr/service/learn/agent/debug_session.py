"""Keep editor debug conversations separate from learner and teacher previews."""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING

from flaskr.api.markdownflow import Session
from flaskr.common.cache_provider import (
    CacheUnavailableError,
    InMemoryCacheProvider,
    redis_cache,
)
from flaskr.dao import get_redis_client
from flaskr.service.common.models import raise_error
from flaskr.service.learn.agent.rewind import RewindUnavailableError
from flaskr.service.learn.learn_dtos import RunElementSSEMessageDTO
from flaskr.service.learn.preview_elements import PreviewElementRunAdapter
from redis.exceptions import RedisError

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

    from flask import Flask
    from flaskr.service.learn.learn_dtos import PlaygroundPreviewRequest


# Local development keeps debug state in process; configured Redis never uses this cache.
cache = InMemoryCacheProvider()


@contextmanager
def _debug_cache_access() -> Iterator[None]:
    try:
        yield
    except (RedisError, CacheUnavailableError):
        raise_error("server.learn.debugServiceUnavailable")


class DebugSessionStore:
    """An expiring session for one editor run of a draft lesson."""

    TTL_SECONDS = 30 * 60

    def __init__(
        self,
        app: Flask,
        *,
        user_bid: str,
        shifu_bid: str,
        outline_bid: str,
        run_bid: str,
        follow_script_edits: bool = False,
    ) -> None:
        """Bind an opaque run ID to its teacher, course, and lesson.

        ``follow_script_edits`` lets an answer resume the conversation after the
        author edited the draft; the run then continues under the edited script.
        """
        identity = f"{user_bid}\0{shifu_bid}\0{outline_bid}\0{run_bid}"
        digest = hashlib.sha256(identity.encode()).hexdigest()
        prefix = app.config.get("REDIS_KEY_PREFIX", "ai-shifu")
        self._key = f"{prefix}:agent_debug:{digest}"
        self._request_bid: str | None = None
        self._cache = redis_cache if get_redis_client() is not None else cache
        self._follow_script_edits = follow_script_edits

    @contextmanager
    def _write_lock(self) -> Iterator[None]:
        with _debug_cache_access():
            lock = self._cache.lock(
                f"{self._key}:write", timeout=10, blocking_timeout=10
            )
            acquired = lock.acquire(blocking=True, blocking_timeout=10)
        if not acquired:
            raise_error("server.learn.debugServiceUnavailable")
        try:
            yield
        except BaseException:
            # Cleanup must preserve the original business error or stream cancellation.
            with suppress(RedisError, CacheUnavailableError):
                lock.release()
            raise
        else:
            with _debug_cache_access():
                lock.release()

    def begin_request(self) -> None:
        """Supersede saves from an earlier stream the browser may have just stopped."""
        request_bid = uuid.uuid4().hex
        with self._write_lock():
            with _debug_cache_access():
                self._cache.setex(f"{self._key}:request", self.TTL_SECONDS, request_bid)
            self._request_bid = request_bid

    def _payload(self, *, script: str, any_script: bool = False) -> dict | None:
        with _debug_cache_access():
            raw = self._cache.get(self._key)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict) or (
                not any_script
                and payload.get("script_hash")
                != hashlib.sha256(script.encode()).hexdigest()
            ):
                return None
        except (TypeError, ValueError):
            return None
        return payload

    def load(self, *, script: str) -> Session | None:
        """Resume when the editor is still debugging the same script.

        With ``follow_script_edits`` the stored conversation is returned even
        after the draft changed; the caller swaps in the edited script.
        """
        payload = self._payload(script=script, any_script=self._follow_script_edits)
        if payload is None:
            return None
        try:
            session = Session.loads(payload["session"])
        except (KeyError, TypeError, ValueError):
            # A deployment may replace the engine while this short-lived session is open.
            # An incompatible history is treated as expired, never replayed into a new turn.
            return None
        return session

    def save(self, session: Session) -> None:
        """Save before the runner emits the turn's terminal event."""
        if self._request_bid is None:
            self._save(session)
            return
        with self._write_lock():
            with _debug_cache_access():
                current = self._cache.get(f"{self._key}:request")
            if isinstance(current, bytes):
                current = current.decode()
            if current != self._request_bid:
                raise RewindUnavailableError
            self._save(session)

    def _save(self, session: Session) -> None:
        payload = {
            "script_hash": hashlib.sha256(session.script.script.encode()).hexdigest(),
            "session": session.dumps(),
        }
        encoded = json.dumps(payload)
        with _debug_cache_access():
            self._cache.setex(self._key, self.TTL_SECONDS, encoded)


def stream_debug_preview(
    app: Flask,
    *,
    preview_request: PlaygroundPreviewRequest,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    run_bid: str,
) -> Generator[RunElementSSEMessageDTO, None, None]:
    """Run the editor's draft through the existing 2.0 lesson and element pipeline."""
    from flaskr.service.learn.agent.lesson_entry import agent_lesson_events

    script = preview_request.get_document()
    if not script.strip():
        msg = "Markdown-Flow content is empty"
        raise ValueError(msg)
    store = DebugSessionStore(
        app,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        run_bid=run_bid,
        # Authors edit the draft while debugging; their next answer continues the
        # conversation under the edited script instead of discarding it.
        follow_script_edits=bool(preview_request.user_input),
    )
    session = store.load(script=script)
    if preview_request.user_input and session is None:
        raise_error("server.learn.debugSessionExpired")
    store.begin_request()
    yield RunElementSSEMessageDTO(
        type="preview_engine",
        event_type="preview_engine",
        content="2.0",
        is_terminal=False,
    )
    adapter = PreviewElementRunAdapter(
        app,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        user_bid=user_bid,
        run_session_bid=run_bid,
    )
    messages = adapter.process(
        agent_lesson_events(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_input=preview_request.user_input,
            preview_mode=True,
            script_override=script,
            debug_store=store,
            preview_variables=preview_request.variables,
        )
    )
    yield from messages
