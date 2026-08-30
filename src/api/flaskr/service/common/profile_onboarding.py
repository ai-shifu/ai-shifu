"""Validate and persist profile-onboarding configuration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from flask import current_app, has_app_context
from flaskr.i18n import get_locale_labels
from flaskr.service.common.models import AppError, raise_error, raise_param_error
from flaskr.service.common.profile_onboarding_prompt import (
    compile_profile_onboarding_assistant_prompt,
    localize_profile_onboarding_assistant_prompt,
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
        "assistant_prompts": {},
        "revision": 0,
        "updated_by": "",
        "updated_at": "",
    }


def normalize_profile_onboarding_config_payload(payload: object) -> dict[str, object]:
    """Normalize profile onboarding config payload."""
    base = _default_config_payload()
    if isinstance(payload, dict):
        raw_assistant_prompts = payload.get("assistant_prompts")
        assistant_prompts = (
            {
                locale.strip(): prompt.strip()
                for locale, prompt in raw_assistant_prompts.items()
                if isinstance(locale, str)
                and locale.strip()
                and isinstance(prompt, str)
                and prompt.strip()
            }
            if isinstance(raw_assistant_prompts, dict)
            else {}
        )
        base.update(
            {
                "enabled": bool(payload.get("enabled", False)),
                "markdownflow": str(payload.get("markdownflow") or ""),
                "assistant_prompt": str(payload.get("assistant_prompt") or ""),
                "assistant_prompts": assistant_prompts,
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
    assistant_prompts: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the canonical persisted onboarding configuration."""
    return {
        "enabled": enabled,
        "markdownflow": markdownflow,
        "assistant_prompt": assistant_prompt,
        "assistant_prompts": dict(assistant_prompts or {}),
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
        "assistant_prompts": normalized["assistant_prompts"],
        "config_revision": normalized["revision"],
        "updated_by": normalized["updated_by"],
        "updated_at": normalized["updated_at"],
    }


def get_profile_onboarding_config() -> dict[str, object]:
    """Return profile onboarding config."""
    return build_profile_onboarding_config_response(
        load_profile_onboarding_config_payload()
    )


def _supported_assistant_prompts(prompts: object) -> dict[str, str]:
    """Keep only non-empty prompts for locales in the current registry."""
    if not isinstance(prompts, dict):
        return {}
    return {
        locale: prompt.strip()
        for locale in get_locale_labels()
        if isinstance((prompt := prompts.get(locale)), str) and prompt.strip()
    }


def generate_profile_onboarding_assistant_prompt(
    app: Flask, *, markdownflow: str
) -> dict[str, str]:
    """Compile one editable master prompt without publishing configuration."""
    if not isinstance(markdownflow, str):
        raise_param_error("markdownflow")
    normalized_markdownflow = markdownflow.strip()
    validate_profile_onboarding_markdownflow(normalized_markdownflow)
    validate_profile_onboarding_config_payload_size(
        build_profile_onboarding_config_payload(
            enabled=False,
            markdownflow=normalized_markdownflow,
            revision=0,
            updated_by="system",
        )
    )
    assistant_prompt = compile_profile_onboarding_assistant_prompt(
        app, normalized_markdownflow
    )
    try:
        validate_profile_onboarding_config_payload_size(
            build_profile_onboarding_config_payload(
                enabled=False,
                markdownflow=normalized_markdownflow,
                revision=0,
                updated_by="system",
                assistant_prompt=assistant_prompt,
            )
        )
    except AppError:
        raise_error("server.profile.profileOnboardingPromptGenerationFailed")
    return {"assistant_prompt": assistant_prompt}


def _merge_missing_assistant_prompts(
    existing_prompts: dict[str, str], generated_prompts: dict[str, str]
) -> dict[str, str]:
    """Fill missing supported locales without rewriting existing translations."""
    merged: dict[str, str] = {}
    for locale in get_locale_labels():
        existing_prompt = existing_prompts.get(locale)
        merged[locale] = (
            existing_prompt.strip()
            if isinstance(existing_prompt, str) and existing_prompt.strip()
            else generated_prompts[locale]
        )
    return merged


def update_profile_onboarding_config(
    app: Flask,
    *,
    payload: dict[str, object],
    operator_user_bid: str,
) -> dict[str, object]:
    """Update profile onboarding config."""
    if set(payload) - {
        "enabled",
        "markdownflow",
        "assistant_prompt",
        "config_revision",
    }:
        raise_param_error("profile_onboarding_config")
    if "enabled" not in payload or not isinstance(payload["enabled"], bool):
        raise_param_error("enabled")
    if "markdownflow" not in payload or not isinstance(payload["markdownflow"], str):
        raise_param_error("markdownflow")
    raw_markdownflow = payload["markdownflow"]
    has_explicit_prompt = "assistant_prompt" in payload
    raw_assistant_prompt = payload.get("assistant_prompt", "")
    if not isinstance(raw_assistant_prompt, str):
        raise_param_error("assistant_prompt")
    has_explicit_revision = "config_revision" in payload
    raw_config_revision = payload.get("config_revision")
    if has_explicit_revision and (
        isinstance(raw_config_revision, bool)
        or not isinstance(raw_config_revision, int)
        or raw_config_revision < 0
    ):
        raise_param_error("config_revision")
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
    if has_explicit_revision and raw_config_revision != existing["revision"]:
        raise_error("server.profile.profileOnboardingConfigConflict")

    existing_assistant_prompt = str(existing.get("assistant_prompt") or "").strip()
    existing_assistant_prompts = dict(existing.get("assistant_prompts") or {})
    # The previous UI sent a blank prompt without a revision to request implicit
    # regeneration. During the backend-first rollout, preserve published text
    # for that sentinel because save paths must no longer compile the master.
    preserve_legacy_blank_prompt = (
        has_explicit_prompt
        and not has_explicit_revision
        and not explicit_prompt
        and bool(markdownflow)
    )
    assistant_prompt = (
        explicit_prompt
        if has_explicit_prompt and not preserve_legacy_blank_prompt
        else existing_assistant_prompt
    )
    enabled = bool(payload.get("enabled", False))
    if not markdownflow and assistant_prompt:
        raise_param_error("assistant_prompt")
    if enabled and not assistant_prompt:
        raise_param_error("assistant_prompt")
    missing_locales: set[str] = set()
    if not markdownflow:
        assistant_prompt = ""
        assistant_prompts: dict[str, str] = {}
        generate_localizations = False
        prompt_changed = bool(existing_assistant_prompt)
    else:
        prompt_changed = assistant_prompt != existing_assistant_prompt
        if not assistant_prompt:
            assistant_prompts = {}
            generate_localizations = False
        elif prompt_changed:
            assistant_prompts = {}
            generate_localizations = True
        else:
            assistant_prompts = _supported_assistant_prompts(existing_assistant_prompts)
            missing_locales = set(get_locale_labels()) - set(assistant_prompts)
            generate_localizations = bool(missing_locales)

    if markdownflow and generate_localizations:
        # Reject oversized input before spending a localization model call,
        # then check the complete JSON after every localized prompt is included.
        validate_profile_onboarding_config_payload_size(
            build_profile_onboarding_config_payload(
                enabled=enabled,
                markdownflow=markdownflow,
                revision=int(existing["revision"]) + 1,
                updated_by=operator_user_bid or "system",
                assistant_prompt=assistant_prompt,
            )
        )
    if generate_localizations:
        generated_prompts = (
            localize_profile_onboarding_assistant_prompt(app, assistant_prompt)
            if prompt_changed
            else localize_profile_onboarding_assistant_prompt(
                app,
                assistant_prompt,
                target_locales=missing_locales,
            )
        )
        assistant_prompts = (
            generated_prompts
            if prompt_changed
            else _merge_missing_assistant_prompts(
                existing_assistant_prompts, generated_prompts
            )
        )
    next_payload = build_profile_onboarding_config_payload(
        enabled=enabled,
        markdownflow=markdownflow,
        revision=int(existing.get("revision") or 0) + 1,
        updated_by=operator_user_bid or "system",
        assistant_prompt=assistant_prompt,
        assistant_prompts=assistant_prompts,
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
