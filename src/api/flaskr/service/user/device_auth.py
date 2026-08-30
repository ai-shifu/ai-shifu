"""Device authorization flow for command-line clients.

The skill CLI cannot render an image captcha, which is why it historically
called a captcha-free SMS endpoint. This module replaces that flow with a
browser based device authorization grant: the CLI starts an authorization
request, the user approves it from a browser session that already carries the
regular login protections, and the CLI polls until a token is issued.

Two distinct codes are used, and they must not be mixed up:

``device_code``
    High entropy secret held only by the CLI. Whoever holds it can collect the
    issued token, so it is never placed in a URL or shown to the user.

``user_code``
    Short human readable pairing code that identifies the pending request in
    the browser. It is safe to put in the verification URL because on its own
    it cannot collect a token; approving still requires an authenticated user
    who clicks through the confirmation page.
"""

from __future__ import annotations

import json
import secrets
import time
from typing import TYPE_CHECKING, Any

from flaskr.common.cache_provider import cache as redis
from flaskr.common.config import get_redis_derived_prefix
from flaskr.common.public_urls import build_public_url
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import raise_error
from flaskr.service.user.utils import generate_token

if TYPE_CHECKING:
    from flask import Flask

DEVICE_VERIFICATION_PATH = "/login/device"

# Characters that stay unambiguous when a person reads the pairing code out of
# a terminal: no O/0, I/1, S/5, B/8 lookalikes.
_USER_CODE_ALPHABET = "ACDEFHJKLMNPRTUVWXY3479"
_USER_CODE_LENGTH = 6
_USER_CODE_GROUP_SIZE = 3
_USER_CODE_GENERATION_TRIES = 5

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_DENIED = "denied"

# Device metadata is attacker supplied and only ever displayed, so it is capped
# to keep oversized payloads out of the cache and out of the approval page.
_MAX_TEXT_FIELD_LENGTH = 64


def _expire_seconds(app: Flask) -> int:
    return int(app.config.get("DEVICE_AUTH_EXPIRE_TIME", 600))


def _poll_interval(app: Flask) -> int:
    return int(app.config.get("DEVICE_AUTH_POLL_INTERVAL", 5))


def _session_key(app: Flask, device_code: str) -> str:
    prefix = get_redis_derived_prefix("REDIS_KEY_PREFIX_DEVICE_AUTH", app=app)
    return f"{prefix}{device_code}"


def _user_code_key(app: Flask, user_code: str) -> str:
    prefix = get_redis_derived_prefix("REDIS_KEY_PREFIX_DEVICE_USER_CODE", app=app)
    return f"{prefix}{user_code}"


def _lookup_limit_key(app: Flask, scope: str) -> str:
    prefix = get_redis_derived_prefix("REDIS_KEY_PREFIX_DEVICE_USER_CODE", app=app)
    return f"{prefix}attempts:{scope}"


def _issue_limit_key(app: Flask, scope: str) -> str:
    prefix = get_redis_derived_prefix("REDIS_KEY_PREFIX_DEVICE_AUTH", app=app)
    return f"{prefix}issued:{scope}"


def _decode(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _clean_text(value: object, limit: int = _MAX_TEXT_FIELD_LENGTH) -> str:
    text = str(value or "").strip()
    return text[:limit]


def normalize_user_code(value: object) -> str:
    """Strip separators and casing so a pasted pairing code still resolves."""
    raw = str(value or "").strip().upper()
    return "".join(character for character in raw if character.isalnum())


def format_user_code(user_code: str) -> str:
    """Group the pairing code so it is easier to read and to type."""
    groups = [
        user_code[index : index + _USER_CODE_GROUP_SIZE]
        for index in range(0, len(user_code), _USER_CODE_GROUP_SIZE)
    ]
    return "-".join(group for group in groups if group)


def _load_session(app: Flask, device_code: str) -> dict[str, Any] | None:
    raw_value = _decode(redis.get(_session_key(app, device_code)))
    if not raw_value:
        return None
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        redis.delete(_session_key(app, device_code))
        return None
    if not isinstance(payload, dict):
        redis.delete(_session_key(app, device_code))
        return None
    return payload


def _store_session(
    app: Flask, device_code: str, payload: dict[str, Any], ttl_seconds: int
) -> None:
    redis.set(
        _session_key(app, device_code),
        json.dumps(payload, separators=(",", ":")),
        ex=ttl_seconds,
    )


def _drop_session(app: Flask, device_code: str, user_code: str | None) -> None:
    redis.delete(_session_key(app, device_code))
    if user_code:
        redis.delete(_user_code_key(app, user_code))


def _resolve_device_code(app: Flask, user_code: str) -> str | None:
    return _decode(redis.get(_user_code_key(app, user_code)))


def _generate_user_code(app: Flask, ttl_seconds: int) -> str:
    """Reserve an unused pairing code, retrying on the rare collision."""
    reserved: str | None = None
    for _ in range(_USER_CODE_GENERATION_TRIES):
        candidate = "".join(
            secrets.choice(_USER_CODE_ALPHABET) for _ in range(_USER_CODE_LENGTH)
        )
        # ``nx`` makes the reservation atomic, so two concurrent requests can
        # never be handed the same pairing code.
        if redis.set(_user_code_key(app, candidate), "", ex=ttl_seconds, nx=True):
            reserved = candidate
            break
    if reserved is None:
        raise_error("server.user.deviceCodeInvalid")
    return reserved


def _guard_lookup_rate(app: Flask, client_ip: str | None) -> None:
    """Throttle pairing-code guesses so the short code cannot be brute forced.

    The counter deliberately survives a successful lookup for the rest of the
    window. Clearing it on success would let an attacker reset the budget with
    a pairing code they legitimately hold and keep guessing indefinitely.
    """
    if not client_ip:
        return
    max_attempts = int(app.config.get("DEVICE_AUTH_MAX_LOOKUP_ATTEMPTS", 10))
    window = int(app.config.get("DEVICE_AUTH_LOOKUP_WINDOW", 600))
    key = _lookup_limit_key(app, client_ip)
    attempts = _decode(redis.get(key))
    if attempts and int(attempts) >= max_attempts:
        raise_error("server.user.deviceCodeInvalid")
    redis.set(key, int(attempts or 0) + 1, ex=window)


def _guard_issue_rate(app: Flask, client_ip: str | None) -> None:
    """Bound how many requests one client can open.

    Starting a request is unauthenticated and writes two cache entries that
    live for the full expiry window, so an unbounded caller could otherwise
    keep allocating them.
    """
    if not client_ip:
        return
    max_requests = int(app.config.get("DEVICE_AUTH_MAX_REQUESTS", 20))
    window = int(app.config.get("DEVICE_AUTH_ISSUE_WINDOW", 600))
    key = _issue_limit_key(app, client_ip)
    issued = _decode(redis.get(key))
    if issued and int(issued) >= max_requests:
        raise_error("server.user.deviceAuthTooManyRequests")
    redis.set(key, int(issued or 0) + 1, ex=window)


def _session_lock(app: Flask, device_code: str) -> object:
    """Serialize read-modify-write cycles on a single request.

    Approving, denying and collecting all read the request, decide, then write
    it back. Without this lock two of them can read the same pending state and
    both act on it: conflicting decisions would race, and a request could be
    collected more than once.
    """
    return redis.lock(
        f"{_session_key(app, device_code)}:lock", timeout=5, blocking_timeout=3
    )


def create_device_authorization(
    app: Flask,
    *,
    device_name: str | None = None,
    device_os: str | None = None,
    client_version: str | None = None,
    client_ip: str | None = None,
) -> dict[str, Any]:
    """Start a pending authorization and hand the CLI its polling secret."""
    _guard_issue_rate(app, client_ip)
    ttl_seconds = _expire_seconds(app)
    device_code = secrets.token_urlsafe(32)
    user_code = _generate_user_code(app, ttl_seconds)

    payload = {
        "user_code": user_code,
        "status": STATUS_PENDING,
        "user_id": "",
        "device_name": _clean_text(device_name),
        "device_os": _clean_text(device_os),
        "client_version": _clean_text(client_version),
        "client_ip": _clean_text(client_ip),
        "created_at": int(time.time()),
    }
    _store_session(app, device_code, payload, ttl_seconds)
    redis.set(_user_code_key(app, user_code), device_code, ex=ttl_seconds)

    verification_uri = build_public_url(DEVICE_VERIFICATION_PATH)
    formatted_user_code = format_user_code(user_code)
    return {
        "device_code": device_code,
        "user_code": formatted_user_code,
        "verification_uri": verification_uri,
        "verification_uri_complete": f"{verification_uri}?code={formatted_user_code}",
        "expires_in": ttl_seconds,
        "interval": _poll_interval(app),
    }


def _require_pending(
    app: Flask, user_code: str, client_ip: str | None
) -> tuple[str, dict[str, Any]]:
    normalized = normalize_user_code(user_code)
    if not normalized:
        raise_error("server.user.deviceCodeInvalid")

    _guard_lookup_rate(app, client_ip)
    device_code = _resolve_device_code(app, normalized)
    if not device_code:
        raise_error("server.user.deviceCodeInvalid")

    payload = _load_session(app, device_code)
    if payload is None:
        redis.delete(_user_code_key(app, normalized))
        raise_error("server.user.deviceCodeInvalid")

    if payload.get("status") != STATUS_PENDING:
        raise_error("server.user.deviceAuthAlreadyHandled")

    return device_code, payload


def get_device_authorization(
    app: Flask, *, user_code: str, client_ip: str | None = None
) -> dict[str, Any]:
    """Describe a pending request so the approval page can show what it is."""
    device_code, payload = _require_pending(app, user_code, client_ip)
    # Read the remaining lifetime from the cache entry itself rather than
    # deriving it from a stored epoch value.
    expires_in = max(0, int(redis.ttl(_session_key(app, device_code)) or 0))
    return {
        "user_code": format_user_code(str(payload.get("user_code") or "")),
        "device_name": payload.get("device_name") or "",
        "device_os": payload.get("device_os") or "",
        "client_version": payload.get("client_version") or "",
        "client_ip": payload.get("client_ip") or "",
        "expires_in": expires_in,
    }


def _record_decision(
    app: Flask,
    *,
    user_code: str,
    status: str,
    user_id: str = "",
    client_ip: str | None = None,
) -> dict[str, Any]:
    """Write a decision onto a pending request, one decision at a time."""
    device_code, _ = _require_pending(app, user_code, client_ip)

    lock = _session_lock(app, device_code)
    if not lock.acquire(blocking=True, blocking_timeout=3):
        raise_error("server.user.deviceCodeInvalid")
    try:
        # Re-read inside the lock: another decision may have landed between the
        # lookup above and this point.
        payload = _load_session(app, device_code)
        if payload is None:
            raise_error("server.user.deviceCodeInvalid")
        if payload.get("status") != STATUS_PENDING:
            raise_error("server.user.deviceAuthAlreadyHandled")

        # Keep the remaining lifetime rather than extending it: deciding must
        # not widen the window in which the pairing code stays usable.
        remaining_ttl = redis.ttl(_session_key(app, device_code))
        if remaining_ttl is None or remaining_ttl <= 0:
            raise_error("server.user.deviceCodeInvalid")

        payload["status"] = status
        if user_id:
            payload["user_id"] = str(user_id)
            payload["approved_at"] = int(time.time())
        _store_session(app, device_code, payload, remaining_ttl)
    finally:
        lock.release()

    return {"status": status}


def approve_device_authorization(
    app: Flask, *, user_code: str, user_id: str, client_ip: str | None = None
) -> dict[str, Any]:
    """Bind the pending request to the signed-in user after they confirm."""
    if not user_id:
        raise_error("server.user.userNotLogin")
    return _record_decision(
        app,
        user_code=user_code,
        status=STATUS_APPROVED,
        user_id=user_id,
        client_ip=client_ip,
    )


def deny_device_authorization(
    app: Flask, *, user_code: str, client_ip: str | None = None
) -> dict[str, Any]:
    """Reject the pending request so the CLI stops polling immediately."""
    return _record_decision(
        app, user_code=user_code, status=STATUS_DENIED, client_ip=client_ip
    )


def poll_device_authorization(app: Flask, *, device_code: str) -> dict[str, Any]:
    """Report the request state, issuing the token once it was approved.

    The token is minted here rather than at approval time so that it never sits
    in the cache, and so its lifetime starts when the client actually collects
    it. Collection happens under the request lock, so two concurrent polls
    cannot both walk away with a token.
    """
    normalized = str(device_code or "").strip()
    if not normalized:
        raise_error("server.user.deviceCodeInvalid")

    if _load_session(app, normalized) is None:
        raise_error("server.user.deviceCodeInvalid")

    lock = _session_lock(app, normalized)
    if not lock.acquire(blocking=True, blocking_timeout=3):
        # Another caller holds the request; report the state it had on entry
        # rather than risking a second collection.
        return {"status": STATUS_PENDING, "token": "", "interval": _poll_interval(app)}
    try:
        payload = _load_session(app, normalized)
        if payload is None:
            raise_error("server.user.deviceCodeInvalid")

        status = payload.get("status")
        user_code = str(payload.get("user_code") or "")

        if status == STATUS_DENIED:
            _drop_session(app, normalized, user_code)
            return {"status": STATUS_DENIED, "token": ""}

        if status == STATUS_APPROVED:
            user_id = str(payload.get("user_id") or "")
            if not user_id:
                _drop_session(app, normalized, user_code)
                raise_error("server.user.deviceCodeInvalid")
            with unit_of_work():
                # Name the session after the machine the user approved, not
                # after the polling client's user agent.
                token = generate_token(
                    app,
                    user_id,
                    source="cli",
                    device_name=str(payload.get("device_name") or ""),
                    device_os=str(payload.get("device_os") or ""),
                )
            # One-shot: the request is consumed so a leaked device code cannot
            # be replayed to mint a second token.
            _drop_session(app, normalized, user_code)
            return {"status": STATUS_APPROVED, "token": token}

        return {"status": STATUS_PENDING, "token": "", "interval": _poll_interval(app)}
    finally:
        lock.release()
