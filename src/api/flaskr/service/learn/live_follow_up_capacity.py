"""Shared Redis key layout and lease types for Gemini Live capacity."""

from __future__ import annotations

import hashlib
import os
import socket
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask
    from redis import Redis

_ERROR_REDIS_UNAVAILABLE = "redis_unavailable"


class LiveFollowUpCapacityError(RuntimeError):
    """Base class for bounded capacity failures."""


class LiveFollowUpCapacityUnavailableError(LiveFollowUpCapacityError):
    """Redis is unavailable, so Live must fail closed."""


@dataclass(frozen=True)
class LiveFollowUpCapacityLease:
    """Opaque ownership token for one undisclosed or live credential."""

    lease_id: str
    user_bid: str
    worker_id: str


def _redis_client() -> Redis | None:
    from flaskr.dao import get_redis_client

    return get_redis_client()


def default_live_follow_up_worker_id() -> str:
    """Return the stable identifier for the current Gunicorn worker process."""
    return f"{socket.gethostname()}:{os.getpid()}"


def _scope_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _key_prefix(app: Flask) -> str:
    configured = str(app.config.get("REDIS_KEY_PREFIX", "ai-shifu:") or "ai-shifu:")
    return f"{configured.rstrip(':')}:live-follow-up:capacity"


def _lease_keys(app: Flask, *, user_bid: str, worker_id: str) -> tuple[str, str, str]:
    prefix = _key_prefix(app)
    return (
        f"{prefix}:global",
        f"{prefix}:worker:{_scope_digest(worker_id)}",
        f"{prefix}:user:{_scope_digest(user_bid)}",
    )


def _require_redis() -> Redis:
    client = _redis_client()
    if client is None:
        raise LiveFollowUpCapacityUnavailableError(_ERROR_REDIS_UNAVAILABLE)
    return client
