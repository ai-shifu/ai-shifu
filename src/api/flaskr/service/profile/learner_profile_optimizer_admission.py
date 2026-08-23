"""Limit concurrent learner-profile optimization requests."""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from flaskr.service.common.models import raise_error

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask
    from redis import Redis

IN_FLIGHT_TTL_SECONDS = 360

_ACQUIRE_ADMISSION_SCRIPT = """
local acquired = redis.call('set', KEYS[1], ARGV[1], 'NX', 'EX', ARGV[2])
if acquired then
    return 1
end
return 0
"""

_RELEASE_ADMISSION_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


@dataclass(frozen=True)
class _AdmissionLease:
    backend: str
    token: str
    key: str


@dataclass(frozen=True)
class _LocalLease:
    token: str
    expires_at: float


class _AdmissionDeniedError(Exception):
    pass


_local_lock = threading.RLock()
_local_in_flight_state: dict[str, _LocalLease] = {}


def _scope_digest(value: str) -> str:
    normalized = str(value or "").strip() or "unknown"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _admission_key(app: Flask, *, user_id: str) -> str:
    prefix = str(app.config.get("REDIS_KEY_PREFIX", "ai-shifu:") or "ai-shifu:")
    return (
        f"{prefix.rstrip(':')}:learner-profile-optimize:in-flight:user:"
        f"{_scope_digest(user_id)}"
    )


def _redis_client() -> Redis | None:
    from flaskr.dao import get_redis_client

    return get_redis_client()


def _acquire_redis_admission(*, key: str, token: str) -> _AdmissionLease | None:
    client = _redis_client()
    if client is None:
        return None

    acquired = bool(
        client.eval(
            _ACQUIRE_ADMISSION_SCRIPT,
            1,
            key,
            token,
            str(IN_FLIGHT_TTL_SECONDS),
        )
    )
    if not acquired:
        raise _AdmissionDeniedError
    return _AdmissionLease(backend="redis", token=token, key=key)


def _acquire_local_admission(*, key: str, token: str) -> _AdmissionLease:
    now = time.monotonic()
    with _local_lock:
        existing = _local_in_flight_state.get(key)
        if existing is not None and existing.expires_at > now:
            raise _AdmissionDeniedError
        _local_in_flight_state[key] = _LocalLease(
            token=token,
            expires_at=now + IN_FLIGHT_TTL_SECONDS,
        )
    return _AdmissionLease(backend="local", token=token, key=key)


def _acquire_admission(app: Flask, *, user_id: str) -> _AdmissionLease:
    key = _admission_key(app, user_id=user_id)
    token = uuid.uuid4().hex
    try:
        lease = _acquire_redis_admission(key=key, token=token)
        if lease is not None:
            return lease
    except _AdmissionDeniedError:
        raise
    except Exception as exc:
        app.logger.warning(
            "Learner profile optimization Redis admission failed; "
            "denying request | error_type=%s",
            type(exc).__name__,
        )
        raise _AdmissionDeniedError from exc
    return _acquire_local_admission(key=key, token=token)


def _release_local_admission(lease: _AdmissionLease) -> None:
    with _local_lock:
        current = _local_in_flight_state.get(lease.key)
        if current is not None and current.token == lease.token:
            _local_in_flight_state.pop(lease.key, None)


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
            1,
            lease.key,
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
    app: Flask, *, user_id: str
) -> Iterator[None]:
    """Allow only one in-flight optimization for each learner."""
    try:
        lease = _acquire_admission(app, user_id=user_id)
    except _AdmissionDeniedError:
        app.logger.warning("Learner profile optimization already in flight")
        raise_error("server.profile.learnerProfileOptimizationRateLimited")

    try:
        yield
    finally:
        _release_admission(app, lease)
