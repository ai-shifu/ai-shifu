"""Phone identifier normalization helpers."""

from __future__ import annotations

import re


SMS_MOBILE_PATTERN = re.compile(r"^1\d{10}$")


def normalize_phone_identifier(phone: str | None) -> str:
    """Normalize phone identifiers used by auth and import flows."""

    normalized = str(phone or "").strip()
    if normalized.startswith("+86"):
        normalized = normalized[3:].strip()
    return normalized


def is_valid_sms_mobile(phone: str | None) -> bool:
    """Return whether a phone identifier is valid for SMS delivery in China."""

    return bool(SMS_MOBILE_PATTERN.fullmatch(normalize_phone_identifier(phone)))
