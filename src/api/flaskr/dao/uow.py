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

Nesting depth is tracked per execution context via ``contextvars``, so
request handlers, the /run producer thread, and celery tasks each get an
independent depth counter.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_depth: contextvars.ContextVar[int] = contextvars.ContextVar("uow_depth", default=0)
_post_commit: contextvars.ContextVar[list] = contextvars.ContextVar(
    "uow_post_commit", default=None
)


def in_unit_of_work() -> bool:
    """Return True when the caller is inside an active unit of work."""
    return _depth.get() > 0


def on_commit(callback) -> None:
    """Run ``callback()`` after the OUTERMOST unit of work commits.

    Use this for external side effects (notifications, webhooks) that must
    only fire once the transaction they describe is durable. Inside a nested
    block the callback is deferred to the outermost commit; on rollback it is
    dropped. Outside any unit of work the callback runs immediately (there is
    no transaction to wait for). Callback exceptions are logged, not raised —
    the transaction is already committed.
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
        except Exception as exc:  # noqa: BLE001 - commit already durable
            logger.exception("unit_of_work post-commit callback failed: %s", exc)


@contextmanager
def unit_of_work():
    """Commit on clean exit of the outermost block; roll back on exception.

    Nested blocks join the outer transaction (no commit, no rollback): an
    exception inside a nested block propagates and the outermost block rolls
    everything back, which is exactly the semantics scattered mid-function
    commits used to break.
    """
    from flaskr import dao

    depth = _depth.get()
    token = _depth.set(depth + 1)
    callbacks_token = None
    if depth == 0:
        callbacks_token = _post_commit.set([])
    try:
        yield
        if depth == 0:
            callbacks = _post_commit.get()
            dao.db.session.commit()
            _run_post_commit(callbacks)
    except Exception:
        if depth == 0:
            try:
                dao.db.session.rollback()
            except Exception as rollback_exc:  # noqa: BLE001 - best-effort cleanup
                logger.warning("unit_of_work rollback failed: %s", rollback_exc)
        raise
    finally:
        _depth.reset(token)
        if callbacks_token is not None:
            _post_commit.reset(callbacks_token)
