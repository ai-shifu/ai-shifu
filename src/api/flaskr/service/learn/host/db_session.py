"""Own the database session around a streamed run: probe, checkpoint, discard and remove."""

import sys
import uuid

from flask import Flask
from flaskr.dao import (
    db,
    invalidate_session,
    is_abnormal_stream_termination,
)
from flaskr.dao.uow import unit_of_work
from sqlalchemy import text as sa_text
from sqlalchemy.exc import InterfaceError, OperationalError, ResourceClosedError


def _remove_db_session_safely(app: Flask, *, source: str) -> None:
    # In finally blocks sys.exc_info still sees a propagating
    # SystemExit/GeneratorExit that never reached an except handler
    # (raised during IO inside the generator frame); discard the connection
    # before removal in that case instead of letting remove() emit a
    # ROLLBACK on a possibly desynced stream. Uses this module's ``db`` so
    # tests that monkeypatch this module's db keep working.
    exc = sys.exc_info()[1]
    if exc is not None and is_abnormal_stream_termination(exc):
        invalidate_session(source=source, session=db.session)
    try:
        db.session.remove()
    except Exception:
        app.logger.warning("%s db session cleanup failed", source, exc_info=True)


def _discard_session_connection(*, source: str) -> None:
    """Drop the session's DB connection instead of returning it to the pool.

    Used when the streaming generator terminates abnormally: the close (or a
    protocol error) can leave an unconsumed response owed on the wire, and
    rolling back on such a connection consumes stale packets and returns a
    poisoned connection to the pool. Delegates to the shared dao helper,
    which resolves the REAL Session through the scoped registry -
    scoped_session does not proxy ``Session.invalidate``, so calling
    ``db.session.invalidate()`` directly raises AttributeError and silently
    does nothing.
    """
    invalidate_session(source=source, session=db.session)


# Number of connection checkouts to probe before giving up: the pool may hold
# more than one poisoned connection, so retry a couple of fresh checkouts.
_CONNECTION_PROBE_ATTEMPTS = 3


def _ensure_healthy_db_connection(app: Flask) -> None:
    """Drop pooled connections whose MySQL protocol stream is desynced.

    A streaming run interrupted mid-IO can return a connection to the pool
    with an unread response packet still buffered. pool_pre_ping cannot catch
    this: the ping reads the stale packet and "succeeds", leaving every later
    query on that connection off by one response, which surfaces as
    ResourceClosedError on SELECTs and pymysql 2014 "Command Out of Sync" on
    rollback. Probe with a nonce echo before the run touches business tables;
    on any mismatch invalidate the connection and retry on a fresh checkout.
    The probe leaves the session transaction open so the run keeps using the
    verified connection.
    """
    last_error: Exception | None = None
    for attempt in range(1, _CONNECTION_PROBE_ATTEMPTS + 1):
        nonce = uuid.uuid4().hex
        try:
            echoed = db.session.execute(
                sa_text("SELECT :nonce"), {"nonce": nonce}
            ).scalar()
            if echoed == nonce:
                return
            last_error = None
            app.logger.warning(
                "db connection probe echoed %r instead of the nonce "
                "(attempt %d/%d); invalidating desynced connection",
                echoed,
                attempt,
                _CONNECTION_PROBE_ATTEMPTS,
            )
        except (ResourceClosedError, OperationalError, InterfaceError) as exc:
            last_error = exc
            app.logger.warning(
                "db connection probe failed (attempt %d/%d); "
                "invalidating desynced connection: %s",
                attempt,
                _CONNECTION_PROBE_ATTEMPTS,
                exc,
            )
        # Session.invalidate() both resets the session state WITHOUT emitting
        # SQL and discards the raw connection - a rollback here would send a
        # ROLLBACK on the very stream that just proved desynced.
        _discard_session_connection(source="db connection probe failure")
    if last_error is not None:
        raise last_error
    message = (
        "db connection probe kept returning mismatched results; "
        "no healthy connection available"
    )
    raise RuntimeError(message)


def _commit_pending_step() -> None:
    """Make rows staged between run steps durable.

    ``RunRecorder`` bounds the per-step writes; this checkpoint runs only at
    step boundaries (after a reload rewind, after the stream completes, and
    on ``BreakError``) so collaborators that still stage rows with plain
    flushes never span a ``yield``. The block stages nothing itself: the
    commit is the point.
    """
    with unit_of_work():
        pass
