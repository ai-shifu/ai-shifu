"""Redis binding for browser-direct Gemini Live follow-up sessions."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from .live_follow_up_capacity import (
    LIVE_FOLLOW_UP_LEASE_TTL_SECONDS,
    LiveFollowUpCapacityLease,
)

if TYPE_CHECKING:
    from flask import Flask
    from redis import Redis

LIVE_FOLLOW_UP_SESSION_STORE_TTL_SECONDS = LIVE_FOLLOW_UP_LEASE_TTL_SECONDS
_SESSION_RECORD_VERSION = 1
_ERROR_INVALID_SESSION = "invalid_session"
_ERROR_REDIS_UNAVAILABLE = "redis_unavailable"
_ERROR_SESSION_EXPIRED = "session_expired"
_ERROR_SESSION_NOT_STORED = "session_not_stored"

_TOUCH_SESSION_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return 0
end
redis.call('EXPIRE', KEYS[1], ARGV[1])
return 1
"""

_CONSUME_SESSION_SCRIPT = """
local payload = redis.call('GET', KEYS[1])
if payload then
    redis.call('DEL', KEYS[1])
end
return payload
"""


class LiveFollowUpSessionStoreError(RuntimeError):
    """Base class for bounded browser-direct session failures."""


class LiveFollowUpSessionStoreUnavailableError(LiveFollowUpSessionStoreError):
    """Redis could not safely read or mutate the session binding."""


class LiveFollowUpSessionRejectedError(LiveFollowUpSessionStoreError):
    """The session is absent, expired, malformed, or bound elsewhere."""


@dataclass(frozen=True)
class LiveFollowUpSessionBinding:
    """Trusted values bound to one browser-direct Gemini Live session."""

    session_bid: str
    user_bid: str
    shifu_bid: str
    outline_bid: str
    anchor_element_bid: str
    progress_record_bid: str
    preview_mode: bool
    origin: str
    model: str
    voice_name: str
    language: str
    learning_mode: str
    expires_at_epoch: float


@dataclass(frozen=True)
class StoredLiveFollowUpSession:
    """Session binding plus the Redis capacity lease owned by it."""

    binding: LiveFollowUpSessionBinding
    lease: LiveFollowUpCapacityLease


def _redis_client() -> Redis | None:
    from flaskr.dao import get_redis_client

    return get_redis_client()


def _require_redis() -> Redis:
    client = _redis_client()
    if client is None:
        raise LiveFollowUpSessionStoreUnavailableError(_ERROR_REDIS_UNAVAILABLE)
    return client


def _scope_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _session_key(app: Flask, session_bid: str) -> str:
    prefix = str(app.config.get("REDIS_KEY_PREFIX", "ai-shifu:") or "ai-shifu:")
    return f"{prefix.rstrip(':')}:live-follow-up:session:{_scope_digest(session_bid)}"


def _validate_binding(binding: LiveFollowUpSessionBinding) -> None:
    strings = (
        binding.session_bid,
        binding.user_bid,
        binding.shifu_bid,
        binding.outline_bid,
        binding.anchor_element_bid,
        binding.progress_record_bid,
        binding.origin,
        binding.model,
        binding.voice_name,
        binding.language,
        binding.learning_mode,
    )
    if any(not isinstance(value, str) or not value for value in strings):
        raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION)
    if type(binding.preview_mode) is not bool:
        raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION)
    if not isinstance(binding.expires_at_epoch, (int, float)) or not math.isfinite(
        binding.expires_at_epoch
    ):
        raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION)


def _serialize_session(session: StoredLiveFollowUpSession) -> str:
    _validate_binding(session.binding)
    return json.dumps(
        {
            "version": _SESSION_RECORD_VERSION,
            "binding": asdict(session.binding),
            "lease": asdict(session.lease),
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _decode_session(raw: bytes | str) -> StoredLiveFollowUpSession:
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        record: Any = json.loads(text)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION) from exc
    if not isinstance(record, dict) or record.get("version") != 1:
        raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION)
    try:
        binding = LiveFollowUpSessionBinding(**record["binding"])
        lease = LiveFollowUpCapacityLease(**record["lease"])
    except (KeyError, TypeError) as exc:
        raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION) from exc
    _validate_binding(binding)
    if not lease.lease_id or not lease.user_bid or not lease.worker_id:
        raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION)
    return StoredLiveFollowUpSession(binding=binding, lease=lease)


def store_live_follow_up_session(
    app: Flask,
    *,
    session: StoredLiveFollowUpSession,
) -> None:
    """Store one unique direct-session binding or fail closed."""
    payload = _serialize_session(session)
    try:
        stored = _require_redis().set(
            _session_key(app, session.binding.session_bid),
            payload,
            ex=LIVE_FOLLOW_UP_SESSION_STORE_TTL_SECONDS,
            nx=True,
        )
    except LiveFollowUpSessionStoreError:
        raise
    except Exception as exc:
        raise LiveFollowUpSessionStoreUnavailableError(
            _ERROR_REDIS_UNAVAILABLE
        ) from exc
    if not stored:
        raise LiveFollowUpSessionStoreUnavailableError(_ERROR_SESSION_NOT_STORED)


def load_live_follow_up_session(
    app: Flask,
    *,
    session_bid: str,
    current_time: float | None = None,
) -> StoredLiveFollowUpSession:
    """Load an active direct-session binding without extending its lease."""
    if not session_bid:
        raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION)
    try:
        raw = _require_redis().get(_session_key(app, session_bid))
    except LiveFollowUpSessionStoreError:
        raise
    except Exception as exc:
        raise LiveFollowUpSessionStoreUnavailableError(
            _ERROR_REDIS_UNAVAILABLE
        ) from exc
    if raw is None:
        raise LiveFollowUpSessionRejectedError(_ERROR_SESSION_EXPIRED)
    session = _decode_session(raw)
    if session.binding.session_bid != session_bid:
        raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION)
    now = time.time() if current_time is None else current_time
    if session.binding.expires_at_epoch <= now:
        raise LiveFollowUpSessionRejectedError(_ERROR_SESSION_EXPIRED)
    return session


def touch_live_follow_up_session(app: Flask, *, session_bid: str) -> None:
    """Extend the Redis binding only after its capacity lease was renewed."""
    try:
        touched = bool(
            _require_redis().eval(
                _TOUCH_SESSION_SCRIPT,
                1,
                _session_key(app, session_bid),
                str(LIVE_FOLLOW_UP_SESSION_STORE_TTL_SECONDS),
            )
        )
    except LiveFollowUpSessionStoreError:
        raise
    except Exception as exc:
        raise LiveFollowUpSessionStoreUnavailableError(
            _ERROR_REDIS_UNAVAILABLE
        ) from exc
    if not touched:
        raise LiveFollowUpSessionRejectedError(_ERROR_SESSION_EXPIRED)


def consume_live_follow_up_session(
    app: Flask,
    *,
    session_bid: str,
) -> StoredLiveFollowUpSession:
    """Atomically remove and return one direct-session binding."""
    try:
        raw = _require_redis().eval(
            _CONSUME_SESSION_SCRIPT,
            1,
            _session_key(app, session_bid),
        )
    except LiveFollowUpSessionStoreError:
        raise
    except Exception as exc:
        raise LiveFollowUpSessionStoreUnavailableError(
            _ERROR_REDIS_UNAVAILABLE
        ) from exc
    if raw is None:
        raise LiveFollowUpSessionRejectedError(_ERROR_SESSION_EXPIRED)
    return _decode_session(raw)
