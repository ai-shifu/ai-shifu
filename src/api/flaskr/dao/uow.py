"""Unit-of-work transaction boundary for service code.

Historically service functions called ``db.session.commit()`` wherever they
pleased (213 call sites at the 2026-07 inventory), which hides transaction
boundaries and makes helpers commit state their callers cannot roll back.
``unit_of_work()`` makes the boundary explicit:

    from flaskr.dao import uow

    def create_order(...):
        with uow.unit_of_work():
            ...  # add/flush freely; NO commits inside
        # committed here, or fully rolled back on exception

Rules:

- The OUTERMOST ``unit_of_work()`` commits on clean exit and rolls back on
  exception. Nested ``unit_of_work()`` blocks join the outer transaction and
  do nothing on exit, so a helper can declare a boundary without breaking its
  caller's.
- Code inside a unit of work must not call ``db.session.commit()`` /
  ``rollback()`` directly; use ``db.session.flush()`` when generated ids are
  needed mid-flow.
- ``retry_on_deadlock`` composes with this: decorate the function that OWNS
  the outermost unit of work, so a MySQL deadlock (rolled back quietly by the
  decorator) re-runs the whole transaction.
- A unit of work must not span a generator ``yield`` or a provider HTTP call.
  Multi-step flows (claim -> external call -> finalize) use one unit of work
  per persistence step, so each must-persist step is durable on its own.
- Reuse the caller's app context with ``app_context_scope(app)``; never push
  ``app.app_context()`` from service code, which would switch sessions.

Nesting depth is tracked per execution context via ``contextvars``, so
request handlers, the /run producer thread, and celery tasks each get an
independent depth counter.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import AbstractContextManager, contextmanager, nullcontext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask
    from flask.ctx import AppContext

from flask import current_app, has_app_context
from werkzeug.local import LocalProxy

logger = logging.getLogger(__name__)


def app_context_scope(app: object) -> AbstractContextManager[AppContext | None]:
    """Reuse the caller's app context (and DB session) when one is active.

    Flask-SQLAlchemy 3.1 scopes the session to the innermost app context, so
    pushing a nested ``app.app_context()`` silently switches to a *different*
    session and breaks the unit-of-work boundary owned by the caller. Only
    push a new context when none exists (celery workers, CLI commands,
    scripts) or when the active context belongs to a *different* Flask app:
    reusing that one would bind the session to the wrong database (the celery
    ``FlaskTask`` wrapper and multi-app test fixtures both hit this).
    """
    target = app._get_current_object() if isinstance(app, LocalProxy) else app
    if has_app_context() and current_app._get_current_object() is target:
        return nullcontext()
    return target.app_context()


_depth: contextvars.ContextVar[int] = contextvars.ContextVar("uow_depth", default=0)
_post_commit: contextvars.ContextVar[list] = contextvars.ContextVar(
    "uow_post_commit", default=None
)
_discard: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "uow_discard", default=False
)


def in_unit_of_work() -> bool:
    """Return True when the caller is inside an active unit of work."""
    return _depth.get() > 0


def require_transaction_owner(operation: str) -> None:
    """Refuse to run ``operation`` inside a caller's unit of work.

    Multi-step flows (claim -> provider call -> finalize, or "try the insert,
    re-read the winner on IntegrityError") only work when their inner
    ``unit_of_work()`` blocks are the OUTERMOST ones: nested, the first step
    would not be durable before the external call, and an IntegrityError would
    surface at the caller's commit instead of inside the handler. Call this at
    the top of such functions so a future nested caller fails loudly instead
    of silently changing the transaction semantics.
    """
    if in_unit_of_work():
        message = (
            f"{operation} owns its own transaction and must not be called "
            "inside an active unit_of_work()"
        )
        raise RuntimeError(message)


def on_commit(callback: object) -> None:
    """Run ``callback()`` after the OUTERMOST unit of work commits.

    Use this for external side effects (notifications, webhooks) that must
    only fire once the transaction they describe is durable. Inside a nested
    block the callback is deferred to the outermost commit; on rollback it is
    dropped. Outside any unit of work the callback runs immediately (there is
    no transaction to wait for). Callback exceptions are logged, not raised —
    the transaction is already committed.

    Callbacks run after the unit of work has fully unwound, so a callback may
    open its own ``unit_of_work()`` and that block commits normally.
    """
    callbacks = _post_commit.get()
    if callbacks is None:
        callback()
        return
    callbacks.append(callback)


def _run_post_commit(callbacks: list) -> None:
    for callback in callbacks:
        try:
            callback()
        except Exception:
            logger.exception("unit_of_work post-commit callback failed")


@contextmanager
def unit_of_work(*, discard: bool = False) -> Iterator[None]:
    """Commit on clean exit of the outermost block; roll back on exception.

    Nested blocks join the outer transaction (no commit, no rollback): an
    exception inside a nested block propagates and the outermost block rolls
    everything back, which is exactly the semantics scattered mid-function
    commits used to break.

    ``discard=True`` turns the transaction into a preview (``dry_run`` paths
    that used to call ``db.session.rollback()`` directly): the outermost block
    rolls back on clean exit instead of committing and drops post-commit
    callbacks. A nested block propagates the flag outward, so a dry run inside
    a larger unit of work never commits the caller's work by accident.
    """
    from flaskr import dao

    depth = _depth.get()
    token = _depth.set(depth + 1)
    callbacks_token = None
    discard_token = None
    if depth == 0:
        callbacks_token = _post_commit.set([])
        discard_token = _discard.set(discard)
    elif discard:
        # Restored by the outermost block's reset(); no token needed here.
        _discard.set(True)
    committed_callbacks: list | None = None
    try:
        yield
        if depth == 0:
            if _discard.get():
                dao.cleanup_session_after(None, source="unit_of_work discard")
            else:
                committed_callbacks = _post_commit.get()
                dao.db.session.commit()
    except Exception as exc:
        if depth == 0:
            # Classified cleanup: stream-interrupting failures (desync
            # errors surfaced by the commit) discard the connection, other
            # errors roll back; a rollback that itself fails escalates to
            # invalidate. Never emit a ROLLBACK on a desynced stream.
            dao.cleanup_session_after(exc, source="unit_of_work")
        raise
    except BaseException:
        if depth == 0:
            # GreenletExit landing inside the COMMIT's network IO leaves an
            # unread response owed on the wire; discard the connection
            # before any later cleanup could roll back on it.
            dao.invalidate_session(source="unit_of_work interrupt")
        raise
    finally:
        _depth.reset(token)
        if callbacks_token is not None:
            _post_commit.reset(callbacks_token)
        if discard_token is not None:
            _discard.reset(discard_token)
    # Post-commit callbacks run only after the depth counter has been reset:
    # a callback that opens its own unit_of_work() must be treated as a NEW
    # outermost block (and commit), not as a nested block that never commits.
    if committed_callbacks is not None:
        _run_post_commit(committed_callbacks)


@contextmanager
def autonomous_unit_of_work(app: Flask) -> Iterator[None]:
    """Commit a small, independent transaction on a fresh session.

    Deliberately pushes a NEW app context so Flask-SQLAlchemy hands out a
    session separate from the caller's: rows written here stay durable even
    when the surrounding unit of work rolls back, and the caller's staged
    rows are never committed early. Reserve this for audit and metering rows
    that must persist on their own (risk-control results, usage records)
    while a /run stream is still in flight; everything else joins the caller
    through plain ``unit_of_work()``.
    """
    depth_token = _depth.set(0)
    callbacks_token = _post_commit.set(None)
    discard_token = _discard.set(False)
    try:
        with app.app_context(), unit_of_work():
            yield
    finally:
        _discard.reset(discard_token)
        _post_commit.reset(callbacks_token)
        _depth.reset(depth_token)
