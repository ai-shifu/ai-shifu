"""Shared low-level billing primitives for scalar, JSON, and datetime coercion."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from flask import has_app_context
from flaskr.common.config import get_config as get_common_config
from flaskr.service.config.funcs import get_config
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.util.datetime import to_utc_iso

from .consts import BILL_CONFIG_KEY_CREDIT_PRECISION, BILL_CONFIG_KEY_ENABLED
from .value_objects import JsonObjectMap

_USAGE_SCENE_LABELS = {
    BILL_USAGE_SCENE_DEBUG: "debug",
    BILL_USAGE_SCENE_PREVIEW: "preview",
    BILL_USAGE_SCENE_PROD: "production",
}
DEFAULT_BILL_CREDIT_PRECISION = 2
MAX_BILL_CREDIT_PRECISION = 10
DEFAULT_BILL_ENABLED = False


def normalize_bid(value: object) -> str:
    """Normalize BID."""
    return str(value or "").strip()


def to_decimal(value: object) -> Decimal:
    """Convert a value to the billing Decimal representation."""
    if isinstance(value, Decimal):
        return value
    if value in (None, ""):
        return Decimal(0)
    return Decimal(str(value))


def safe_int(value: object) -> int | None:
    """Convert a value to an integer, returning None when invalid."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def clamp_billing_credit_precision(
    value: object,
    *,
    default: int = DEFAULT_BILL_CREDIT_PRECISION,
) -> int:
    """Clamp billing credit precision."""
    candidate = safe_int(value)
    if candidate is None:
        candidate = default
    return max(0, min(int(candidate), MAX_BILL_CREDIT_PRECISION))


def get_billing_credit_precision(
    *,
    default: int = DEFAULT_BILL_CREDIT_PRECISION,
) -> int:
    """Return billing credit precision."""
    normalized_default = clamp_billing_credit_precision(default, default=default)
    if not has_app_context():
        return normalized_default
    return clamp_billing_credit_precision(
        get_config(BILL_CONFIG_KEY_CREDIT_PRECISION, normalized_default),
        default=normalized_default,
    )


def is_billing_enabled(*, default: bool = DEFAULT_BILL_ENABLED) -> bool:
    """Return whether billing enabled."""
    raw_value = get_common_config(BILL_CONFIG_KEY_ENABLED, default)
    return coerce_bool(raw_value, default=default)


def build_credit_quantizer(*, precision: int | None = None) -> Decimal:
    """Build credit quantizer."""
    normalized_precision = (
        get_billing_credit_precision()
        if precision is None
        else clamp_billing_credit_precision(precision)
    )
    return Decimal(1).scaleb(-normalized_precision)


def quantize_credit_amount(
    value: object,
    *,
    precision: int | None = None,
) -> Decimal:
    """Quantize credit amount."""
    return to_decimal(value).quantize(
        build_credit_quantizer(precision=precision),
        rounding=ROUND_HALF_UP,
    )


def credit_decimal_to_number(
    value: object,
    *,
    precision: int | None = None,
) -> int | float:
    """Convert a credit Decimal to an API-safe number."""
    normalized = quantize_credit_amount(value, precision=precision)
    if normalized == normalized.to_integral():
        return int(normalized)
    return float(normalized)


def decimal_to_number(value: object) -> int | float:
    """Convert a numeric value to an API-safe integer or float."""
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


def coerce_bool(value: object, *, default: bool = False) -> bool:
    """Coerce bool."""
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def safe_to_positive_int(value: object, *, default: int) -> int:
    """Return a positive integer or the supplied default."""
    candidate = safe_int(value)
    if candidate is None or candidate <= 0:
        return default
    return candidate


def coerce_datetime(value: object) -> datetime | None:
    """Coerce datetime."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return datetime.fromtimestamp(value, UTC).replace(tzinfo=None)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        epoch_seconds = int(text)
        if epoch_seconds <= 0:
            return None
        return datetime.fromtimestamp(epoch_seconds, UTC).replace(tzinfo=None)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def normalize_mysql_datetime(value: datetime) -> datetime:
    """Normalize to MySQL DATETIME(0)'s default fractional-second rounding."""
    if value.microsecond >= 500_000:
        value = value + timedelta(seconds=1)
    return value.replace(microsecond=0)


def normalize_json_value(value: object) -> object:
    """Normalize JSON value."""
    if isinstance(value, Decimal):
        return decimal_to_number(value)
    if isinstance(value, datetime):
        return to_utc_iso(value)
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


def normalize_json_object(value: object) -> JsonObjectMap:
    """Normalize JSON object."""
    normalized = normalize_json_value(value)
    if isinstance(normalized, JsonObjectMap):
        return normalized
    return JsonObjectMap()
