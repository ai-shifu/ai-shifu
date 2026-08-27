"""Validate and persist profile-onboarding configuration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from flask import current_app, has_app_context
from flaskr.service.common.models import raise_param_error
from flaskr.service.common.profile_onboarding_prompt import (
    compile_profile_onboarding_assistant_prompt,
)
from flaskr.service.config.funcs import get_config
from flaskr.service.config.profile_onboarding import (
    assert_profile_onboarding_persistable,
    publish_profile_onboarding_database,
    read_profile_onboarding_database,
    read_profile_onboarding_effective_value,
)
from flaskr.util.datetime import now_utc, to_utc_iso

if TYPE_CHECKING:
    from flask import Flask

PROFILE_ONBOARDING_CONFIG_KEY = "PROFILE_ONBOARDING_FLOW"
PROFILE_ONBOARDING_CONFIG_MAX_UTF8_BYTES = 65_535


def _now_iso() -> str:
    return to_utc_iso(now_utc().replace(microsecond=0)) or ""


def _default_config_payload() -> dict[str, object]:
    return {
        "enabled": False,
        "markdownflow": "",
        "assistant_prompt": "",
        "revision": 0,
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
                "assistant_prompt": str(payload.get("assistant_prompt") or ""),
                "revision": int(payload.get("revision") or 0),
                "updated_by": str(payload.get("updated_by") or ""),
                "updated_at": str(payload.get("updated_at") or ""),
            }
        )
    return base


def load_profile_onboarding_config_payload() -> dict[str, object]:
    """Load profile onboarding config payload."""
    default = json.dumps(_default_config_payload(), ensure_ascii=False)
    raw_value = (
        read_profile_onboarding_effective_value(current_app, default)
        if has_app_context()
        else get_config(PROFILE_ONBOARDING_CONFIG_KEY, default)
    )
    if isinstance(raw_value, dict):
        return normalize_profile_onboarding_config_payload(raw_value)
    try:
        return normalize_profile_onboarding_config_payload(
            json.loads(raw_value or "{}")
        )
    except (TypeError, ValueError):
        return _default_config_payload()


def build_profile_onboarding_config_payload(
    *,
    enabled: bool,
    markdownflow: str,
    revision: int,
    updated_by: str,
    assistant_prompt: str = "",
) -> dict[str, Any]:
    """Build the canonical persisted onboarding configuration."""
    return {
        "enabled": enabled,
        "markdownflow": markdownflow,
        "assistant_prompt": assistant_prompt,
        "revision": revision,
        "updated_by": updated_by,
        "updated_at": _now_iso(),
    }


def validate_profile_onboarding_config_payload_size(
    payload: dict[str, Any],
) -> str:
    """Serialize and enforce the persisted configuration byte limit."""
    serialized_payload = json.dumps(payload, ensure_ascii=False)
    if (
        len(serialized_payload.encode("utf-8"))
        > PROFILE_ONBOARDING_CONFIG_MAX_UTF8_BYTES
    ):
        raise_param_error("profile_onboarding_config")
    return serialized_payload


def save_profile_onboarding_config_payload(
    app: Flask,
    payload: dict[str, Any],
    *,
    updated_by: str,
    expected_value: str | None = None,
) -> bool:
    """Persist a validated profile-onboarding configuration."""
    serialized_payload = validate_profile_onboarding_config_payload_size(payload)
    return publish_profile_onboarding_database(
        app,
        expected_value=expected_value,
        value=serialized_payload,
        updated_by=updated_by,
    )


def validate_profile_onboarding_markdownflow(markdownflow: str) -> dict[str, Any]:
    """Validate profile onboarding MarkdownFlow with the official runtime."""
    if not markdownflow.strip():
        raise_param_error("markdownflow")
    from flaskr.service.profile_research.api import validate_profile_research_document

    try:
        return validate_profile_research_document(markdownflow)
    except Exception:
        raise_param_error("markdownflow")


def build_profile_onboarding_config_response(
    payload: dict[str, object],
) -> dict[str, object]:
    """Build profile onboarding config response."""
    normalized = normalize_profile_onboarding_config_payload(payload)
    return {
        "enabled": normalized["enabled"],
        "markdownflow": normalized["markdownflow"],
        "assistant_prompt": normalized["assistant_prompt"],
        "config_revision": normalized["revision"],
        "updated_by": normalized["updated_by"],
        "updated_at": normalized["updated_at"],
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
    if set(payload) - {"enabled", "markdownflow", "assistant_prompt"}:
        raise_param_error("profile_onboarding_config")
    if not isinstance(payload.get("enabled", False), bool):
        raise_param_error("enabled")
    raw_markdownflow = payload.get("markdownflow", "")
    if not isinstance(raw_markdownflow, str):
        raise_param_error("markdownflow")
    has_explicit_prompt = "assistant_prompt" in payload
    raw_assistant_prompt = payload.get("assistant_prompt", "")
    if not isinstance(raw_assistant_prompt, str):
        raise_param_error("assistant_prompt")
    explicit_prompt = raw_assistant_prompt.strip()
    markdownflow = raw_markdownflow.strip()
    if explicit_prompt and not markdownflow:
        raise_param_error("assistant_prompt")
    if markdownflow:
        validate_profile_onboarding_markdownflow(markdownflow)
    elif payload.get("enabled", False):
        raise_param_error("markdownflow")
    assert_profile_onboarding_persistable()
    expected_value = read_profile_onboarding_database(app)
    try:
        existing = normalize_profile_onboarding_config_payload(
            json.loads(expected_value) if expected_value else {}
        )
    except (TypeError, ValueError):
        existing = _default_config_payload()
    assistant_prompt = str(existing.get("assistant_prompt") or "")
    defer_missing_prompt_while_disabling = (
        not bool(payload.get("enabled", False))
        and markdownflow == existing["markdownflow"]
        and not assistant_prompt
    )
    if explicit_prompt:
        assistant_prompt = explicit_prompt
    elif markdownflow and (
        not defer_missing_prompt_while_disabling
        and (
            has_explicit_prompt
            or markdownflow != existing["markdownflow"]
            or not assistant_prompt
        )
    ):
        # Reject oversized input before spending a model call, then check the
        # complete JSON again after the generated prompt is included.
        validate_profile_onboarding_config_payload_size(
            build_profile_onboarding_config_payload(
                enabled=bool(payload.get("enabled", False)),
                markdownflow=markdownflow,
                revision=int(existing["revision"]) + 1,
                updated_by=operator_user_bid or "system",
            )
        )
        assistant_prompt = compile_profile_onboarding_assistant_prompt(
            app, markdownflow
        )
    if not markdownflow:
        assistant_prompt = ""
    next_payload = build_profile_onboarding_config_payload(
        enabled=bool(payload.get("enabled", False)),
        markdownflow=markdownflow,
        revision=int(existing.get("revision") or 0) + 1,
        updated_by=operator_user_bid or "system",
        assistant_prompt=assistant_prompt,
    )
    cache_refresh_pending = save_profile_onboarding_config_payload(
        app,
        next_payload,
        updated_by=operator_user_bid or "system",
        expected_value=expected_value,
    )
    response = build_profile_onboarding_config_response(next_payload)
    if cache_refresh_pending:
        response["cache_refresh_pending"] = True
    return response
