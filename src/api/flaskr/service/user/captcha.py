from __future__ import annotations

import base64
import hashlib
import hmac
import json
import random
import secrets
from io import BytesIO
from typing import Any

from flask import Flask
from PIL import Image, ImageDraw, ImageFont

from flaskr.common.cache_provider import cache as redis
from flaskr.service.common.models import raise_error


_CAPTCHA_ALPHABET = "ACDEFHJKLMNPRTUVWXY3479"
_CAPTCHA_IMAGE_WIDTH = 160
_CAPTCHA_IMAGE_HEIGHT = 48
_CAPTCHA_FONT_SIZE = 34
_CAPTCHA_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "DejaVuSans-Bold.ttf",
)
_RANDOM = random.SystemRandom()


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
    return "".join(_RANDOM.choice(_CAPTCHA_ALPHABET) for _ in range(4))


def _load_captcha_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in _CAPTCHA_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(font_path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_captcha_png(code: str) -> bytes:
    image = Image.new(
        "RGB",
        (_CAPTCHA_IMAGE_WIDTH, _CAPTCHA_IMAGE_HEIGHT),
        color=(250, 252, 255),
    )
    draw = ImageDraw.Draw(image)
    font = _load_captcha_font(_CAPTCHA_FONT_SIZE)
    resample_filter = getattr(getattr(Image, "Resampling", Image), "BICUBIC")

    for y in (13, 25, 37):
        draw.line(
            (
                8,
                y + _RANDOM.randint(-2, 2),
                _CAPTCHA_IMAGE_WIDTH - 8,
                y + _RANDOM.randint(-2, 2),
            ),
            fill=(226, 233, 242),
            width=1,
        )

    char_cell_width = 34
    char_layer_size = (40, 44)
    start_x = 12
    text_colors = ((28, 39, 58), (41, 63, 96), (32, 79, 114), (65, 74, 91))
    for index, character in enumerate(code):
        layer = Image.new("RGBA", char_layer_size, (255, 255, 255, 0))
        layer_draw = ImageDraw.Draw(layer)
        bbox = layer_draw.textbbox((0, 0), character, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (char_layer_size[0] - text_width) / 2 - bbox[0]
        y = (char_layer_size[1] - text_height) / 2 - bbox[1] - 1
        color = _RANDOM.choice(text_colors)
        layer_draw.text((x, y), character, fill=(*color, 255), font=font)
        rotated = layer.rotate(
            _RANDOM.uniform(-3.0, 3.0),
            resample=resample_filter,
            expand=False,
        )
        image.paste(
            rotated,
            (start_x + index * char_cell_width + _RANDOM.randint(-1, 1), 2),
            rotated,
        )

    for _ in range(22):
        draw.point(
            (
                _RANDOM.randint(0, _CAPTCHA_IMAGE_WIDTH - 1),
                _RANDOM.randint(0, _CAPTCHA_IMAGE_HEIGHT - 1),
            ),
            fill=(204, 214, 228),
        )
    draw.rectangle(
        (0, 0, _CAPTCHA_IMAGE_WIDTH - 1, _CAPTCHA_IMAGE_HEIGHT - 1),
        outline=(221, 228, 238),
    )
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
