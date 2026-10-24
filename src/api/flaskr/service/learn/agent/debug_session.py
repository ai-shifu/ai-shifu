"""Keep editor debug conversations separate from learner and teacher previews."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from flaskr.common.cache_provider import cache
from flaskr.service.common.models import raise_error
from flaskr.service.learn.agent.engine.session import Session
from flaskr.service.learn.learn_dtos import RunElementSSEMessageDTO
from flaskr.service.learn.preview_elements import PreviewElementRunAdapter

if TYPE_CHECKING:
    from collections.abc import Generator

    from flask import Flask
    from flaskr.service.learn.learn_dtos import PlaygroundPreviewRequest


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
    ) -> None:
        """Bind an opaque run ID to its teacher, course, and lesson."""
        identity = f"{user_bid}\0{shifu_bid}\0{outline_bid}\0{run_bid}"
        digest = hashlib.sha256(identity.encode()).hexdigest()
        prefix = app.config.get("REDIS_KEY_PREFIX", "ai-shifu")
        self._key = f"{prefix}:agent_debug:{digest}"

    def load(self, *, script: str) -> Session | None:
        """Resume only when the editor is still debugging the same script."""
        raw = cache.get(self._key)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            if (
                payload.get("script_hash")
                != hashlib.sha256(script.encode()).hexdigest()
            ):
                return None
            return Session.loads(payload["session"])
        except (KeyError, TypeError, ValueError):
            # A deployment may replace the engine while this short-lived session is open.
            # An incompatible history is treated as expired, never replayed into a new turn.
            return None

    def save(self, session: Session) -> None:
        """Save before the runner emits the turn's terminal event."""
        payload = {
            "script_hash": hashlib.sha256(session.script.script.encode()).hexdigest(),
            "session": session.dumps(),
        }
        cache.setex(self._key, self.TTL_SECONDS, json.dumps(payload))


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
    )
    if preview_request.user_input and store.load(script=script) is None:
        raise_error("server.learn.debugSessionExpired")
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
    last_message = None
    for message in adapter.process(
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
    ):
        last_message = message
        yield message
    if last_message and last_message.type == "done" and not last_message.is_terminal:
        # The lesson pauses at a question. Close this HTTP response for the editor;
        # the next answer resumes the stored engine session in a new request.
        yield RunElementSSEMessageDTO(
            type="done",
            event_type="done",
            content="",
            is_terminal=True,
        )
