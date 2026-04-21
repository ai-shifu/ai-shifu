"""Shared RPM queue gate for TTS provider calls."""

from __future__ import annotations

import hashlib
import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from flaskr.common.log import AppLoggerProxy


logger = AppLoggerProxy(logging.getLogger(__name__))

_LOCAL_STATE: dict[str, float] = {}
_LOCAL_LOCK = threading.RLock()
_FALLBACK_WARNING_LOCK = threading.Lock()
_FALLBACK_WARNING_KEYS: set[str] = set()


class TTSRpmQueueTimeout(TimeoutError):
    """Raised when a TTS request cannot enter the RPM queue fast enough."""


@dataclass(frozen=True)
class TTSRpmGateResult:
    """Queue wait metadata returned after a successful gate acquisition."""

    waited_seconds: float
    scheduled_at: float


def acquire_tts_rpm_slot(
    *,
    provider: str,
    api_key: str,
    rpm_limit: int | float,
    max_wait_seconds: int | float,
    now_fn: Callable[[], float] = time.time,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> TTSRpmGateResult:
    """Reserve one smoothed RPM slot for a provider/API-key pair.

    The Redis path coordinates all workers. When Redis is not configured or is
    unreachable, the local process path still protects a single worker so the
    request can continue with reduced coordination guarantees.
    """

    limit = float(rpm_limit or 0)
    if limit <= 0:
        now = now_fn()
        return TTSRpmGateResult(waited_seconds=0.0, scheduled_at=now)

    wait_cap = max(float(max_wait_seconds or 0), 0.0)
    interval = 60.0 / limit
    scope_key = _scope_key(provider=provider, api_key=api_key)
    start = now_fn()
    deadline = start + wait_cap

    try:
        result = _acquire_redis_slot(
            scope_key=scope_key,
            interval=interval,
            deadline=deadline,
            max_wait_seconds=wait_cap,
            now_fn=now_fn,
        )
    except TTSRpmQueueTimeout:
        raise
    except Exception as exc:
        _warn_redis_fallback_once(provider=provider, scope_key=scope_key, exc=exc)
        result = _acquire_local_slot(
            scope_key=scope_key,
            interval=interval,
            deadline=deadline,
            now_fn=now_fn,
        )

    sleep_seconds = max(result.scheduled_at - now_fn(), 0.0)
    if sleep_seconds > 0:
        sleep_fn(sleep_seconds)

    return TTSRpmGateResult(
        waited_seconds=max(result.scheduled_at - start, 0.0),
        scheduled_at=result.scheduled_at,
    )


def _acquire_redis_slot(
    *,
    scope_key: str,
    interval: float,
    deadline: float,
    max_wait_seconds: float,
    now_fn: Callable[[], float],
) -> TTSRpmGateResult:
    redis_client = _get_redis_client()
    next_key = f"tts:rpm_gate:{scope_key}:next_available_at"
    lock_key = f"tts:rpm_gate:{scope_key}:lock"
    lock_timeout = max(math.ceil(max_wait_seconds + 5), 5)
    lock = redis_client.lock(
        lock_key,
        timeout=lock_timeout,
        blocking_timeout=max_wait_seconds,
    )
    acquired = lock.acquire(blocking=True, blocking_timeout=max_wait_seconds)
    if not acquired:
        raise TTSRpmQueueTimeout(
            f"TTS RPM queue lock timed out after {max_wait_seconds:.2f}s"
        )

    try:
        now = now_fn()
        raw_next = redis_client.get(next_key)
        next_available_at = _parse_timestamp(raw_next, default=now)
        scheduled_at = max(now, next_available_at)
        if scheduled_at > deadline:
            raise TTSRpmQueueTimeout(
                f"TTS RPM queue wait exceeded {max_wait_seconds:.2f}s"
            )

        ttl_seconds = max(math.ceil(interval * 4 + max_wait_seconds + 60), 120)
        redis_client.set(next_key, f"{scheduled_at + interval:.6f}", ex=ttl_seconds)
        return TTSRpmGateResult(
            waited_seconds=max(scheduled_at - now, 0.0),
            scheduled_at=scheduled_at,
        )
    finally:
        try:
            lock.release()
        except Exception:
            logger.debug("Failed to release TTS RPM Redis lock", exc_info=True)


def _acquire_local_slot(
    *,
    scope_key: str,
    interval: float,
    deadline: float,
    now_fn: Callable[[], float],
) -> TTSRpmGateResult:
    with _LOCAL_LOCK:
        now = now_fn()
        scheduled_at = max(now, _LOCAL_STATE.get(scope_key, now))
        if scheduled_at > deadline:
            raise TTSRpmQueueTimeout("TTS RPM local queue wait exceeded limit")

        _LOCAL_STATE[scope_key] = scheduled_at + interval
        return TTSRpmGateResult(
            waited_seconds=max(scheduled_at - now, 0.0),
            scheduled_at=scheduled_at,
        )


def _get_redis_client():
    from flaskr.dao import redis_client

    if redis_client is None:
        raise RuntimeError("Redis is not configured")
    return redis_client


def _scope_key(*, provider: str, api_key: str) -> str:
    normalized_provider = (provider or "default").strip().lower() or "default"
    key_hash = hashlib.sha256((api_key or "").encode("utf-8")).hexdigest()[:24]
    return f"{normalized_provider}:{key_hash}"


def _parse_timestamp(
    raw: Optional[bytes | str | float | int], *, default: float
) -> float:
    if raw is None:
        return default
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return value


def _warn_redis_fallback_once(*, provider: str, scope_key: str, exc: Exception) -> None:
    with _FALLBACK_WARNING_LOCK:
        if scope_key in _FALLBACK_WARNING_KEYS:
            return
        _FALLBACK_WARNING_KEYS.add(scope_key)

    logger.warning(
        "Redis unavailable for TTS RPM gate; using process-local queue for provider=%s: %s",
        (provider or "default").strip().lower() or "default",
        exc,
    )
