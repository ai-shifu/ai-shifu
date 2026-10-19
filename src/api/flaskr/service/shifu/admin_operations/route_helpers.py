"""Parse and validate operator admin-operation request parameters.

These helpers are shared by every operator route module and remain importable
from ``flaskr.service.shifu.admin_operations.route``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from flask import request
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.util.datetime import parse_naive_utc

MAX_CONTACT_LENGTH = 320
PHONE_PATTERN = re.compile(r"^\d{11}$")
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
OPERATOR_USER_STATUS_VALUES = {
    "unregistered",
    "registered",
    "trial",
    "paid",
    "cancelled",
}
OPERATOR_USER_ROLE_VALUES = {"operator", "creator", "learner", "regular"}
PROMOTION_COUPON_STATUS_VALUES = {"inactive", "not_started", "active", "expired"}
PROMOTION_CAMPAIGN_STATUS_VALUES = {"inactive", "not_started", "active", "ended"}
REFERRAL_CAMPAIGN_STATUS_VALUES = {"inactive", "not_started", "active", "ended"}
PROMOTION_COUPON_USAGE_STATUS_VALUES = {"901", "902", "903", "904"}
CREDIT_NOTIFICATION_STATUS_VALUES = {
    "pending",
    "sent",
    "skipped",
    "skipped_no_mobile",
    "skipped_opt_out",
    "suppressed_duplicate",
    "failed_provider",
}
CREDIT_NOTIFICATION_DELIVERY_STATUS_VALUES = {
    "pending",
    "sent",
    "failed",
    "not_sent",
}
CREDIT_NOTIFICATION_SKIP_REASON_VALUES = {
    "contact",
    "duplicate",
    "policy",
    "stale",
    "template_params",
}


def _parse_datetime_filter(
    value: str, *, field_name: str, is_end: bool = False
) -> datetime | None:
    if not value:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    for datetime_format in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = parse_naive_utc(normalized, datetime_format)
            if datetime_format == "%Y-%m-%d":
                if is_end:
                    parsed = parsed.replace(hour=23, minute=59, second=59)
                else:
                    parsed = parsed.replace(hour=0, minute=0, second=0)
        except ValueError:
            continue
        else:
            return parsed
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        raise_param_error(field_name)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _normalize_query_text(raw_value: object) -> str:
    return str(raw_value or "").strip()


def _parse_choice_query_param(
    raw_value: object,
    *,
    field_name: str,
    allowed_values: set[str],
) -> str:
    normalized = _normalize_query_text(raw_value).lower()
    if not normalized:
        return ""
    if normalized not in allowed_values:
        raise_param_error(field_name)
    return normalized


def _parse_digit_query_param(raw_value: object, *, field_name: str) -> str:
    normalized = _normalize_query_text(raw_value)
    if not normalized:
        return ""
    if not normalized.isdigit():
        raise_param_error(field_name)
    return normalized


def _validate_datetime_range(
    start_time: datetime | None,
    end_time: datetime | None,
    *,
    field_name: str,
) -> None:
    if start_time is not None and end_time is not None and start_time > end_time:
        raise_param_error(field_name)


def _parse_boolean_query_param(
    raw_value: object,
    *,
    field_name: str,
    default: bool = False,
) -> bool:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    normalized = str(raw_value).strip().lower()
    if not normalized:
        return default
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise_param_error(f"{field_name} is not a boolean")
    return None


def _parse_positive_query_int(
    raw_value: object,
    *,
    field_name: str,
    default: int,
    minimum: int = 1,
) -> int:
    if raw_value is None:
        return default
    try:
        parsed_value = int(raw_value)
    except (TypeError, ValueError):
        raise_param_error(field_name)
    if parsed_value < minimum:
        raise_param_error(field_name)
    return parsed_value


def _normalize_contact_type(raw_type: str) -> str:
    """Normalize the incoming contact type value."""
    return (raw_type or "").strip().lower()


def _require_operator() -> None:
    user = getattr(request, "user", None)
    if not getattr(user, "is_operator", False):
        raise_error("server.shifu.noPermission")


def _normalize_contacts(raw_contacts: object) -> list[str]:
    """Split and normalize contact identifiers from request payloads."""
    if isinstance(raw_contacts, str):
        items = re.split(r"[,\uFF0C\n]", raw_contacts)
    elif isinstance(raw_contacts, (list, tuple, set)):
        items = list(raw_contacts)
    else:
        items = []
    normalized = []
    for item in items:
        if item is None:
            continue
        trimmed = str(item).strip()
        if trimmed:
            normalized.append(trimmed)
    return normalized


def _validate_contacts(contact_type: str, contacts: list[str]) -> list[str]:
    """Validate and deduplicate contact identifiers."""
    normalized: list[str] = []
    seen: set[str] = set()
    for contact in contacts:
        if not contact or len(contact) > MAX_CONTACT_LENGTH:
            raise_param_error("contact")
        candidate = contact.lower() if contact_type == "email" else contact
        if candidate in seen:
            continue
        seen.add(candidate)
        if contact_type == "phone":
            if not PHONE_PATTERN.match(contact):
                raise_param_error("mobile")
        elif contact_type == "email" and not EMAIL_PATTERN.match(candidate):
            raise_param_error("email")
        normalized.append(candidate)
    return normalized
