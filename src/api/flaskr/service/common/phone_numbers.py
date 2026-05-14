"""Phone identifier normalization helpers."""

from __future__ import annotations


def normalize_phone_identifier(phone: str | None) -> str:
    """Normalize phone identifiers used by auth and import flows."""

    normalized = str(phone or "").strip()
    if normalized.startswith("+86"):
        normalized = normalized[3:].strip()
    return normalized
