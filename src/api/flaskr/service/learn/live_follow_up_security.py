"""Issue and consume one-time Redis tickets for Live follow-up WebSockets.

The raw ticket is returned only to the HTTP route so it can be placed in an
HttpOnly cookie. Redis stores a SHA-256 digest and the exact session binding;
there is deliberately no process-local fallback when Redis is unavailable.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from flaskr.util.datetime import now_utc

if TYPE_CHECKING:
    from flask import Flask
    from redis import Redis

LIVE_FOLLOW_UP_TICKET_TTL_SECONDS = 30
LIVE_FOLLOW_UP_TICKET_COOKIE_NAME = "live_follow_up_ticket"
_TICKET_RECORD_VERSION = 1
_ERROR_INVALID_BINDING = "invalid_binding"
_ERROR_INVALID_ORIGIN = "invalid_origin"
_ERROR_INVALID_TICKET = "invalid_ticket"
_ERROR_REDIS_UNAVAILABLE = "redis_unavailable"
_ERROR_TICKET_NOT_STORED = "ticket_not_stored"

_CONSUME_TICKET_SCRIPT = """
local payload = redis.call('GET', KEYS[1])
if payload then
    redis.call('DEL', KEYS[1])
end
return payload
"""


class LiveFollowUpSecurityError(RuntimeError):
    """Base class for bounded Live follow-up ticket failures."""


class LiveFollowUpSecurityUnavailableError(LiveFollowUpSecurityError):
    """Redis could not safely issue or consume a Live ticket."""


class LiveFollowUpTicketRejectedError(LiveFollowUpSecurityError):
    """The ticket is missing, expired, malformed, or bound elsewhere."""


@dataclass(frozen=True)
class LiveFollowUpTicketBinding:
    """Trusted values bound to exactly one Live WebSocket handshake."""

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


@dataclass(frozen=True)
class IssuedLiveFollowUpTicket:
    """Raw one-time ticket and its short-lived expiry for cookie delivery."""

    token: str
    expires_at: datetime


def _redis_client() -> Redis | None:
    from flaskr.dao import get_redis_client

    return get_redis_client()


def _scope_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ticket_key(app: Flask, session_bid: str) -> str:
    prefix = str(app.config.get("REDIS_KEY_PREFIX", "ai-shifu:") or "ai-shifu:")
    return f"{prefix.rstrip(':')}:live-follow-up:ticket:{_scope_digest(session_bid)}"


def _ticket_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _validate_origin(origin: str) -> str:
    if not isinstance(origin, str) or not origin or origin != origin.strip():
        raise LiveFollowUpTicketRejectedError(_ERROR_INVALID_ORIGIN)
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise LiveFollowUpTicketRejectedError(_ERROR_INVALID_ORIGIN)
    return origin


def _validate_binding(binding: LiveFollowUpTicketBinding) -> None:
    required_strings = (
        binding.session_bid,
        binding.user_bid,
        binding.shifu_bid,
        binding.outline_bid,
        binding.anchor_element_bid,
        binding.progress_record_bid,
        binding.model,
        binding.voice_name,
        binding.language,
        binding.learning_mode,
    )
    if any(not isinstance(value, str) or not value for value in required_strings):
        raise LiveFollowUpTicketRejectedError(_ERROR_INVALID_BINDING)
    if type(binding.preview_mode) is not bool:
        raise LiveFollowUpTicketRejectedError(_ERROR_INVALID_BINDING)
    _validate_origin(binding.origin)


def _serialize_ticket_record(*, token: str, binding: LiveFollowUpTicketBinding) -> str:
    return json.dumps(
        {
            "version": _TICKET_RECORD_VERSION,
            "ticket_hash": _ticket_digest(token),
            "binding": asdict(binding),
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def issue_live_follow_up_ticket(
    app: Flask,
    *,
    binding: LiveFollowUpTicketBinding,
) -> IssuedLiveFollowUpTicket:
    """Create a 256-bit, single-use ticket or fail closed."""
    _validate_binding(binding)
    client = _redis_client()
    if client is None:
        raise LiveFollowUpSecurityUnavailableError(_ERROR_REDIS_UNAVAILABLE)

    token = secrets.token_urlsafe(32)
    payload = _serialize_ticket_record(token=token, binding=binding)
    try:
        stored = client.set(
            _ticket_key(app, binding.session_bid),
            payload,
            ex=LIVE_FOLLOW_UP_TICKET_TTL_SECONDS,
            nx=True,
        )
    except Exception as exc:
        raise LiveFollowUpSecurityUnavailableError(_ERROR_REDIS_UNAVAILABLE) from exc
    if not stored:
        raise LiveFollowUpSecurityUnavailableError(_ERROR_TICKET_NOT_STORED)

    return IssuedLiveFollowUpTicket(
        token=token,
        expires_at=now_utc() + timedelta(seconds=LIVE_FOLLOW_UP_TICKET_TTL_SECONDS),
    )


def _decode_ticket_record(raw: bytes | str) -> tuple[str, LiveFollowUpTicketBinding]:
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        record: Any = json.loads(text)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveFollowUpTicketRejectedError(_ERROR_INVALID_TICKET) from exc
    if not isinstance(record, dict) or record.get("version") != 1:
        raise LiveFollowUpTicketRejectedError(_ERROR_INVALID_TICKET)
    ticket_hash = record.get("ticket_hash")
    binding_data = record.get("binding")
    if not isinstance(ticket_hash, str) or not isinstance(binding_data, dict):
        raise LiveFollowUpTicketRejectedError(_ERROR_INVALID_TICKET)
    try:
        binding = LiveFollowUpTicketBinding(**binding_data)
    except TypeError as exc:
        raise LiveFollowUpTicketRejectedError(_ERROR_INVALID_TICKET) from exc
    _validate_binding(binding)
    return ticket_hash, binding


def consume_live_follow_up_ticket(
    app: Flask,
    *,
    session_bid: str,
    token: str | None,
    origin: str | None,
) -> LiveFollowUpTicketBinding:
    """Atomically consume and verify the exact ticket, Origin, and session."""
    if not session_bid or not token or not origin:
        raise LiveFollowUpTicketRejectedError(_ERROR_INVALID_TICKET)

    client = _redis_client()
    if client is None:
        raise LiveFollowUpSecurityUnavailableError(_ERROR_REDIS_UNAVAILABLE)
    try:
        raw = client.eval(
            _CONSUME_TICKET_SCRIPT,
            1,
            _ticket_key(app, session_bid),
        )
    except Exception as exc:
        raise LiveFollowUpSecurityUnavailableError(_ERROR_REDIS_UNAVAILABLE) from exc
    if raw is None:
        raise LiveFollowUpTicketRejectedError(_ERROR_INVALID_TICKET)

    stored_hash, binding = _decode_ticket_record(raw)
    supplied_hash = _ticket_digest(token)
    if not hmac.compare_digest(stored_hash, supplied_hash):
        raise LiveFollowUpTicketRejectedError(_ERROR_INVALID_TICKET)
    if not hmac.compare_digest(binding.session_bid, session_bid):
        raise LiveFollowUpTicketRejectedError(_ERROR_INVALID_TICKET)
    if not hmac.compare_digest(binding.origin, origin):
        raise LiveFollowUpTicketRejectedError(_ERROR_INVALID_ORIGIN)
    return binding
