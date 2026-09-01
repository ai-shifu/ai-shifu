"""Redis-backed capacity leases for Gemini Live follow-up sessions."""

from __future__ import annotations

import hashlib
import os
import secrets
import socket
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask
    from redis import Redis

LIVE_FOLLOW_UP_GLOBAL_LIMIT = 24
LIVE_FOLLOW_UP_WORKER_LIMIT = 6
LIVE_FOLLOW_UP_USER_LIMIT = 1
LIVE_FOLLOW_UP_LEASE_TTL_SECONDS = 45
LIVE_FOLLOW_UP_LEASE_RENEW_INTERVAL_SECONDS = 15
_ERROR_LEASE_LOST = "lease_lost"
_ERROR_LEASE_NOT_ACQUIRED = "lease_not_acquired"
_ERROR_REDIS_UNAVAILABLE = "redis_unavailable"
_SCOPE_USER = "user"
_SCOPE_WORKER = "worker"

_ACQUIRE_LEASE_SCRIPT = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', ARGV[1])

if redis.call('EXISTS', KEYS[3]) == 1 then
    return -3
end
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[4]) then
    return -1
end
if redis.call('ZCARD', KEYS[2]) >= tonumber(ARGV[5]) then
    return -2
end

local user_acquired = redis.call(
    'SET', KEYS[3], ARGV[3], 'NX', 'EX', ARGV[6]
)
if not user_acquired then
    return -3
end
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[3])
redis.call('ZADD', KEYS[2], ARGV[2], ARGV[3])
return 1
"""

_RENEW_LEASE_SCRIPT = """
local global_score = redis.call('ZSCORE', KEYS[1], ARGV[2])
local worker_score = redis.call('ZSCORE', KEYS[2], ARGV[2])
local user_lease = redis.call('GET', KEYS[3])
if not global_score or not worker_score or user_lease ~= ARGV[2] then
    return 0
end
if tonumber(global_score) <= tonumber(ARGV[1])
    or tonumber(worker_score) <= tonumber(ARGV[1]) then
    return 0
end
redis.call('ZADD', KEYS[1], ARGV[3], ARGV[2])
redis.call('ZADD', KEYS[2], ARGV[3], ARGV[2])
redis.call('EXPIRE', KEYS[3], ARGV[4])
return 1
"""

_RELEASE_LEASE_SCRIPT = """
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('ZREM', KEYS[2], ARGV[1])
if redis.call('GET', KEYS[3]) == ARGV[1] then
    redis.call('DEL', KEYS[3])
    return 1
end
return 0
"""


class LiveFollowUpCapacityError(RuntimeError):
    """Base class for bounded capacity failures."""


class LiveFollowUpCapacityUnavailableError(LiveFollowUpCapacityError):
    """Redis is unavailable, so Live must fail closed."""


class LiveFollowUpCapacityLimitError(LiveFollowUpCapacityError):
    """A configured global, worker, or per-user cap was reached."""

    def __init__(self, scope: str) -> None:
        """Record which bounded capacity scope rejected the session."""
        super().__init__(scope)
        self.scope = scope


class LiveFollowUpCapacityLeaseLostError(LiveFollowUpCapacityError):
    """An expired or replaced lease cannot be renewed."""


@dataclass(frozen=True)
class LiveFollowUpCapacityLease:
    """Opaque ownership token and the scopes it reserves."""

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


def acquire_live_follow_up_capacity(
    app: Flask,
    *,
    user_bid: str,
    worker_id: str | None = None,
    now: float | None = None,
) -> LiveFollowUpCapacityLease:
    """Atomically reserve global, worker, and user capacity."""
    if not user_bid:
        raise LiveFollowUpCapacityLimitError(_SCOPE_USER)
    resolved_worker_id = worker_id or default_live_follow_up_worker_id()
    if not resolved_worker_id:
        raise LiveFollowUpCapacityLimitError(_SCOPE_WORKER)
    lease_id = secrets.token_urlsafe(32)
    current_time = time.time() if now is None else now
    expires_at = current_time + LIVE_FOLLOW_UP_LEASE_TTL_SECONDS
    keys = _lease_keys(
        app,
        user_bid=user_bid,
        worker_id=resolved_worker_id,
    )
    try:
        result = int(
            _require_redis().eval(
                _ACQUIRE_LEASE_SCRIPT,
                3,
                *keys,
                str(current_time),
                str(expires_at),
                lease_id,
                str(LIVE_FOLLOW_UP_GLOBAL_LIMIT),
                str(LIVE_FOLLOW_UP_WORKER_LIMIT),
                str(LIVE_FOLLOW_UP_LEASE_TTL_SECONDS),
            )
        )
    except LiveFollowUpCapacityError:
        raise
    except Exception as exc:
        raise LiveFollowUpCapacityUnavailableError(_ERROR_REDIS_UNAVAILABLE) from exc

    limit_scopes = {-1: "global", -2: "worker", -3: "user"}
    if result in limit_scopes:
        raise LiveFollowUpCapacityLimitError(limit_scopes[result])
    if result != 1:
        raise LiveFollowUpCapacityUnavailableError(_ERROR_LEASE_NOT_ACQUIRED)
    return LiveFollowUpCapacityLease(
        lease_id=lease_id,
        user_bid=user_bid,
        worker_id=resolved_worker_id,
    )


def renew_live_follow_up_capacity(
    app: Flask,
    *,
    lease: LiveFollowUpCapacityLease,
    now: float | None = None,
) -> None:
    """Extend an owned lease by 45 seconds or fail closed."""
    current_time = time.time() if now is None else now
    expires_at = current_time + LIVE_FOLLOW_UP_LEASE_TTL_SECONDS
    keys = _lease_keys(
        app,
        user_bid=lease.user_bid,
        worker_id=lease.worker_id,
    )
    try:
        renewed = bool(
            _require_redis().eval(
                _RENEW_LEASE_SCRIPT,
                3,
                *keys,
                str(current_time),
                lease.lease_id,
                str(expires_at),
                str(LIVE_FOLLOW_UP_LEASE_TTL_SECONDS),
            )
        )
    except LiveFollowUpCapacityError:
        raise
    except Exception as exc:
        raise LiveFollowUpCapacityUnavailableError(_ERROR_REDIS_UNAVAILABLE) from exc
    if not renewed:
        raise LiveFollowUpCapacityLeaseLostError(_ERROR_LEASE_LOST)


def release_live_follow_up_capacity(
    app: Flask,
    *,
    lease: LiveFollowUpCapacityLease,
) -> bool:
    """Release only the caller's lease; never remove a replacement lease."""
    keys = _lease_keys(
        app,
        user_bid=lease.user_bid,
        worker_id=lease.worker_id,
    )
    try:
        return bool(
            _require_redis().eval(
                _RELEASE_LEASE_SCRIPT,
                3,
                *keys,
                lease.lease_id,
            )
        )
    except LiveFollowUpCapacityError:
        raise
    except Exception as exc:
        raise LiveFollowUpCapacityUnavailableError(_ERROR_REDIS_UNAVAILABLE) from exc
