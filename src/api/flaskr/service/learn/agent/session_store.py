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

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from flaskr.api.markdownflow import Session
from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, require_transaction_owner, unit_of_work
from flaskr.i18n import _
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn.agent.models import (
    AGENT_SESSION_SCHEMA_VERSION,
    LearnAgentSession,
    active_key_for,
)
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask
    from sqlalchemy.orm import Query


PREVIEW_PRESENTATION_KEY = "ai_shifu_preview_presentation"
_ATTEMPT_SOURCE_KEY = "ai_shifu_lesson_source"


class PreviewGenerationDiscardedError(Exception):
    """A draft restart retired the generation this turn was teaching."""


def preview_presentation(row: LearnAgentSession | None) -> dict:
    """Read recognized host metadata without interpreting raw engine history."""
    try:
        data = json.loads(row.session_data) if row is not None else {}
    except (TypeError, ValueError):
        return {}
    return preview_presentation_from_document(data)


def preview_presentation_from_document(data: object) -> dict:
    """Read presentation from an already decoded session without parsing it again."""
    value = data.get(PREVIEW_PRESENTATION_KEY) if isinstance(data, dict) else None
    if (
        isinstance(value, dict)
        and value.get("version") == 1
        and isinstance(value.get("runs"), list)
        and all(isinstance(bid, str) for bid in value["runs"])
        and isinstance(value.get("questions"), dict)
        and isinstance(value.get("answers"), dict)
    ):
        return value
    return {}


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


@dataclass(frozen=True)
class LessonAttemptSource:
    """Physical content rows selected when an ordinary learning attempt starts."""

    preview_mode: bool
    outline_row_id: int | None = None
    course_row_id: int | None = None
    structure_row_id: int | None = None
    content_revision: int | None = None


class UnreadableLessonAttemptSourceError(AppError):
    """The session's provenance cannot safely be used to serve the attempt."""

    def __init__(self) -> None:
        """Use the existing recovery message and response code."""
        key = "server.learn.agentRewindUnavailable"
        super().__init__(
            _(key), ERROR_CODE.get(key, ERROR_CODE["server.common.unknownError"])
        )


def _attempt_source(row: LearnAgentSession) -> LessonAttemptSource:
    try:
        document = json.loads(row.session_data) if row.session_data else {}
    except (TypeError, ValueError) as exc:
        raise UnreadableLessonAttemptSourceError from exc
    if not isinstance(document, dict):
        raise UnreadableLessonAttemptSourceError
    if _ATTEMPT_SOURCE_KEY not in document:
        # The preexisting canonical key was used only by published learning.
        return LessonAttemptSource(
            preview_mode=False, content_revision=row.content_revision
        )
    source = document[_ATTEMPT_SOURCE_KEY]
    if not isinstance(source, dict) or type(source.get("preview_mode")) is not bool:
        raise UnreadableLessonAttemptSourceError
    try:
        return LessonAttemptSource(**source)
    except TypeError as exc:
        raise UnreadableLessonAttemptSourceError from exc


def _shared_session_query(*, user_bid: str, shifu_bid: str, outline_bid: str) -> Query:
    return LearnAgentSession.query.filter_by(
        active_key=active_key_for(user_bid, outline_bid),
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        deleted=0,
    )


def load_lesson_attempt_source(
    *, user_bid: str, shifu_bid: str, outline_bid: str, for_update: bool = False
) -> LessonAttemptSource | None:
    """Return the canonical attempt's pinned source, including unstarted reservations."""
    query = _shared_session_query(
        user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
    )
    if for_update:
        query = query.populate_existing().with_for_update()
    row = query.first()
    return _attempt_source(row) if row is not None else None


def bind_lesson_attempt_source(
    row: LearnAgentSession, source: LessonAttemptSource
) -> None:
    """Attach immutable content provenance to a reserved or legacy preview session."""
    document = json.loads(row.session_data or "{}")
    document[_ATTEMPT_SOURCE_KEY] = asdict(source)
    row.session_data = json.dumps(document, ensure_ascii=False)


def _is_attempt_reservation_conflict(error: IntegrityError) -> bool:
    args = error.orig.args if error.orig is not None else ()
    if args == ("UNIQUE constraint failed: learn_agent_sessions.active_key",):
        return True
    if len(args) < 2 or args[0] != 1062:
        return False
    index = str(args[1]).rpartition(" for key ")[2].strip("'\"`").rsplit(".", 1)[-1]
    return index == "uq_learn_agent_sessions_active"


def stage_lesson_attempt_source(
    *, user_bid: str, shifu_bid: str, outline_bid: str, source: LessonAttemptSource
) -> bool:
    """Pin a new attempt while its progress row is locked, before making history visible."""
    query = _shared_session_query(
        user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
    )
    # A locking read of a missing unique key can gap-lock the insertion point in MySQL.
    # Let the unique index choose the winner instead, and lock only a row we observed.
    row = query.first()
    if row is not None:
        row = query.filter_by(id=row.id).populate_existing().with_for_update().first()
        if row is None:
            return False
        current = _attempt_source(row)
        if current.outline_row_id is None:
            # A legacy published session has no physical source to relabel.
            return not source.preview_mode
        return current == source
    row = LearnAgentSession(
        agent_session_bid=uuid.uuid4().hex,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        active_key=active_key_for(user_bid, outline_bid),
    )
    bind_lesson_attempt_source(row, source)
    try:
        with db.session.begin_nested():
            db.session.add(row)
            db.session.flush()
    except IntegrityError as error:
        if not _is_attempt_reservation_conflict(error):
            raise
        return False
    return True


def load_agent_session(
    app: Flask, user_bid: str, outline_item_bid: str, *, preview_mode: bool = False
) -> Session | None:
    """Return the learner's session for this lesson, or None if they have not started it.

    Raises `StoredSessionUnusable` when a row exists but was written by code whose sessions this
    version cannot read.
    """
    with app_context_scope(app):
        return _load(user_bid, outline_item_bid, preview_mode=preview_mode)


def active_session_id(
    user_bid: str, outline_item_bid: str, *, preview_mode: bool = False
) -> str | None:
    """Return the native id of the learner's live session for this lesson, if any.

    This is the Langfuse Session the lesson's turns are traced in. Only the id is read, so a
    session this build could not resume still names its Session.
    """
    row = LearnAgentSession.query.filter(
        LearnAgentSession.active_key
        == active_key_for(user_bid, outline_item_bid, preview_mode=preview_mode)
    ).first()
    if row is None:
        return None
    try:
        session_id = json.loads(row.session_data).get("id")
    except (TypeError, ValueError, AttributeError):
        return None
    return session_id if isinstance(session_id, str) and session_id else None


def _active_preview_session_query(
    *, user_bid: str, shifu_bid: str, outline_bid: str
) -> Query:
    return LearnAgentSession.query.filter_by(
        active_key=active_key_for(user_bid, outline_bid, preview_mode=True),
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        deleted=0,
    )


def _load(
    user_bid: str, outline_item_bid: str, *, preview_mode: bool = False
) -> Session | None:
    row = LearnAgentSession.query.filter(
        LearnAgentSession.active_key
        == active_key_for(user_bid, outline_item_bid, preview_mode=preview_mode)
    ).first()
    if row is None:
        return None
    if not row.schema_version and _ATTEMPT_SOURCE_KEY in row.session_data:
        # The host has already pinned the source but the engine has no messages yet.
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
    stage: Callable[[], object] | None = None,
    preview_generation: str | None = None,
    content_revision: int | None = None,
) -> None:
    """Write the session back, replacing the learner's previous one for this lesson.

    `stage` runs inside this transaction, for rows that only make sense together with the session
    -- the block a turn's elements hang off, which would orphan them if it landed without one.

    Returns once the row is committed. Callers that stream events must not tell the learner a turn
    finished before this returns, and must not call this inside their own unit of work: nested, it
    would return with the write still pending in the caller's transaction.
    """
    require_transaction_owner("save_agent_session", app)
    key = active_key_for(user_bid, outline_item_bid, preview_mode=preview_mode)
    with app_context_scope(app), unit_of_work():
        row = None
        if preview_generation is not None:
            if not preview_mode:
                raise PreviewGenerationDiscardedError
            row = (
                _active_preview_session_query(
                    user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_item_bid
                )
                .filter_by(agent_session_bid=preview_generation)
                .with_for_update()
                .first()
            )
            if row is None:
                raise PreviewGenerationDiscardedError
        if stage is not None:
            stage()
        if row is None:
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
        _apply(row, session, content_revision=content_revision)


def _apply(
    row: LearnAgentSession, session: Session, *, content_revision: int | None = None
) -> None:
    """Copy the session onto the row, recording what wrote it."""
    # The engine's own stores stamp this before serializing; without it the timestamp inside the
    # document stays at whatever the session was created with, however many turns it has run.
    session.updated_at = datetime.now(UTC).isoformat()
    try:
        previous = json.loads(row.session_data) if row.session_data else {}
    except (TypeError, ValueError):
        previous = {"messages": ["unknown"]}
    if not isinstance(previous, dict):
        previous = {"messages": ["unknown"]}
    presentation = preview_presentation_from_document(previous)
    data = json.loads(session.dumps())
    # A loader-incompatible session starts a new engine attempt on the same DB
    # row. Its baseline follows its new document ID, just like an explicit retake.
    new_attempt = previous.get("id") != data["id"]
    if new_attempt:
        row.content_revision = None
    # Continuing the same attempt, including a legacy NULL baseline, must never
    # relabel the original lesson content. Empty reservations have no learning messages.
    if (
        (new_attempt or not previous.get("messages"))
        and data.get("messages")
        and row.content_revision is None
    ):
        row.content_revision = (
            content_revision if content_revision and content_revision > 0 else 0
        )
    if presentation:
        data[PREVIEW_PRESENTATION_KEY] = presentation
    if _ATTEMPT_SOURCE_KEY in previous:
        data[_ATTEMPT_SOURCE_KEY] = previous[_ATTEMPT_SOURCE_KEY]
    row.session_data = json.dumps(data, ensure_ascii=False)
    row.schema_version = AGENT_SESSION_SCHEMA_VERSION
    row.pydantic_ai_version = _pydantic_ai_version()
    row.turn = session.turn
    row.finished = 1 if session.finished else 0


def stage_agent_session_discard(
    *,
    user_bid: str,
    outline_item_bid: str,
    preview_mode: bool | None = None,
    shifu_bid: str | None = None,
) -> None:
    """Retire this learner's sessions for the lesson without committing.

    For callers that already own a transaction and need the discard to land with the rest of it --
    resetting a lesson retires its progress records and its session together, or neither, so a
    reset cannot half-apply and leave the learner resumed into the conversation they just cleared.

    Legacy callers retire both scopes. Explicit preview resets retire only the draft.
    """
    query = LearnAgentSession.query.filter(
        LearnAgentSession.user_bid == user_bid,
        LearnAgentSession.outline_item_bid == outline_item_bid,
        LearnAgentSession.deleted == 0,
    )
    if shifu_bid is not None:
        query = query.filter(LearnAgentSession.shifu_bid == shifu_bid)
    if preview_mode is not None:
        query = query.filter(
            LearnAgentSession.active_key
            == active_key_for(user_bid, outline_item_bid, preview_mode=preview_mode)
        )
    rows = query.with_for_update().all()
    for row in rows:
        row.deleted = 1
        # Releasing the key is what lets the next start claim it; NULLs do not collide, so
        # every discarded row can keep sitting there for support questions.
        row.active_key = None
