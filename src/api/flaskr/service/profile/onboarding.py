from __future__ import annotations

import json
from typing import Any

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.models import raise_param_error
from flaskr.service.common.profile_onboarding import (
    ALLOWED_PROFILE_ONBOARDING_VARIABLE_KEYS,
    PROFILE_ONBOARDING_STATE_KEY,
    load_profile_onboarding_config_payload,
)
from flaskr.service.profile.dtos import ProfileToSave
from flaskr.service.profile.funcs import (
    check_text_content,
    get_user_profiles,
    save_user_profiles,
)
from flaskr.service.profile.models import VariableValue
from flaskr.util.uuid import generate_id


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _has_onboarding_state(user_id: str) -> bool:
    return (
        VariableValue.query.filter(
            VariableValue.user_bid == user_id,
            VariableValue.shifu_bid == "",
            VariableValue.key == PROFILE_ONBOARDING_STATE_KEY,
            VariableValue.deleted == 0,
        ).first()
        is not None
    )


def _write_onboarding_state(
    app: Flask, user_id: str, *, skipped: bool, version: int
) -> None:
    state_payload = {
        "status": "skipped" if skipped else "completed",
        "version": version,
        "updated_at": _now_iso(),
    }
    db.session.add(
        VariableValue(
            variable_value_bid=generate_id(app),
            user_bid=user_id,
            shifu_bid="",
            variable_bid="",
            key=PROFILE_ONBOARDING_STATE_KEY,
            value=json.dumps(state_payload, ensure_ascii=False),
            deleted=0,
        )
    )


def _current_values_for_response(app: Flask, user_id: str) -> dict[str, str]:
    profiles = get_user_profiles(app, user_id, "")
    return {
        key: str(profiles.get(key) or "")
        for key in ALLOWED_PROFILE_ONBOARDING_VARIABLE_KEYS
    }


def get_profile_onboarding_status(app: Flask, *, user_id: str) -> dict[str, Any]:
    config_payload = load_profile_onboarding_config_payload()
    enabled = bool(config_payload.get("enabled")) and bool(
        str(config_payload.get("markdownflow") or "").strip()
    )
    return {
        "enabled": enabled,
        "should_show": enabled and not _has_onboarding_state(user_id),
        "markdownflow": str(config_payload.get("markdownflow") or ""),
        "allowed_variable_keys": list(ALLOWED_PROFILE_ONBOARDING_VARIABLE_KEYS),
        "current_values": _current_values_for_response(app, user_id),
    }


def _normalize_submitted_variables(raw_variables: Any) -> dict[str, str]:
    if raw_variables is None:
        return {}
    if not isinstance(raw_variables, dict):
        raise_param_error("variables")
    invalid_keys = set(raw_variables).difference(
        ALLOWED_PROFILE_ONBOARDING_VARIABLE_KEYS
    )
    if invalid_keys:
        raise_param_error("variables")
    return {
        key: str(value or "").strip()
        for key, value in raw_variables.items()
        if key in ALLOWED_PROFILE_ONBOARDING_VARIABLE_KEYS and str(value or "").strip()
    }


def complete_profile_onboarding(
    app: Flask,
    *,
    user_id: str,
    skipped: bool,
    variables: dict[str, Any] | None,
) -> dict[str, Any]:
    config_payload = load_profile_onboarding_config_payload()
    normalized_variables = _normalize_submitted_variables(variables)
    if not skipped:
        nickname = normalized_variables.get("sys_user_nickname")
        if nickname and not check_text_content(app, user_id, nickname):
            raise_param_error("sys_user_nickname")
        background = normalized_variables.get("sys_user_background")
        if background and not check_text_content(app, user_id, background):
            raise_param_error("sys_user_background")
        save_user_profiles(
            app,
            user_id,
            "",
            [
                ProfileToSave(key=key, value=value, bid=None)
                for key, value in normalized_variables.items()
            ],
        )

    _write_onboarding_state(
        app,
        user_id,
        skipped=skipped,
        version=int(config_payload.get("version") or 0),
    )
    db.session.flush()
    return {
        "completed": True,
        "skipped": bool(skipped),
        "variables": normalized_variables,
    }
