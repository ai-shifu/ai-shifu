"""Verification code consumption helpers.

These helpers validate and consume SMS/email verification codes without
creating or merging user accounts. This is important for flows like setting or
resetting passwords where we only want to validate ownership of an identifier.
"""

from __future__ import annotations

import datetime
from typing import Literal

from flask import Flask

from flaskr.common.cache_provider import cache as redis
from flaskr.dao import db
from flaskr.service.common.models import raise_error
from flaskr.service.user.models import UserVerifyCode

CodeKind = Literal["sms", "email"]


def _is_within_seconds(value: datetime.datetime, *, seconds: int) -> bool:
    if value is None:
        return False
    try:
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
    except Exception:
        # Defensive: keep original value if tzinfo manipulation fails.
        pass
    now = datetime.datetime.utcnow()
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


def _decode_cache_value(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


def consume_verification_code(app: Flask, *, identifier: str, code: str) -> None:
    """Validate and consume a verification code for an email or phone identifier."""

    identifier = (identifier or "").strip()
    code = (code or "").strip()
    # Parameter validation is handled by route handlers. Keep this helper focused
    # on verification logic.
    if not identifier or not code:
        raise_error("server.common.unknownError")

    is_email = "@" in identifier
    if is_email:
        email_key = identifier
        email_lower = email_key.lower()

        cache_keys = [app.config["REDIS_KEY_PREFIX_MAIL_CODE"] + email_key]
        if email_lower != email_key:
            cache_keys.append(app.config["REDIS_KEY_PREFIX_MAIL_CODE"] + email_lower)

        cached = None
        for cache_key in cache_keys:
            cached = redis.get(cache_key)
            if cached is not None:
                break

        if cached is not None:
            if code != _decode_cache_value(cached):
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
                raise_error("server.user.mailCheckError")
            if status != "ok":
                raise_error("server.user.mailSendExpired")

        redis.delete(*cache_keys)
        return

    cache_key = app.config["REDIS_KEY_PREFIX_PHONE_CODE"] + identifier
    cached = redis.get(cache_key)
    if cached is not None:
        if code != _decode_cache_value(cached):
            raise_error("server.user.smsCheckError")
        _consume_latest_code_from_db(
            app,
            kind="sms",
            identifier=identifier,
            code=code,
        )
    else:
        status = _consume_latest_code_from_db(
            app,
            kind="sms",
            identifier=identifier,
            code=code,
        )
        if status == "invalid":
            raise_error("server.user.smsCheckError")
        if status != "ok":
            raise_error("server.user.smsSendExpired")

    redis.delete(cache_key)
