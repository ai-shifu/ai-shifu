"""Shared parsing for deployment-owned TTS voice allowlists."""

from __future__ import annotations

import json


def parse_voice_list_json(value: object, *, env_name: str) -> list[dict[str, str]]:
    """Parse and normalize a JSON voice allowlist from deployment configuration.

    The value must be a JSON array (or an already-decoded list) of objects with
    non-empty ``value`` and ``label`` fields. Whitespace is stripped, duplicate
    voice ids are rejected, and ``env_name`` is used in error messages so the
    operator knows which variable to fix.
    """
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            message = f"{env_name} must be valid JSON"
            raise ValueError(message) from exc
    else:
        payload = value

    if payload in (None, ""):
        return []
    if not isinstance(payload, list):
        message = f"{env_name} must be a JSON array"
        raise TypeError(message)

    voices: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            message = f"{env_name} voice at index {index} must be an object"
            raise TypeError(message)
        voice_id = str(item.get("value") or "").strip()
        label = str(item.get("label") or "").strip()
        if not voice_id or not label:
            message = (
                f"{env_name} voice at index {index} requires non-empty value and label"
            )
            raise ValueError(message)
        if voice_id in seen_ids:
            message = f"Duplicate {env_name} voice id: {voice_id}"
            raise ValueError(message)
        seen_ids.add(voice_id)
        voices.append({"value": voice_id, "label": label})
    return voices
