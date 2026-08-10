from __future__ import annotations

import json
from typing import Any

from flask import Flask
from flaskr.service.common.models import raise_param_error
from flaskr.service.config.funcs import add_config, get_config
from flaskr.util.datetime import now_utc, to_utc_iso

PROFILE_ONBOARDING_CONFIG_KEY = "PROFILE_ONBOARDING_FLOW"
PROFILE_ONBOARDING_STATE_KEY = "_sys_profile_onboarding_state"
PROFILE_ONBOARDING_SCENE_KEY = "profile_onboarding"
PROFILE_ONBOARDING_VERSION = "profile-v2"
PROFILE_ONBOARDING_DOCUMENT_PROMPT_MAX_CODEPOINTS = 10_000
PROFILE_ONBOARDING_CONFIG_MAX_UTF8_BYTES = 65_535
ALLOWED_PROFILE_ONBOARDING_VARIABLE_KEYS = (
    "sys_user_nickname",
    "sys_user_style",
    "sys_user_background",
)


def _now_iso() -> str:
    return to_utc_iso(now_utc().replace(microsecond=0)) or ""


def _default_config_payload() -> dict[str, Any]:
    return {
        "enabled": False,
        "markdownflow": "",
        "document_prompt": "",
        "revision": 0,
        "updated_by": "",
        "updated_at": "",
    }


def normalize_profile_onboarding_config_payload(payload: Any) -> dict[str, Any]:
    base = _default_config_payload()
    if isinstance(payload, dict):
        base.update(
            {
                "enabled": bool(payload.get("enabled", False)),
                "markdownflow": str(payload.get("markdownflow") or ""),
                "document_prompt": str(payload.get("document_prompt") or ""),
                "revision": int(payload.get("revision") or payload.get("version") or 0),
                "updated_by": str(payload.get("updated_by") or ""),
                "updated_at": str(payload.get("updated_at") or ""),
            }
        )
    return base


def load_profile_onboarding_config_payload() -> dict[str, Any]:
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
    app: Flask, payload: dict[str, Any], *, updated_by: str
) -> None:
    serialized_payload = json.dumps(payload, ensure_ascii=False)
    if (
        len(serialized_payload.encode("utf-8"))
        > PROFILE_ONBOARDING_CONFIG_MAX_UTF8_BYTES
    ):
        raise_param_error("profile_onboarding_config")
    add_config(
        app,
        PROFILE_ONBOARDING_CONFIG_KEY,
        serialized_payload,
        is_secret=False,
        remark="Profile onboarding MarkdownFlow configuration",
        updated_by=updated_by,
    )


def validate_profile_onboarding_markdownflow(markdownflow: str) -> dict[str, Any]:
    if not markdownflow.strip():
        raise_param_error("markdownflow")
    from flaskr.service.profile_research.api import validate_profile_research_document

    try:
        return validate_profile_research_document(markdownflow)
    except Exception:
        raise_param_error("markdownflow")


def build_profile_onboarding_config_response(
    payload: dict[str, Any],
) -> dict[str, Any]:
    normalized = normalize_profile_onboarding_config_payload(payload)
    return {
        **normalized,
        "config_revision": normalized["revision"],
        "version": normalized["revision"],
        "allowed_variable_keys": list(ALLOWED_PROFILE_ONBOARDING_VARIABLE_KEYS),
    }


def get_profile_onboarding_config() -> dict[str, Any]:
    return build_profile_onboarding_config_response(
        load_profile_onboarding_config_payload()
    )


def update_profile_onboarding_config(
    app: Flask,
    *,
    payload: dict[str, Any],
    operator_user_bid: str,
) -> dict[str, Any]:
    existing = load_profile_onboarding_config_payload()
    if not isinstance(payload.get("enabled", False), bool):
        raise_param_error("enabled")
    raw_markdownflow = payload.get("markdownflow", "")
    if not isinstance(raw_markdownflow, str):
        raise_param_error("markdownflow")
    markdownflow = raw_markdownflow.strip()
    if "document_prompt" in payload:
        raw_document_prompt = payload["document_prompt"]
        if not isinstance(raw_document_prompt, str):
            raise_param_error("document_prompt")
        document_prompt = raw_document_prompt.strip()
        if len(document_prompt) > PROFILE_ONBOARDING_DOCUMENT_PROMPT_MAX_CODEPOINTS:
            raise_param_error("document_prompt")
    else:
        document_prompt = str(existing.get("document_prompt") or "")
    if markdownflow:
        validate_profile_onboarding_markdownflow(markdownflow)
    elif payload.get("enabled", False):
        raise_param_error("markdownflow")
    next_payload = {
        "enabled": bool(payload.get("enabled", False)),
        "markdownflow": markdownflow,
        "document_prompt": document_prompt,
        "revision": int(existing.get("revision") or 0) + 1,
        "updated_by": operator_user_bid or "system",
        "updated_at": _now_iso(),
    }
    save_profile_onboarding_config_payload(
        app, next_payload, updated_by=operator_user_bid or "system"
    )
    return build_profile_onboarding_config_response(next_payload)
