"""
Shifu context utilities.

This module provides a simple thread-local context for shifu-related
metadata that should be accessible during a single API request, including
background threads spawned from that request.
"""

from __future__ import annotations

import threading
from functools import wraps
from typing import Optional, Dict, Any, Callable

_context_local = threading.local()


def set_shifu_context(
    shifu_bid: Optional[str], shifu_creator_bid: Optional[str]
) -> None:
    """
    Set the shifu context for the current thread.

    Args:
        shifu_bid: Shifu business identifier
        shifu_creator_bid: Shifu creator user business identifier
    """
    _context_local.shifu_bid = shifu_bid
    _context_local.shifu_creator_bid = shifu_creator_bid


def clear_shifu_context() -> None:
    """Clear shifu context for the current thread."""
    for attr in ("shifu_bid", "shifu_creator_bid"):
        if hasattr(_context_local, attr):
            delattr(_context_local, attr)


def get_shifu_bid() -> Optional[str]:
    """Get current shifu business identifier from context."""
    return getattr(_context_local, "shifu_bid", None)


def get_shifu_creator_bid() -> Optional[str]:
    """Get current shifu creator user business identifier from context."""
    return getattr(_context_local, "shifu_creator_bid", None)


def get_shifu_context_snapshot() -> Dict[str, Any]:
    """
    Capture the current shifu context as a plain dict.

    This snapshot can be passed into a background thread and applied there.
    """
    return {
        "shifu_bid": getattr(_context_local, "shifu_bid", None),
        "shifu_creator_bid": getattr(_context_local, "shifu_creator_bid", None),
    }


def apply_shifu_context_snapshot(snapshot: Optional[Dict[str, Any]]) -> None:
    """
    Apply a previously captured shifu context snapshot to the current thread.

    Args:
        snapshot: Snapshot returned by get_shifu_context_snapshot
    """
    if not snapshot:
        return
    if "shifu_bid" in snapshot:
        _context_local.shifu_bid = snapshot.get("shifu_bid")
    if "shifu_creator_bid" in snapshot:
        _context_local.shifu_creator_bid = snapshot.get("shifu_creator_bid")


def _get_shifu_creator_bid_cached(app, shifu_bid: str) -> Optional[str]:
    """
    Resolve creator bid for a shifu with a lightweight Redis cache.

    The mapping (shifu_bid -> creator_bid) is effectively immutable, so we can
    safely cache it with a short TTL to avoid repeated database lookups.
    """
    if not shifu_bid:
        return None

    try:
        from flaskr.common.cache_provider import cache as cache_provider  # type: ignore
        from flaskr.service.shifu.utils import get_shifu_creator_bid
    except Exception:
        try:
            from flaskr.service.shifu.utils import get_shifu_creator_bid  # type: ignore
        except Exception:
            return None
        return get_shifu_creator_bid(app, shifu_bid)

    try:
        prefix = app.config.get("REDIS_KEY_PREFIX", "ai-shifu")
        cache_key = f"{prefix}:shifu_creator:{shifu_bid}"
        raw = cache_provider.get(cache_key)
        if raw is not None:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return raw or None

        lock_key = f"{cache_key}:lock"
        lock = cache_provider.lock(lock_key, timeout=5, blocking_timeout=1)
        if lock is None:
            creator_bid = get_shifu_creator_bid(app, shifu_bid)
            return creator_bid

        acquired = lock.acquire(blocking=True)
        try:
            raw = cache_provider.get(cache_key)
            if raw is not None:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                return raw or None

            creator_bid = get_shifu_creator_bid(app, shifu_bid)
            value = creator_bid or ""
            # Cache for 1 day as this mapping is effectively immutable
            cache_provider.setex(cache_key, 86400, value)
            return creator_bid
        finally:
            if acquired:
                try:
                    lock.release()
                except Exception:
                    pass
    except Exception:
        try:
            from flaskr.service.shifu.utils import get_shifu_creator_bid  # type: ignore
        except Exception:
            return None
        return get_shifu_creator_bid(app, shifu_bid)


def with_shifu_context(
    resolve_shifu_bid: Optional[Callable[..., Optional[str]]] = None,
) -> Callable:
    """
    Decorator to automatically populate shifu context for a route handler.

    By default it tries to resolve shifu_bid from:
      - path parameters: request.view_args["shifu_bid"]
      - query parameters: request.args["shifu_bid"]
      - JSON body: shifu_bid or course_id

    A custom resolver can be provided via resolve_shifu_bid, which receives
    the wrapped function's *args and **kwargs.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                from flask import request, current_app
            except Exception:
                # If Flask context is not available, just call the function.
                return func(*args, **kwargs)

            shifu_bid: Optional[str] = None
            if resolve_shifu_bid is not None:
                try:
                    shifu_bid = resolve_shifu_bid(*args, **kwargs)
                except Exception:
                    shifu_bid = None

            if not shifu_bid:
                view_args = getattr(request, "view_args", {}) or {}
                shifu_bid = (
                    view_args.get("shifu_bid")
                    or request.args.get("shifu_bid")
                    or request.args.get("shifu-bid")
                )
                if (
                    not shifu_bid
                    and request.method.upper() in {"POST", "PUT", "PATCH"}
                    and request.is_json
                ):
                    payload = request.get_json(silent=True) or {}
                    shifu_bid = payload.get("shifu_bid") or payload.get("course_id")

            if shifu_bid:
                try:
                    app = current_app._get_current_object()
                    creator_bid = _get_shifu_creator_bid_cached(app, shifu_bid)
                    set_shifu_context(shifu_bid, creator_bid)
                except Exception:
                    # Context population failures should not break the endpoint.
                    pass

            return func(*args, **kwargs)

        return wrapper

    return decorator
