from __future__ import annotations

import hashlib
import json
from typing import Any

from flask import Flask
from flaskr.api.check import CHECK_RESULT_PASS, CHECK_RESULT_REJECT, check_text
from flaskr.dao.uow import unit_of_work
from flaskr.service.check_risk.api import add_risk_control_result
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.util.datetime import now_utc, to_utc_iso
from flaskr.util.uuid import generate_id

LEARNER_PROFILE_MAX_LENGTH = 1000
LEARNER_PROFILE_CHECK_STRATEGY = "check_learner_profile"


def _learner_profile_audit_text(learner_profile: str) -> str:
    """Return linkage metadata without duplicating the learner's profile text."""

    return json.dumps(
        {
            "content": "[redacted]",
            "sha256": hashlib.sha256(learner_profile.encode("utf-8")).hexdigest(),
            "unicode_code_points": len(learner_profile),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _learner_profile_audit_response(result: Any) -> str:
    """Allowlist moderation verdict details and discard the provider raw payload."""

    return json.dumps(
        {
            "risk_label_ids": list(getattr(result, "risk_label_ids", []) or []),
            "risk_labels": [
                str(label) for label in (getattr(result, "risk_labels", []) or [])
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def check_text_content(app: Flask, user_id: str, learner_profile: str) -> bool:
    """Moderate a profile while keeping its canonical row as the only local raw copy."""

    check_id = generate_id(app)
    result = check_text(app, check_id, learner_profile, user_id)
    add_risk_control_result(
        app,
        check_id,
        user_id,
        _learner_profile_audit_text(learner_profile),
        result.provider,
        result.check_result,
        _learner_profile_audit_response(result),
        1 if result.check_result == CHECK_RESULT_PASS else 0,
        LEARNER_PROFILE_CHECK_STRATEGY,
    )
    return result.check_result != CHECK_RESULT_REJECT


def load_learner_profile_user(user_id: str) -> UserEntity:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        raise_error("server.user.userNotLogin")
    user = UserEntity.query.filter(
        UserEntity.user_bid == normalized_user_id,
        UserEntity.deleted == 0,
    ).first()
    if user is None:
        raise_error("server.user.userNotLogin")
    return user


def normalize_learner_profile(raw_profile: Any) -> str:
    if not isinstance(raw_profile, str):
        raise_param_error("learner_profile")
    normalized = raw_profile.strip()
    if not normalized or len(normalized) > LEARNER_PROFILE_MAX_LENGTH:
        raise_param_error("learner_profile")
    return normalized


def serialize_learner_profile(user: UserEntity) -> dict[str, Any]:
    profile = str(user.learner_profile or "")
    return {
        "learner_profile": profile,
        "learner_profile_updated_at": to_utc_iso(user.learner_profile_updated_at),
        "has_learner_profile": bool(profile),
        "max_length": LEARNER_PROFILE_MAX_LENGTH,
    }


def get_learner_profile(*, user_id: str) -> dict[str, Any]:
    return serialize_learner_profile(load_learner_profile_user(user_id))


def apply_learner_profile(user: UserEntity, learner_profile: str) -> bool:
    if str(user.learner_profile or "") == learner_profile:
        return False
    user.learner_profile = learner_profile
    user.learner_profile_updated_at = now_utc()
    return True


def validate_learner_profile_content(
    app: Flask,
    *,
    user_id: str,
    learner_profile: str,
) -> str:
    normalized = normalize_learner_profile(learner_profile)
    if not check_text_content(app, user_id, normalized):
        raise_param_error("learner_profile")
    return normalized


def replace_learner_profile(
    app: Flask,
    *,
    user_id: str,
    learner_profile: str,
) -> dict[str, Any]:
    normalized = validate_learner_profile_content(
        app,
        user_id=user_id,
        learner_profile=learner_profile,
    )

    with unit_of_work():
        user = load_learner_profile_user(user_id)
        apply_learner_profile(user, normalized)
    return serialize_learner_profile(user)


def clear_learner_profile(*, user_id: str) -> dict[str, Any]:
    with unit_of_work():
        user = load_learner_profile_user(user_id)
        if user.learner_profile or user.learner_profile_updated_at is not None:
            user.learner_profile = ""
            user.learner_profile_updated_at = None
    return serialize_learner_profile(user)
