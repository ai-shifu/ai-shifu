"""Read and write agent lesson sessions.

The engine defines a `SessionStore` protocol; this is the implementation backed by this project's
database. It is deliberately narrow: load a session for a learner and a lesson, save it back, and
refuse rows the running code cannot understand.

**Saving comes before telling the learner a turn is done.** The engine streams its events as they
happen, so a caller that forwards a terminal event before the session is stored leaves the learner
believing a turn succeeded that the next request will not find: answers, pending interactions and
the finished flag all revert.

That promise only holds if the write is durable when `save_agent_session` returns, and a
`unit_of_work()` nested inside a caller's own does not commit -- it joins the caller's transaction,
which a later failure can still roll back. So this owns its transaction and says so: calling it
inside an open unit of work raises rather than quietly weakening the guarantee the caller is about
to rely on.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, require_transaction_owner, unit_of_work
from flaskr.service.learn.agent.engine import Session
from flaskr.service.learn.agent.models import (
    AGENT_SESSION_SCHEMA_VERSION,
    LearnAgentSession,
    active_key_for,
)
from sqlalchemy.exc import IntegrityError

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
    app: Flask, user_bid: str, outline_item_bid: str, *, preview_mode: bool = False
) -> Session | None:
    """Return the learner's session for this lesson, or None if they have not started it.

    Raises `StoredSessionUnusable` when a row exists but was written by code whose sessions this
    version cannot read.
    """
    with app_context_scope(app):
        return _load(user_bid, outline_item_bid, preview_mode=preview_mode)


def _load(
    user_bid: str, outline_item_bid: str, *, preview_mode: bool = False
) -> Session | None:
    row = LearnAgentSession.query.filter(
        LearnAgentSession.active_key
        == active_key_for(user_bid, outline_item_bid, preview_mode=preview_mode)
    ).first()
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
    preview_mode: bool = False,
) -> None:
    """Write the session back, replacing the learner's previous one for this lesson.

    Returns once the row is committed. Callers that stream events must not tell the learner a turn
    finished before this returns, and must not call this inside their own unit of work: nested, it
    would return with the write still pending in the caller's transaction.
    """
    require_transaction_owner("save_agent_session", app)
    key = active_key_for(user_bid, outline_item_bid, preview_mode=preview_mode)
    with app_context_scope(app), unit_of_work():
        row = LearnAgentSession.query.filter(
            LearnAgentSession.active_key == key
        ).first()
        if row is None:
            row = LearnAgentSession(
                agent_session_bid=str(uuid.uuid4()).replace("-", ""),
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_item_bid=outline_item_bid,
                active_key=key,
            )
            db.session.add(row)
            try:
                # A concurrent first save -- the learner opened the lesson in two tabs -- can get
                # here too. The unique index is what decides between them; without this the loser
                # would insert a second live row and the next load would silently drop one
                # learner's progress.
                with db.session.begin_nested():
                    db.session.flush()
            except IntegrityError:
                row = LearnAgentSession.query.filter(
                    LearnAgentSession.active_key == key
                ).one()
        _apply(row, session)


def _apply(row: LearnAgentSession, session: Session) -> None:
    """Copy the session onto the row, recording what wrote it."""
    # The engine's own stores stamp this before serializing; without it the timestamp inside the
    # document stays at whatever the session was created with, however many turns it has run.
    session.updated_at = datetime.now(UTC).isoformat()
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
    require_transaction_owner("discard_agent_session", app)
    with app_context_scope(app), unit_of_work():
        stage_agent_session_discard(
            user_bid=user_bid, outline_item_bid=outline_item_bid
        )


def stage_agent_session_discard(*, user_bid: str, outline_item_bid: str) -> None:
    """Retire this learner's sessions for the lesson without committing.

    For callers that already own a transaction and need the discard to land with the rest of it --
    resetting a lesson retires its progress records and its session together, or neither, so a
    reset cannot half-apply and leave the learner resumed into the conversation they just cleared.

    Both scopes go: an author resetting a lesson means the preview too.
    """
    rows = LearnAgentSession.query.filter(
        LearnAgentSession.user_bid == user_bid,
        LearnAgentSession.outline_item_bid == outline_item_bid,
        LearnAgentSession.deleted == 0,
    ).all()
    for row in rows:
        row.deleted = 1
        # Releasing the key is what lets the next start claim it; NULLs do not collide, so
        # every discarded row can keep sitting there for support questions.
        row.active_key = None
