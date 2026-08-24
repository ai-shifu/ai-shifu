"""Validate and persist profile-onboarding configuration."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from flaskr.service.common.models import raise_param_error
from flaskr.service.config.funcs import add_config, get_config
from flaskr.util.datetime import now_utc, to_utc_iso

if TYPE_CHECKING:
    from flask import Flask

PROFILE_ONBOARDING_CONFIG_KEY = "PROFILE_ONBOARDING_FLOW"
PROFILE_ONBOARDING_STATE_KEY = "_sys_profile_onboarding_state"
ALLOWED_PROFILE_ONBOARDING_VARIABLE_KEYS = (
    "sys_user_nickname",
    "sys_user_style",
    "sys_user_background",
)

_INTERACTION_VARIABLE_PATTERN = re.compile(r"%\{\{\s*([^}\s]+)\s*\}\}")


def _now_iso() -> str:
    return to_utc_iso(now_utc().replace(microsecond=0)) or ""


def _default_config_payload() -> dict[str, object]:
    return {
        "enabled": False,
        "markdownflow": "",
        "version": 0,
        "updated_by": "",
        "updated_at": "",
    }


def normalize_profile_onboarding_config_payload(payload: object) -> dict[str, object]:
    """Normalize profile onboarding config payload."""
    base = _default_config_payload()
    if isinstance(payload, dict):
        base.update(
            {
                "enabled": bool(payload.get("enabled", False)),
                "markdownflow": str(payload.get("markdownflow") or ""),
                "version": int(payload.get("version") or 0),
                "updated_by": str(payload.get("updated_by") or ""),
                "updated_at": str(payload.get("updated_at") or ""),
            }
        )
    return base


def load_profile_onboarding_config_payload() -> dict[str, object]:
    """Load profile onboarding config payload."""
    raw_value = get_config(
        PROFILE_ONBOARDING_CONFIG_KEY,
        json.dumps(_default_config_payload(), ensure_ascii=False),
    )
    if isinstance(raw_value, dict):
        return normalize_profile_onboarding_config_payload(raw_value)
    try:
        return normalize_profile_onboarding_config_payload(
            json.loads(raw_value or "{}")
        )
    except (TypeError, ValueError):
        return _default_config_payload()


def save_profile_onboarding_config_payload(
    app: Flask, payload: dict[str, object], *, updated_by: str
) -> None:
    """Persist profile onboarding config payload."""
    add_config(
        app,
        PROFILE_ONBOARDING_CONFIG_KEY,
        json.dumps(payload, ensure_ascii=False),
        is_secret=False,
        remark="Profile onboarding MarkdownFlow configuration",
        updated_by=updated_by,
    )


def extract_profile_onboarding_variable_keys(markdownflow: str) -> set[str]:
    """Extract profile onboarding variable keys."""
    return {
        match.group(1).strip()
        for match in _INTERACTION_VARIABLE_PATTERN.finditer(markdownflow or "")
        if match.group(1).strip()
    }


def validate_profile_onboarding_markdownflow(markdownflow: str) -> None:
    """Validate profile onboarding markdownflow."""
    keys = extract_profile_onboarding_variable_keys(markdownflow)
    invalid_keys = keys.difference(ALLOWED_PROFILE_ONBOARDING_VARIABLE_KEYS)
    if invalid_keys:
        raise_param_error("markdownflow")


def build_profile_onboarding_config_response(
    payload: dict[str, object],
) -> dict[str, object]:
    """Build profile onboarding config response."""
    normalized = normalize_profile_onboarding_config_payload(payload)
    return {
        **normalized,
        "allowed_variable_keys": list(ALLOWED_PROFILE_ONBOARDING_VARIABLE_KEYS),
    }


def get_profile_onboarding_config() -> dict[str, object]:
    """Return profile onboarding config."""
    return build_profile_onboarding_config_response(
        load_profile_onboarding_config_payload()
    )


def update_profile_onboarding_config(
    app: Flask,
    *,
    payload: dict[str, object],
    operator_user_bid: str,
) -> dict[str, object]:
    """Update profile onboarding config."""
    existing = load_profile_onboarding_config_payload()
    markdownflow = str(payload.get("markdownflow") or "")
    validate_profile_onboarding_markdownflow(markdownflow)
    next_payload = {
        "enabled": bool(payload.get("enabled", False)),
        "markdownflow": markdownflow,
        "version": int(existing.get("version") or 0) + 1,
        "updated_by": operator_user_bid or "system",
        "updated_at": _now_iso(),
    }
    save_profile_onboarding_config_payload(
        app, next_payload, updated_by=operator_user_bid or "system"
    )
    return build_profile_onboarding_config_response(next_payload)
