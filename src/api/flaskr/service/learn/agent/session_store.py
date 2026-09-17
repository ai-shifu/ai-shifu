"""Read and write agent lesson sessions.

The engine defines a `SessionStore` protocol; this is the implementation backed by this project's
database. It is deliberately narrow: load a session for a learner and a lesson, save it back, and
refuse rows the running code cannot understand.

**Saving comes before telling the learner a turn is done.** The engine streams its events as they
happen, so a caller that forwards a terminal event before the session is stored leaves the learner
believing a turn succeeded that the next request will not find: answers, pending interactions and
the finished flag all revert. `save` is synchronous and raises, so the caller can hold the terminal
event until it returns and turn a failure into an error rather than a silent rollback.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent.engine import Session
from flaskr.service.learn.agent.models import (
    AGENT_SESSION_SCHEMA_VERSION,
    LearnAgentSession,
)

if TYPE_CHECKING:
    from flask import Flask


def _pydantic_ai_version() -> str:
    """Report the pydantic-ai version running now, which stored histories are tied to."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("pydantic-ai-slim")
    except PackageNotFoundError:  # pragma: no cover - the package is a hard dependency
        return ""


class StoredSessionUnusable(Exception):  # noqa: N818 - this is an outcome, not a failure
    """The stored session cannot be resumed by the code running now.

    Raised rather than returned so a caller cannot forget to check. What the host should do is
    start the lesson again: the learner loses the conversation, which is why the versions are
    compared rather than the history being parsed hopefully.
    """


def load_agent_session(
    app: Flask, user_bid: str, outline_item_bid: str
) -> Session | None:
    """Return the learner's session for this lesson, or None if they have not started it.

    Raises `StoredSessionUnusable` when a row exists but was written by code whose sessions this
    version cannot read.
    """
    _ = app  # the session comes from the app context; kept for call-site symmetry
    row = (
        LearnAgentSession.query.filter(
            LearnAgentSession.user_bid == user_bid,
            LearnAgentSession.outline_item_bid == outline_item_bid,
            LearnAgentSession.deleted == 0,
        )
        .order_by(LearnAgentSession.id.desc())
        .first()
    )
    if row is None:
        return None
    if row.schema_version != AGENT_SESSION_SCHEMA_VERSION:
        msg = (
            f"session {row.agent_session_bid} was written with schema version "
            f"{row.schema_version}, this build reads {AGENT_SESSION_SCHEMA_VERSION}"
        )
        raise StoredSessionUnusable(msg)
    running = _pydantic_ai_version()
    if row.pydantic_ai_version != running:
        msg = (
            f"session {row.agent_session_bid} holds a message history from pydantic-ai "
            f"{row.pydantic_ai_version}, this build runs {running}"
        )
        raise StoredSessionUnusable(msg)
    try:
        return Session.loads(row.session_data)
    except Exception as exc:
        msg = f"session {row.agent_session_bid} could not be deserialized: {exc}"
        raise StoredSessionUnusable(msg) from exc


def save_agent_session(
    app: Flask,
    session: Session,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_item_bid: str,
) -> None:
    """Write the session back, replacing the learner's previous one for this lesson.

    Returns once the row is committed. Callers that stream events must not tell the learner a turn
    finished before this returns.
    """
    _ = app  # the session comes from the app context; kept for call-site symmetry
    with unit_of_work():
        row = (
            LearnAgentSession.query.filter(
                LearnAgentSession.user_bid == user_bid,
                LearnAgentSession.outline_item_bid == outline_item_bid,
                LearnAgentSession.deleted == 0,
            )
            .order_by(LearnAgentSession.id.desc())
            .first()
        )
        if row is None:
            row = LearnAgentSession(
                agent_session_bid=str(uuid.uuid4()).replace("-", ""),
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_item_bid=outline_item_bid,
            )
            db.session.add(row)
        row.session_data = session.dumps()
        row.schema_version = AGENT_SESSION_SCHEMA_VERSION
        row.pydantic_ai_version = _pydantic_ai_version()
        row.turn = session.turn
        row.finished = 1 if session.finished else 0


def discard_agent_session(app: Flask, user_bid: str, outline_item_bid: str) -> None:
    """Drop the learner's session for this lesson so the next run starts over.

    Used when a stored session cannot be resumed, and when the teacher switches the lesson's engine
    out from under a learner who is part-way through it.
    """
    _ = app  # the session comes from the app context; kept for call-site symmetry
    with unit_of_work():
        rows = LearnAgentSession.query.filter(
            LearnAgentSession.user_bid == user_bid,
            LearnAgentSession.outline_item_bid == outline_item_bid,
            LearnAgentSession.deleted == 0,
        ).all()
        for row in rows:
            row.deleted = 1
