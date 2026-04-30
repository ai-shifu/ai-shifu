from __future__ import annotations

import base64
import hashlib
import hmac
import json
import random
import secrets
import string
from io import BytesIO
from typing import Any

from flask import Flask
from PIL import Image, ImageDraw, ImageFont

try:
    from captcha.image import ImageCaptcha
except ModuleNotFoundError:  # pragma: no cover - exercised only in slim envs
    ImageCaptcha = None

from flaskr.common.cache_provider import cache as redis
from flaskr.service.common.models import raise_error


_CAPTCHA_ALPHABET = "".join(
    character
    for character in string.ascii_uppercase + string.digits
    if character not in {"0", "O", "1", "I"}
)


def _is_production(app: Flask) -> bool:
    environment = (
        app.config.get("ENV")
        or app.config.get("MODE")
        or app.config.get("ENVERIMENT")
        or ""
    )
    return str(environment).strip().lower() in {"prod", "production"}


def _cache_prefix(app: Flask, config_key: str, suffix: str) -> str:
    configured = app.config.get(config_key)
    if configured:
        return str(configured)
    base_prefix = str(app.config.get("REDIS_KEY_PREFIX") or "")
    return base_prefix + suffix


def _captcha_key(app: Flask, captcha_id: str) -> str:
    return _cache_prefix(app, "REDIS_KEY_PREFIX_CAPTCHA", "captcha:") + captcha_id


def _ticket_key(app: Flask, ticket: str) -> str:
    return (
        _cache_prefix(app, "REDIS_KEY_PREFIX_CAPTCHA_TICKET", "captcha_ticket:")
        + ticket
    )


def _normalize_code(value: str | None) -> str:
    return str(value or "").strip().upper()


def _decode_cache_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _code_digest(app: Flask, code: str) -> str:
    secret = str(app.config.get("SECRET_KEY") or "")
    return hmac.new(
        secret.encode("utf-8"),
        _normalize_code(code).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _load_captcha_payload(app: Flask, captcha_id: str) -> dict[str, Any] | None:
    raw_value = _decode_cache_value(redis.get(_captcha_key(app, captcha_id)))
    if not raw_value:
        return None
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        redis.delete(_captcha_key(app, captcha_id))
        return None
    if not isinstance(payload, dict):
        redis.delete(_captcha_key(app, captcha_id))
        return None
    return payload


def _store_captcha_payload(
    app: Flask, captcha_id: str, payload: dict[str, Any], ttl_seconds: int
) -> None:
    redis.set(
        _captcha_key(app, captcha_id),
        json.dumps(payload, separators=(",", ":")),
        ex=ttl_seconds,
    )


def _generate_code(app: Flask) -> str:
    override = app.config.get("CAPTCHA_CODE_OVERRIDE")
    if override and not _is_production(app):
        return _normalize_code(str(override))[:4]
    return "".join(random.SystemRandom().choice(_CAPTCHA_ALPHABET) for _ in range(4))


def _render_captcha_png(code: str) -> bytes:
    if ImageCaptcha is not None:
        image = ImageCaptcha(width=120, height=40)
        return image.generate(code, format="png").getvalue()

    image = Image.new("RGB", (120, 40), color=(245, 247, 250))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for _ in range(6):
        draw.line(
            (
                random.randint(0, 120),
                random.randint(0, 40),
                random.randint(0, 120),
                random.randint(0, 40),
            ),
            fill=(
                random.randint(120, 190),
                random.randint(120, 190),
                random.randint(120, 190),
            ),
            width=1,
        )
    draw.text((28, 12), code, fill=(28, 39, 58), font=font)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def create_captcha_challenge(app: Flask) -> dict[str, Any]:
    expire_seconds = int(app.config.get("CAPTCHA_EXPIRE_TIME", 300))
    code = _generate_code(app)
    captcha_id = secrets.token_urlsafe(18)
    image_bytes = _render_captcha_png(code)

    _store_captcha_payload(
        app,
        captcha_id,
        {"digest": _code_digest(app, code), "attempts": 0},
        expire_seconds,
    )

    return {
        "captcha_id": captcha_id,
        "image": "data:image/png;base64,"
        + base64.b64encode(image_bytes).decode("ascii"),
        "expires_in": expire_seconds,
    }


def verify_captcha_code(
    app: Flask, captcha_id: str, captcha_code: str
) -> dict[str, Any]:
    payload = _load_captcha_payload(app, captcha_id)
    if payload is None:
        raise_error("server.user.checkCodeExpired")

    max_attempts = int(app.config.get("CAPTCHA_MAX_VERIFY_ATTEMPTS", 5))
    expected_digest = str(payload.get("digest") or "")
    provided_digest = _code_digest(app, captcha_code)
    if not hmac.compare_digest(expected_digest, provided_digest):
        attempts = int(payload.get("attempts", 0) or 0) + 1
        if attempts >= max_attempts:
            redis.delete(_captcha_key(app, captcha_id))
        else:
            payload["attempts"] = attempts
            remaining_ttl = redis.ttl(_captcha_key(app, captcha_id))
            if remaining_ttl <= 0:
                redis.delete(_captcha_key(app, captcha_id))
                raise_error("server.user.checkCodeExpired")
            _store_captcha_payload(app, captcha_id, payload, remaining_ttl)
        raise_error("server.user.checkCodeError")

    redis.delete(_captcha_key(app, captcha_id))
    ticket = secrets.token_urlsafe(32)
    ticket_expire_seconds = int(app.config.get("CAPTCHA_TICKET_EXPIRE_TIME", 300))
    redis.set(_ticket_key(app, ticket), captcha_id, ex=ticket_expire_seconds)

    return {"captcha_ticket": ticket, "expires_in": ticket_expire_seconds}


def consume_captcha_ticket(app: Flask, captcha_ticket: str | None) -> None:
    if not captcha_ticket:
        raise_error("server.user.checkCodeError")

    key = _ticket_key(app, str(captcha_ticket).strip())
    if redis.get(key) is None:
        raise_error("server.user.checkCodeExpired")
    redis.delete(key)
