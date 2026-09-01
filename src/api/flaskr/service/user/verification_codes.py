"""Verification code consumption helpers.

These helpers validate and consume SMS/email verification codes without
creating or merging user accounts. This is important for flows like setting or
resetting passwords where we only want to validate ownership of an identifier.
"""

from __future__ import annotations

import contextlib
import hashlib
import threading
from typing import TYPE_CHECKING, Literal

from flaskr.common.cache_provider import CacheLock, CacheProvider
from flaskr.common.cache_provider import cache as redis
from flaskr.common.cache_provider import redis_cache as distributed_lock_cache
from flaskr.common.config import get_redis_derived_prefix, get_redis_key_prefix
from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.phone_numbers import normalize_phone_identifier
from flaskr.service.user.models import UserVerifyCode
from flaskr.util.datetime import now_utc

if TYPE_CHECKING:
    import datetime
    from collections.abc import Iterator

    from flask import Flask

CodeKind = Literal["sms", "email"]
MAX_VERIFICATION_ATTEMPTS = 5
VERIFICATION_CODE_CONSUMED_MARKER = MAX_VERIFICATION_ATTEMPTS + 1
VERIFICATION_LOCK_TIMEOUT_SECONDS = 120
VERIFICATION_LOCK_RENEW_INTERVAL_SECONDS = 30.0


def _renew_verification_lock(
    app: Flask,
    lock: CacheLock,
    stop_event: threading.Event,
    lock_lost_event: threading.Event,
) -> None:
    while not stop_event.wait(VERIFICATION_LOCK_RENEW_INTERVAL_SECONDS):
        try:
            if not lock.extend(
                VERIFICATION_LOCK_TIMEOUT_SECONDS,
                replace_ttl=True,
            ):
                lock_lost_event.set()
                return
        except Exception:
            app.logger.exception("Failed to renew verification code lock")
            lock_lost_event.set()
            return


def _verification_code_settings(app: Flask, kind: CodeKind) -> tuple[str, int]:
    if kind == "email":
        return (
            get_redis_derived_prefix("REDIS_KEY_PREFIX_MAIL_CODE", app=app),
            int(app.config.get("MAIL_CODE_EXPIRE_TIME", 300)),
        )
    return (
        get_redis_derived_prefix("REDIS_KEY_PREFIX_PHONE_CODE", app=app),
        int(app.config.get("PHONE_CODE_EXPIRE_TIME", 300)),
    )


def _verification_attempt_key(app: Flask, kind: CodeKind, identifier: str) -> str:
    if kind == "email":
        normalized_identifier = (identifier or "").strip().lower()
    else:
        normalized_identifier = normalize_phone_identifier(identifier)
    identifier_digest = hashlib.sha256(
        f"{kind}:{normalized_identifier}".encode()
    ).hexdigest()
    return (
        f"{get_redis_key_prefix(app)}verification_code_state:"
        f"attempts:{identifier_digest}"
    )


def clear_verification_attempts(
    app: Flask,
    *,
    kind: CodeKind,
    identifier: str,
    cache_provider: CacheProvider | None = None,
) -> None:
    """Reset failed attempts when a new verification challenge is issued."""
    cache = cache_provider or redis
    cache.delete(_verification_attempt_key(app, kind, identifier))


@contextlib.contextmanager
def verification_code_lock(
    app: Flask,
    *,
    kind: CodeKind,
    identifier: str,
    cache_provider: CacheProvider | None = None,
) -> Iterator[CacheProvider]:
    """Serialize challenge issuance and consumption for one identifier."""
    cache = cache_provider or redis
    lock_provider = cache_provider or distributed_lock_cache
    if kind == "email":
        lock_identifier = (identifier or "").strip().lower()
        lock_error = "server.user.mailSendExpired"
    else:
        lock_identifier = normalize_phone_identifier(identifier)
        lock_error = "server.user.smsSendExpired"
    if not lock_identifier:
        raise_param_error("identifier")

    try:
        lock = lock_provider.lock(
            f"{_verification_attempt_key(app, kind, lock_identifier)}:lock",
            timeout=VERIFICATION_LOCK_TIMEOUT_SECONDS,
            blocking_timeout=5,
            thread_local=False,
        )
        acquired = bool(lock.acquire(blocking=True, blocking_timeout=5))
    except Exception:
        app.logger.exception("Failed to acquire distributed verification code lock")
        raise_error(lock_error)
    if not acquired:
        raise_error(lock_error)
    stop_event = threading.Event()
    lock_lost_event = threading.Event()
    renewal_thread = threading.Thread(
        target=_renew_verification_lock,
        args=(app, lock, stop_event, lock_lost_event),
        daemon=True,
        name="verification-code-lock-renewer",
    )
    renewal_thread.start()
    try:
        yield cache
    finally:
        stop_event.set()
        renewal_thread.join(timeout=1)
        if renewal_thread.is_alive():
            lock_lost_event.set()
        with contextlib.suppress(Exception):
            lock.release()
    if lock_lost_event.is_set():
        raise_error(lock_error)


def _record_invalid_attempt(
    app: Flask,
    *,
    kind: CodeKind,
    identifier: str,
    cache: CacheProvider,
    code_keys: list[str],
) -> None:
    attempt_key = _verification_attempt_key(app, kind, identifier)
    _prefix, expire_seconds = _verification_code_settings(app, kind)
    cache.set(attempt_key, 0, ex=expire_seconds, nx=True)
    attempts = cache.incr(attempt_key)
    if attempts >= MAX_VERIFICATION_ATTEMPTS:
        cache.delete(*code_keys)


def _verification_attempts_exhausted(
    app: Flask,
    *,
    kind: CodeKind,
    identifier: str,
    cache: CacheProvider,
) -> bool:
    attempts = cache.get(_verification_attempt_key(app, kind, identifier))
    return bool(attempts) and int(attempts) >= MAX_VERIFICATION_ATTEMPTS


def _mark_verification_code_consumed(
    app: Flask,
    *,
    kind: CodeKind,
    identifier: str,
    cache: CacheProvider,
) -> None:
    """Keep a short-lived tombstone so DB fallback cannot reuse the code."""
    attempt_key = _verification_attempt_key(app, kind, identifier)
    _prefix, expire_seconds = _verification_code_settings(app, kind)
    cache.set(
        attempt_key,
        VERIFICATION_CODE_CONSUMED_MARKER,
        ex=expire_seconds,
    )


def _is_within_seconds(value: datetime.datetime, *, seconds: int) -> bool:
    if value is None:
        return False
    # Defensive: keep the original value if tzinfo manipulation fails.
    with contextlib.suppress(Exception):
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
    now = now_utc()
    return (now - value).total_seconds() <= seconds


def _consume_latest_code_from_db(
    app: Flask,
    *,
    kind: CodeKind,
    identifier: str,
    code: str,
) -> str:
    """Consume the latest sent verification code from the database.

    Returns:
      - "ok" when the code is valid and is marked as used.
      - "expired" when no valid code exists (missing/used/expired).
      - "invalid" when a code exists but does not match.

    """
    if kind == "sms":
        expire_seconds = int(app.config.get("PHONE_CODE_EXPIRE_TIME", 300))
        query = UserVerifyCode.query.filter(
            UserVerifyCode.phone == identifier,
            UserVerifyCode.verify_code_type == 1,
            UserVerifyCode.verify_code_send == 1,
        )
    else:
        expire_seconds = int(app.config.get("MAIL_CODE_EXPIRE_TIME", 300))
        query = UserVerifyCode.query.filter(
            UserVerifyCode.mail == identifier,
            UserVerifyCode.verify_code_type == 2,
            UserVerifyCode.verify_code_send == 1,
        )

    latest = query.order_by(
        UserVerifyCode.created.desc(), UserVerifyCode.id.desc()
    ).first()
    if not latest or int(getattr(latest, "verify_code_used", 0) or 0) == 1:
        return "expired"

    created_at = getattr(latest, "created", None)
    if not created_at or not _is_within_seconds(created_at, seconds=expire_seconds):
        return "expired"

    if (latest.verify_code or "") != (code or ""):
        return "invalid"

    latest.verify_code_used = 1
    db.session.flush()
    return "ok"


def _decode_cache_value(raw: object) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


def consume_verification_code(
    app: Flask,
    *,
    identifier: str,
    code: str,
    cache_provider: CacheProvider | None = None,
) -> None:
    """Validate and consume a verification code for an email or phone identifier."""
    cache = cache_provider or redis
    identifier = (identifier or "").strip()
    code = (code or "").strip()
    # Keep helper-level parameter checks for direct service callers such as
    # password setup/reset flows.
    if not identifier:
        raise_param_error("identifier")
    if not code:
        raise_param_error("code")

    fix_code: str | None = app.config.get("UNIVERSAL_VERIFICATION_CODE")
    if fix_code and code == fix_code:
        # Universal code is accepted in dev/test environments and should not
        # affect cache/db state.
        return

    if "@" in identifier:
        kind: CodeKind = "email"
    else:
        kind = "sms"

    with verification_code_lock(
        app,
        kind=kind,
        identifier=identifier,
        cache_provider=cache_provider,
    ):
        _consume_verification_code_locked(
            app,
            identifier=identifier,
            code=code,
            cache=cache,
        )


def _consume_verification_code_locked(
    app: Flask,
    *,
    identifier: str,
    code: str,
    cache: CacheProvider,
) -> None:
    """Consume a code while the normalized identifier lock is held."""
    is_email = "@" in identifier
    if is_email:
        email_key = identifier
        email_lower = email_key.lower()
        mail_code_prefix, _expire_seconds = _verification_code_settings(app, "email")

        cache_keys = [mail_code_prefix + email_key]
        if email_lower != email_key:
            cache_keys.append(mail_code_prefix + email_lower)

        cached = None
        for cache_key in cache_keys:
            cached = cache.get(cache_key)
            if cached is not None:
                break

        if _verification_attempts_exhausted(
            app,
            kind="email",
            identifier=email_lower,
            cache=cache,
        ):
            cache.delete(*cache_keys)
            raise_error("server.user.mailSendExpired")

        if cached is not None:
            if code != _decode_cache_value(cached):
                _record_invalid_attempt(
                    app,
                    kind="email",
                    identifier=email_lower,
                    cache=cache,
                    code_keys=cache_keys,
                )
                raise_error("server.user.mailCheckError")
            # Best-effort: mark the DB record as used if present.
            status = _consume_latest_code_from_db(
                app,
                kind="email",
                identifier=email_key,
                code=code,
            )
            if status != "ok" and email_lower != email_key:
                _consume_latest_code_from_db(
                    app,
                    kind="email",
                    identifier=email_lower,
                    code=code,
                )
        else:
            status = _consume_latest_code_from_db(
                app,
                kind="email",
                identifier=email_key,
                code=code,
            )
            if status != "ok" and email_lower != email_key:
                status = _consume_latest_code_from_db(
                    app,
                    kind="email",
                    identifier=email_lower,
                    code=code,
                )
            if status == "invalid":
                _record_invalid_attempt(
                    app,
                    kind="email",
                    identifier=email_lower,
                    cache=cache,
                    code_keys=cache_keys,
                )
                raise_error("server.user.mailCheckError")
            if status != "ok":
                raise_error("server.user.mailSendExpired")

        _mark_verification_code_consumed(
            app,
            kind="email",
            identifier=email_lower,
            cache=cache,
        )
        cache.delete(*cache_keys)
        return

    raw_identifier = identifier
    identifier = normalize_phone_identifier(raw_identifier)
    if not identifier:
        raise_param_error("identifier")

    lookup_identifiers = [identifier]
    if raw_identifier and raw_identifier not in lookup_identifiers:
        lookup_identifiers.append(raw_identifier)
    phone_code_prefix, _expire_seconds = _verification_code_settings(app, "sms")
    cache_keys = [
        phone_code_prefix + lookup_identifier
        for lookup_identifier in lookup_identifiers
    ]

    cached = None
    cached_identifier = identifier
    for cache_key, lookup_identifier in zip(
        cache_keys, lookup_identifiers, strict=False
    ):
        cached = cache.get(cache_key)
        if cached is not None:
            cached_identifier = lookup_identifier
            break

    if _verification_attempts_exhausted(
        app,
        kind="sms",
        identifier=identifier,
        cache=cache,
    ):
        cache.delete(*cache_keys)
        raise_error("server.user.smsSendExpired")

    if cached is not None:
        if code != _decode_cache_value(cached):
            _record_invalid_attempt(
                app,
                kind="sms",
                identifier=identifier,
                cache=cache,
                code_keys=cache_keys,
            )
            raise_error("server.user.smsCheckError")
        status = _consume_latest_code_from_db(
            app,
            kind="sms",
            identifier=cached_identifier,
            code=code,
        )
        if status != "ok" and cached_identifier != identifier:
            _consume_latest_code_from_db(
                app,
                kind="sms",
                identifier=identifier,
                code=code,
            )
    else:
        status = "expired"
        for lookup_identifier in lookup_identifiers:
            status = _consume_latest_code_from_db(
                app,
                kind="sms",
                identifier=lookup_identifier,
                code=code,
            )
            if status == "ok":
                break
            if status == "invalid":
                break
        if status == "invalid":
            _record_invalid_attempt(
                app,
                kind="sms",
                identifier=identifier,
                cache=cache,
                code_keys=cache_keys,
            )
            raise_error("server.user.smsCheckError")
        if status != "ok":
            raise_error("server.user.smsSendExpired")

    _mark_verification_code_consumed(
        app,
        kind="sms",
        identifier=identifier,
        cache=cache,
    )
    cache.delete(*cache_keys)
