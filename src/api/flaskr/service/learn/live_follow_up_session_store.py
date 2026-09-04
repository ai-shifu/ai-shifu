"""Redis binding for browser-direct Gemini Live follow-up sessions."""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from .live_follow_up_capacity import LiveFollowUpCapacityLease

if TYPE_CHECKING:
    from flask import Flask
    from redis import Redis

LIVE_FOLLOW_UP_SESSION_STORE_TTL_SECONDS = 45
LIVE_FOLLOW_UP_SESSION_HEARTBEAT_INTERVAL_SECONDS = 15
LIVE_FOLLOW_UP_SESSION_FINALIZATION_GRACE_SECONDS = 30
# Bounded in-flight retention, renewed before each accepted finalization write.
LIVE_FOLLOW_UP_SESSION_FINALIZATION_LEASE_SECONDS = 300
LIVE_FOLLOW_UP_MAX_TURNS = 200
_SESSION_RECORD_VERSION = 2
_ERROR_INVALID_SESSION = "invalid_session"
_ERROR_REDIS_UNAVAILABLE = "redis_unavailable"
_ERROR_SESSION_EXPIRED = "session_expired"
_ERROR_SESSION_NOT_STORED = "session_not_stored"
_ERROR_TURN_REJECTED = "turn_rejected"

_TOUCH_SESSION_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return 0
end
-- A concurrent heartbeat must not shorten an accepted finalization lease.
if redis.call('TTL', KEYS[1]) < tonumber(ARGV[1]) then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return 1
"""

_CONSUME_SESSION_SCRIPT = """
local payload = redis.call('GET', KEYS[1])
if payload then
    redis.call('DEL', KEYS[1])
end
return payload
"""

_RESERVE_TURN_SCRIPT = """
-- live_follow_up_reserve_turn
local payload = redis.call('GET', KEYS[1])
if not payload then
    return 0
end
local decoded, record = pcall(cjson.decode, payload)
if not decoded or type(record) ~= 'table' or record['version'] ~= 2 then
    return -1
end
local state = record['turn_state']
if type(state) ~= 'table' then
    return -1
end
local last_index = tonumber(state['last_committed_index'])
local requested_index = tonumber(ARGV[1])
local max_turns = tonumber(ARGV[3])
if not last_index or not requested_index or not max_turns
    or last_index < 0 or last_index % 1 ~= 0
    or requested_index < 1 or requested_index % 1 ~= 0 then
    return -1
end
local pending_index = state['pending_index']
if pending_index ~= nil and pending_index ~= cjson.null then
    -- Recovery is only enabled while holding the connection-scoped database
    -- lock, which proves that the previous writer has exited.
    if ARGV[4] ~= '1' or tonumber(pending_index) ~= requested_index then
        return -2
    end
end
if requested_index ~= last_index + 1 or requested_index > max_turns then
    return -2
end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 1 then
    return 0
end
state['pending_index'] = requested_index
state['pending_claim'] = ARGV[2]
redis.call('SET', KEYS[1], cjson.encode(record), 'EX', ttl)
return 1
"""

_COMMIT_TURN_SCRIPT = """
-- live_follow_up_commit_turn
local payload = redis.call('GET', KEYS[1])
if not payload then
    return 0
end
local decoded, record = pcall(cjson.decode, payload)
if not decoded or type(record) ~= 'table' or record['version'] ~= 2 then
    return -1
end
local state = record['turn_state']
if type(state) ~= 'table'
    or tonumber(state['pending_index']) ~= tonumber(ARGV[1])
    or state['pending_claim'] ~= ARGV[2] then
    return -2
end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 1 then
    return 0
end
state['last_committed_index'] = tonumber(ARGV[1])
state['pending_index'] = cjson.null
state['pending_claim'] = ''
redis.call('SET', KEYS[1], cjson.encode(record), 'EX', ttl)
return 1
"""

_RELEASE_TURN_SCRIPT = """
-- live_follow_up_release_turn
local payload = redis.call('GET', KEYS[1])
if not payload then
    return 0
end
local decoded, record = pcall(cjson.decode, payload)
if not decoded or type(record) ~= 'table' or record['version'] ~= 2 then
    return -1
end
local state = record['turn_state']
if type(state) ~= 'table'
    or tonumber(state['pending_index']) ~= tonumber(ARGV[1])
    or state['pending_claim'] ~= ARGV[2] then
    return -2
end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 1 then
    return 0
end
state['pending_index'] = cjson.null
state['pending_claim'] = ''
redis.call('SET', KEYS[1], cjson.encode(record), 'EX', ttl)
return 1
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
class LiveFollowUpTurnState:
    """Server-owned ordering and in-flight reservation for turn reports."""

    last_committed_index: int = 0
    pending_index: int | None = None
    pending_claim: str = ""


@dataclass(frozen=True)
class StoredLiveFollowUpSession:
    """Session binding plus its independent Redis capacity reservation."""

    binding: LiveFollowUpSessionBinding
    lease: LiveFollowUpCapacityLease
    turn_state: LiveFollowUpTurnState = field(default_factory=LiveFollowUpTurnState)


@dataclass(frozen=True)
class LiveFollowUpTurnReservation:
    """Opaque server claim for one ordered Live turn persistence attempt."""

    session_bid: str
    turn_index: int
    claim: str


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


def _validate_turn_state(state: LiveFollowUpTurnState) -> None:
    if (
        type(state.last_committed_index) is not int
        or not 0 <= state.last_committed_index <= LIVE_FOLLOW_UP_MAX_TURNS
        or not isinstance(state.pending_claim, str)
        or len(state.pending_claim) > 128
    ):
        raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION)
    if state.pending_index is None:
        if state.pending_claim:
            raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION)
        return
    if (
        type(state.pending_index) is not int
        or state.pending_index != state.last_committed_index + 1
        or state.pending_index > LIVE_FOLLOW_UP_MAX_TURNS
        or not state.pending_claim
    ):
        raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION)


def _serialize_session(session: StoredLiveFollowUpSession) -> str:
    _validate_binding(session.binding)
    _validate_turn_state(session.turn_state)
    return json.dumps(
        {
            "version": _SESSION_RECORD_VERSION,
            "binding": asdict(session.binding),
            "lease": asdict(session.lease),
            "turn_state": asdict(session.turn_state),
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
    if not isinstance(record, dict) or record.get("version") != _SESSION_RECORD_VERSION:
        raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION)
    try:
        binding = LiveFollowUpSessionBinding(**record["binding"])
        lease = LiveFollowUpCapacityLease(**record["lease"])
        turn_state = LiveFollowUpTurnState(**record["turn_state"])
    except (KeyError, TypeError) as exc:
        raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION) from exc
    _validate_binding(binding)
    _validate_turn_state(turn_state)
    if not lease.lease_id or not lease.user_bid or not lease.worker_id:
        raise LiveFollowUpSessionRejectedError(_ERROR_INVALID_SESSION)
    return StoredLiveFollowUpSession(
        binding=binding,
        lease=lease,
        turn_state=turn_state,
    )


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
    allow_finalization: bool = False,
) -> StoredLiveFollowUpSession:
    """Load a binding, optionally allowing bounded post-expiry finalization."""
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
    deadline = session.binding.expires_at_epoch
    if allow_finalization:
        deadline += LIVE_FOLLOW_UP_SESSION_FINALIZATION_GRACE_SECONDS
    if deadline <= now:
        raise LiveFollowUpSessionRejectedError(_ERROR_SESSION_EXPIRED)
    return session


def touch_live_follow_up_session(
    app: Flask, *, session_bid: str, finalizing: bool = False
) -> None:
    """Extend binding retention, never the absolute request-admission deadline."""
    ttl = (
        LIVE_FOLLOW_UP_SESSION_FINALIZATION_LEASE_SECONDS
        if finalizing
        else LIVE_FOLLOW_UP_SESSION_STORE_TTL_SECONDS
    )
    try:
        touched = bool(
            _require_redis().eval(
                _TOUCH_SESSION_SCRIPT,
                1,
                _session_key(app, session_bid),
                str(ttl),
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


def _run_turn_reservation_script(
    app: Flask,
    *,
    script: str,
    reservation: LiveFollowUpTurnReservation,
    extra_args: tuple[str, ...] = (),
) -> int:
    try:
        result = _require_redis().eval(
            script,
            1,
            _session_key(app, reservation.session_bid),
            str(reservation.turn_index),
            reservation.claim,
            *extra_args,
        )
    except LiveFollowUpSessionStoreError:
        raise
    except Exception as exc:
        raise LiveFollowUpSessionStoreUnavailableError(
            _ERROR_REDIS_UNAVAILABLE
        ) from exc
    try:
        return int(result)
    except (TypeError, ValueError) as exc:
        raise LiveFollowUpSessionStoreUnavailableError(
            _ERROR_REDIS_UNAVAILABLE
        ) from exc


def reserve_live_follow_up_turn(
    app: Flask,
    *,
    session_bid: str,
    turn_index: int,
    recover_pending: bool = False,
) -> LiveFollowUpTurnReservation:
    """Reserve the next index; recovery requires the session's DB write lock."""
    if (
        not session_bid
        or type(turn_index) is not int
        or not 1 <= turn_index <= LIVE_FOLLOW_UP_MAX_TURNS
    ):
        raise LiveFollowUpSessionRejectedError(_ERROR_TURN_REJECTED)
    reservation = LiveFollowUpTurnReservation(
        session_bid=session_bid,
        turn_index=turn_index,
        claim=secrets.token_urlsafe(32),
    )
    result = _run_turn_reservation_script(
        app,
        script=_RESERVE_TURN_SCRIPT,
        reservation=reservation,
        extra_args=(str(LIVE_FOLLOW_UP_MAX_TURNS), "1" if recover_pending else "0"),
    )
    if result != 1:
        raise LiveFollowUpSessionRejectedError(_ERROR_TURN_REJECTED)
    return reservation


def commit_live_follow_up_turn_reservation(
    app: Flask,
    *,
    reservation: LiveFollowUpTurnReservation,
) -> None:
    """Advance the ordered turn cursor after durable persistence succeeds."""
    result = _run_turn_reservation_script(
        app,
        script=_COMMIT_TURN_SCRIPT,
        reservation=reservation,
    )
    if result != 1:
        raise LiveFollowUpSessionRejectedError(_ERROR_TURN_REJECTED)


def release_live_follow_up_turn_reservation(
    app: Flask,
    *,
    reservation: LiveFollowUpTurnReservation,
) -> None:
    """Release only the matching in-flight claim after persistence fails."""
    result = _run_turn_reservation_script(
        app,
        script=_RELEASE_TURN_SCRIPT,
        reservation=reservation,
    )
    if result != 1:
        raise LiveFollowUpSessionRejectedError(_ERROR_TURN_REJECTED)


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
