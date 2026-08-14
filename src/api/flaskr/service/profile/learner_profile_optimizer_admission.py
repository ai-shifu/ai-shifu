from __future__ import annotations

import hashlib
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from flask import Flask
from flaskr.service.common.models import raise_error

LEARNER_PROFILE_OPTIMIZE_RATE_WINDOW_SECONDS = 60
DEFAULT_IN_FLIGHT_TTL_SECONDS = 360

DEFAULT_USER_RATE_LIMIT = 5
DEFAULT_IP_RATE_LIMIT = 20
DEFAULT_USER_CONCURRENCY = 1
DEFAULT_IP_CONCURRENCY = 4

_ACQUIRE_ADMISSION_SCRIPT = """
local user_rate = tonumber(redis.call('get', KEYS[1]) or '0')
local ip_rate = tonumber(redis.call('get', KEYS[2]) or '0')
local redis_time = redis.call('time')
local now_ms = tonumber(redis_time[1]) * 1000 + math.floor(tonumber(redis_time[2]) / 1000)
redis.call('zremrangebyscore', KEYS[3], '-inf', now_ms)
redis.call('zremrangebyscore', KEYS[4], '-inf', now_ms)
local user_in_flight = tonumber(redis.call('zcard', KEYS[3]))
local ip_in_flight = tonumber(redis.call('zcard', KEYS[4]))

if user_rate >= tonumber(ARGV[1]) then
    return 1
end
if ip_rate >= tonumber(ARGV[2]) then
    return 2
end
if user_in_flight >= tonumber(ARGV[3]) then
    return 3
end
if ip_in_flight >= tonumber(ARGV[4]) then
    return 4
end

local next_user_rate = redis.call('incr', KEYS[1])
if next_user_rate == 1 then
    redis.call('expire', KEYS[1], tonumber(ARGV[5]))
end
local next_ip_rate = redis.call('incr', KEYS[2])
if next_ip_rate == 1 then
    redis.call('expire', KEYS[2], tonumber(ARGV[5]))
end

local in_flight_ttl = tonumber(ARGV[6])
local expires_at_ms = now_ms + in_flight_ttl * 1000
redis.call('zadd', KEYS[3], expires_at_ms, ARGV[7])
redis.call('zadd', KEYS[4], expires_at_ms, ARGV[7])
redis.call('expire', KEYS[3], in_flight_ttl + 1)
redis.call('expire', KEYS[4], in_flight_ttl + 1)
return 0
"""

_RELEASE_ADMISSION_SCRIPT = """
for index = 1, #KEYS do
    redis.call('zrem', KEYS[index], ARGV[1])
end
return 1
"""

_DENIAL_REASONS = {
    1: "user_rate",
    2: "ip_rate",
    3: "user_in_flight",
    4: "ip_in_flight",
}


@dataclass(frozen=True)
class _AdmissionLease:
    backend: str
    token: str
    user_in_flight_key: str
    ip_in_flight_key: str


@dataclass
class _LocalCounter:
    count: int
    expires_at: float


class _AdmissionDenied(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


_local_lock = threading.RLock()
_local_rate_state: dict[str, _LocalCounter] = {}
_local_in_flight_state: dict[str, dict[str, float]] = {}


def _positive_config_int(app: Flask, key: str, default: int) -> int:
    try:
        configured = int(app.config.get(key, default))
    except (TypeError, ValueError):
        return default
    return configured if configured > 0 else default


def _scope_digest(value: str) -> str:
    normalized = str(value or "").strip() or "unknown"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _admission_keys(app: Flask, *, user_id: str, client_ip: str) -> tuple[str, ...]:
    prefix = str(app.config.get("REDIS_KEY_PREFIX", "ai-shifu:") or "ai-shifu:")
    prefix = prefix.rstrip(":")
    user_scope = _scope_digest(user_id)
    ip_scope = _scope_digest(client_ip)
    base = f"{prefix}:learner-profile-optimize"
    return (
        f"{base}:rate:user:{user_scope}",
        f"{base}:rate:ip:{ip_scope}",
        f"{base}:in-flight:user:{user_scope}",
        f"{base}:in-flight:ip:{ip_scope}",
    )


def _limits(app: Flask) -> tuple[int, int, int, int]:
    return (
        _positive_config_int(
            app,
            "LEARNER_PROFILE_OPTIMIZE_USER_RATE_LIMIT",
            DEFAULT_USER_RATE_LIMIT,
        ),
        _positive_config_int(
            app,
            "LEARNER_PROFILE_OPTIMIZE_IP_RATE_LIMIT",
            DEFAULT_IP_RATE_LIMIT,
        ),
        _positive_config_int(
            app,
            "LEARNER_PROFILE_OPTIMIZE_USER_CONCURRENCY",
            DEFAULT_USER_CONCURRENCY,
        ),
        _positive_config_int(
            app,
            "LEARNER_PROFILE_OPTIMIZE_IP_CONCURRENCY",
            DEFAULT_IP_CONCURRENCY,
        ),
    )


def _in_flight_ttl_seconds(app: Flask) -> int:
    return _positive_config_int(
        app,
        "LEARNER_PROFILE_OPTIMIZE_IN_FLIGHT_TTL_SECONDS",
        DEFAULT_IN_FLIGHT_TTL_SECONDS,
    )


def _redis_client():
    from flaskr.dao import redis_client

    return redis_client


def _acquire_redis_admission(
    app: Flask,
    *,
    keys: tuple[str, ...],
    limits: tuple[int, int, int, int],
) -> _AdmissionLease | None:
    client = _redis_client()
    if client is None:
        return None

    token = uuid.uuid4().hex
    result = int(
        client.eval(
            _ACQUIRE_ADMISSION_SCRIPT,
            4,
            *keys,
            *[str(limit) for limit in limits],
            str(LEARNER_PROFILE_OPTIMIZE_RATE_WINDOW_SECONDS),
            str(_in_flight_ttl_seconds(app)),
            token,
        )
    )
    if result:
        raise _AdmissionDenied(_DENIAL_REASONS.get(result, "unknown"))
    return _AdmissionLease(
        backend="redis",
        token=token,
        user_in_flight_key=keys[2],
        ip_in_flight_key=keys[3],
    )


def _purge_expired_local_counters(
    counters: dict[str, _LocalCounter], *, now: float
) -> None:
    expired = [key for key, counter in counters.items() if counter.expires_at <= now]
    for key in expired:
        counters.pop(key, None)


def _local_count(counters: dict[str, _LocalCounter], key: str) -> int:
    counter = counters.get(key)
    return counter.count if counter is not None else 0


def _purge_expired_local_leases(*, now: float) -> None:
    for key, leases in list(_local_in_flight_state.items()):
        active = {
            token: expires_at
            for token, expires_at in leases.items()
            if expires_at > now
        }
        if active:
            _local_in_flight_state[key] = active
        else:
            _local_in_flight_state.pop(key, None)


def _increment_local_counter(
    counters: dict[str, _LocalCounter],
    key: str,
    *,
    now: float,
    ttl_seconds: int,
    refresh_ttl: bool,
) -> None:
    counter = counters.get(key)
    if counter is None:
        counters[key] = _LocalCounter(count=1, expires_at=now + ttl_seconds)
        return
    counter.count += 1
    if refresh_ttl:
        counter.expires_at = now + ttl_seconds


def _acquire_local_admission(
    *,
    keys: tuple[str, ...],
    limits: tuple[int, int, int, int],
    in_flight_ttl_seconds: int,
) -> _AdmissionLease:
    now = time.monotonic()
    token = uuid.uuid4().hex
    with _local_lock:
        _purge_expired_local_counters(_local_rate_state, now=now)
        _purge_expired_local_leases(now=now)
        counts = (
            _local_count(_local_rate_state, keys[0]),
            _local_count(_local_rate_state, keys[1]),
            len(_local_in_flight_state.get(keys[2], {})),
            len(_local_in_flight_state.get(keys[3], {})),
        )
        for index, (count, limit) in enumerate(zip(counts, limits), start=1):
            if count >= limit:
                raise _AdmissionDenied(_DENIAL_REASONS[index])

        for key in keys[:2]:
            _increment_local_counter(
                _local_rate_state,
                key,
                now=now,
                ttl_seconds=LEARNER_PROFILE_OPTIMIZE_RATE_WINDOW_SECONDS,
                refresh_ttl=False,
            )
        expires_at = now + in_flight_ttl_seconds
        for key in keys[2:]:
            _local_in_flight_state.setdefault(key, {})[token] = expires_at

    return _AdmissionLease(
        backend="local",
        token=token,
        user_in_flight_key=keys[2],
        ip_in_flight_key=keys[3],
    )


def _acquire_admission(app: Flask, *, user_id: str, client_ip: str) -> _AdmissionLease:
    keys = _admission_keys(app, user_id=user_id, client_ip=client_ip)
    limits = _limits(app)
    try:
        lease = _acquire_redis_admission(app, keys=keys, limits=limits)
        if lease is not None:
            return lease
    except _AdmissionDenied:
        raise
    except Exception as exc:
        app.logger.warning(
            "Learner profile optimization Redis admission failed; "
            "denying request | error_type=%s",
            type(exc).__name__,
        )
        raise _AdmissionDenied("admission_unavailable") from exc
    return _acquire_local_admission(
        keys=keys,
        limits=limits,
        in_flight_ttl_seconds=_in_flight_ttl_seconds(app),
    )


def _release_local_admission(lease: _AdmissionLease) -> None:
    with _local_lock:
        for key in (lease.user_in_flight_key, lease.ip_in_flight_key):
            leases = _local_in_flight_state.get(key)
            if leases is None:
                continue
            leases.pop(lease.token, None)
            if not leases:
                _local_in_flight_state.pop(key, None)


def _release_admission(app: Flask, lease: _AdmissionLease) -> None:
    if lease.backend == "local":
        _release_local_admission(lease)
        return

    try:
        client = _redis_client()
        if client is None:
            return
        client.eval(
            _RELEASE_ADMISSION_SCRIPT,
            2,
            lease.user_in_flight_key,
            lease.ip_in_flight_key,
            lease.token,
        )
    except Exception as exc:
        app.logger.warning(
            "Learner profile optimization Redis admission release failed | "
            "error_type=%s",
            type(exc).__name__,
        )


@contextmanager
def learner_profile_optimization_admission(
    app: Flask, *, user_id: str, client_ip: str
) -> Iterator[None]:
    """Bound per-user and per-IP optimizer cost without storing business state."""

    try:
        lease = _acquire_admission(app, user_id=user_id, client_ip=client_ip)
    except _AdmissionDenied as exc:
        app.logger.warning(
            "Learner profile optimization admission denied | reason=%s",
            exc.reason,
        )
        raise_error("server.profile.learnerProfileOptimizationRateLimited")

    try:
        yield
    finally:
        _release_admission(app, lease)
