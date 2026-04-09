"""Shared low-level billing primitives for scalar, JSON, and datetime coercion."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from flask import Flask

from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.util.timezone import serialize_with_app_timezone

from .value_objects import JsonObjectMap

_USAGE_SCENE_LABELS = {
    BILL_USAGE_SCENE_DEBUG: "debug",
    BILL_USAGE_SCENE_PREVIEW: "preview",
    BILL_USAGE_SCENE_PROD: "production",
}


def normalize_bid(value: Any) -> str:
    return str(value or "").strip()


def to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def decimal_to_number(value: Any) -> int | float:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        if value == value.to_integral():
            return int(value)
        return float(value)
    if isinstance(value, (int, float)):
        return value
    try:
        normalized = Decimal(str(value))
    except Exception:
        return 0
    if normalized == normalized.to_integral():
        return int(normalized)
    return float(normalized)


def safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def safe_to_decimal(value: Any, *, default: Any) -> Decimal:
    try:
        return to_decimal(value)
    except Exception:
        return to_decimal(default)


def safe_to_positive_int(value: Any, *, default: int) -> int:
    candidate = safe_int(value)
    if candidate is None or candidate <= 0:
        return default
    return candidate


def parse_config_datetime(value: Any) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def coerce_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return datetime.fromtimestamp(value)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text))
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def normalize_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_to_number(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [normalize_json_value(item) for item in value]
    if isinstance(value, JsonObjectMap):
        payload = JsonObjectMap(
            values={str(key): normalize_json_value(item) for key, item in value.items()}
        )
        usage_scene = payload.get("usage_scene")
        if isinstance(usage_scene, (int, str)):
            payload["usage_scene"] = _USAGE_SCENE_LABELS.get(
                safe_int(usage_scene),
                str(usage_scene),
            )
        return payload
    if isinstance(value, dict):
        payload = JsonObjectMap(
            values={str(key): normalize_json_value(item) for key, item in value.items()}
        )
        usage_scene = payload.get("usage_scene")
        if isinstance(usage_scene, (int, str)):
            payload["usage_scene"] = _USAGE_SCENE_LABELS.get(
                safe_int(usage_scene),
                str(usage_scene),
            )
        return payload
    return value


def normalize_json_object(value: Any) -> JsonObjectMap:
    normalized = normalize_json_value(value)
    if isinstance(normalized, JsonObjectMap):
        return normalized
    return JsonObjectMap()


def serialize_dt(
    app: Flask,
    value: datetime | None,
    *,
    timezone_name: str | None = None,
) -> str | None:
    return serialize_with_app_timezone(app, value, timezone_name)
