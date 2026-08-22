"""Surface gevent hub-level errors in the application log.

A callback that dies inside the gevent hub (e.g. the AssertionError seen in
``AbstractLinkable._notify_links``) is printed to stderr by the hub and never
reaches any application-level ``except``. Such a crash can corrupt a greenlet
wakeup chain and silently interrupt an in-flight DB exchange, leaving the
MySQL connection with an unread response (off-by-one protocol desync).

This observer wraps ``hub.handle_error`` so every hub error is ALSO logged
through the application logger with the failing context object named, which
turns the anonymous stderr traceback into an attributable event.
"""

from __future__ import annotations

import contextlib
import os

_OBSERVER_FLAG = "_ai_shifu_hub_error_observer"


def _describe_context(context: object) -> str:
    # repr() of an arbitrary hub context (Semaphore, Event, watcher, callback)
    # can be large or can itself raise; keep it short and never fail.
    try:
        text = repr(context)
    except Exception:
        text = "<repr failed>"
    if len(text) > 300:
        text = text[:300] + "...(truncated)"
    return f"{type(context).__name__}: {text}"


def install_hub_error_observer(logger: object, hub: object = None) -> bool:
    """Wrap the hub's ``handle_error`` to log hub-level failures.

    Returns True when the observer is active (installed now or previously).
    Safe to call multiple times; the wrapper is installed at most once per
    hub. When ``hub`` is None the calling thread's gevent hub is used.
    """
    if hub is None:
        try:
            from gevent import get_hub, monkey
        except ImportError:
            return False
        if not monkey.is_module_patched("socket"):
            # Without monkey-patching there is no gevent scheduling to
            # observe, and get_hub() would needlessly CREATE a hub in a
            # plain-threaded process (e.g. gthread workers).
            return False
        hub = get_hub()

    if getattr(hub, _OBSERVER_FLAG, False):
        return True

    original_handle_error = hub.handle_error

    def handle_error(
        context: object, exc_type: object, value: object, tb: object
    ) -> object:
        # Log BEFORE delegating: the original handler may re-raise for
        # system errors. Nothing in here may raise or block - a failure in
        # the error path would take down the hub itself.
        with contextlib.suppress(Exception):
            logger.error(
                "gevent hub error (pid=%s): context=%s exc=%s: %s. "
                "A crashed hub callback can break a greenlet wakeup and "
                "silently interrupt an in-flight DB exchange.",
                os.getpid(),
                _describe_context(context),
                getattr(exc_type, "__name__", exc_type),
                value,
                exc_info=(exc_type, value, tb) if exc_type is not None else None,
            )
        return original_handle_error(context, exc_type, value, tb)

    hub.handle_error = handle_error
    setattr(hub, _OBSERVER_FLAG, True)
    return True
