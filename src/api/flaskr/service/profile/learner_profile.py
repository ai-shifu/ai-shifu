from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, TypeVar

from flask import Flask
from flaskr.api.check import CHECK_RESULT_PASS, check_text
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.check_risk.api import add_risk_control_result
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.user.models import (
    AuthCredential,
    UserInfo as UserEntity,
)
from flaskr.service.user.models import (
    UserOnboardingState,
)
from flaskr.util.datetime import now_utc, to_utc_iso
from flaskr.util.uuid import generate_id
from sqlalchemy.exc import IntegrityError

LEARNER_PROFILE_MAX_LENGTH = 1000
LEARNER_PROFILE_CHECK_STRATEGY = "check_learner_profile"
LEARNER_PROFILE_STATUS_COMPLETED = "completed"
LEARNER_PROFILE_TRIGGER_SOURCES = frozenset({"guided", "pasted", "settings"})
PROFILE_ONBOARDING_SCENE_KEY = "profile_onboarding"
PROFILE_ONBOARDING_VERSION = "profile-v2"

_T = TypeVar("_T")


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
    return result.check_result == CHECK_RESULT_PASS


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


def load_learner_profile_state(user_id: str) -> UserOnboardingState | None:
    return UserOnboardingState.query.filter(
        UserOnboardingState.user_bid == str(user_id or "").strip(),
        UserOnboardingState.scene_key == PROFILE_ONBOARDING_SCENE_KEY,
        UserOnboardingState.version == PROFILE_ONBOARDING_VERSION,
    ).first()


def merge_learner_profile_for_sign_in(
    *,
    source_user_id: str,
    target_user_id: str,
) -> None:
    """Copy canonical profile state into an existing signed-in account transaction."""

    normalized_source_id = str(source_user_id or "").strip()
    normalized_target_id = str(target_user_id or "").strip()
    if (
        not normalized_source_id
        or not normalized_target_id
        or normalized_source_id == normalized_target_id
    ):
        return

    source_user = UserEntity.query.filter(
        UserEntity.user_bid == normalized_source_id,
        UserEntity.deleted == 0,
    ).first()
    target_user = UserEntity.query.filter(
        UserEntity.user_bid == normalized_target_id,
        UserEntity.deleted == 0,
    ).first()
    if source_user is None or target_user is None:
        return

    source_identify = str(source_user.user_identify or "").strip()
    source_has_account_identifier = bool(
        "@" in source_identify
        or source_identify.isdigit()
        or AuthCredential.query.filter(
            AuthCredential.user_bid == normalized_source_id,
            AuthCredential.provider_name.in_(["phone", "email"]),
            AuthCredential.deleted == 0,
        ).first()
    )
    if source_has_account_identifier:
        return

    if load_learner_profile_state(normalized_target_id) is not None:
        return

    source_profile = str(source_user.learner_profile or "").strip()
    target_profile = str(target_user.learner_profile or "").strip()
    if source_profile and not target_profile:
        target_user.learner_profile = source_user.learner_profile
        target_user.learner_profile_updated_at = source_user.learner_profile_updated_at

    source_state = load_learner_profile_state(normalized_source_id)
    if source_state is None:
        return

    db.session.add(
        UserOnboardingState(
            user_bid=normalized_target_id,
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
            version=PROFILE_ONBOARDING_VERSION,
            status=source_state.status,
            trigger_source=source_state.trigger_source,
            completed_at=source_state.completed_at,
        )
    )


def has_learner_profile_or_state(user_id: str) -> bool:
    user = load_learner_profile_user(user_id)
    return bool(str(user.learner_profile or "").strip()) or (
        load_learner_profile_state(user_id) is not None
    )


def _apply_completed_state(
    *,
    user_id: str,
    trigger_source: str,
) -> UserOnboardingState:
    state = load_learner_profile_state(user_id)
    now = now_utc()
    if state is None:
        state = UserOnboardingState(
            user_bid=user_id,
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
            version=PROFILE_ONBOARDING_VERSION,
            status=LEARNER_PROFILE_STATUS_COMPLETED,
            trigger_source=trigger_source,
            completed_at=now,
        )
        db.session.add(state)
        return state

    previous_status = state.status
    state.status = LEARNER_PROFILE_STATUS_COMPLETED
    state.trigger_source = trigger_source
    if (
        state.completed_at is None
        or previous_status != LEARNER_PROFILE_STATUS_COMPLETED
    ):
        state.completed_at = now
    return state


def _commit_with_state_race_retry(
    operation: Callable[[], _T],
    *,
    user_id: str,
) -> _T:
    def run_once() -> _T:
        with unit_of_work():
            result = operation()
            db.session.flush()
        return result

    try:
        return run_once()
    except IntegrityError:
        with unit_of_work():
            winner = load_learner_profile_state(user_id)
        if winner is None:
            raise
        return run_once()


def _serialize_completed_state(state: UserOnboardingState) -> dict[str, Any]:
    return {
        "handled": True,
        "completed": state.status == LEARNER_PROFILE_STATUS_COMPLETED,
        "skipped": False,
        "status": state.status,
        "trigger_source": state.trigger_source,
        "completed_at": to_utc_iso(state.completed_at),
        "version": state.version,
    }


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


def save_learner_profile(
    app: Flask,
    *,
    user_id: str,
    learner_profile: str,
    trigger_source: str,
) -> dict[str, Any]:
    normalized_trigger_source = str(trigger_source or "").strip()
    if normalized_trigger_source not in LEARNER_PROFILE_TRIGGER_SOURCES:
        raise_param_error("trigger_source")
    normalized = validate_learner_profile_content(
        app,
        user_id=user_id,
        learner_profile=learner_profile,
    )

    def operation() -> tuple[UserEntity, UserOnboardingState]:
        user = load_learner_profile_user(user_id)
        apply_learner_profile(user, normalized)
        state = _apply_completed_state(
            user_id=user_id,
            trigger_source=normalized_trigger_source,
        )
        return user, state

    user, state = _commit_with_state_race_retry(operation, user_id=user_id)
    return {
        **_serialize_completed_state(state),
        **serialize_learner_profile(user),
    }


def replace_learner_profile(
    app: Flask,
    *,
    user_id: str,
    learner_profile: str,
) -> dict[str, Any]:
    return save_learner_profile(
        app,
        user_id=user_id,
        learner_profile=learner_profile,
        trigger_source="settings",
    )


def clear_learner_profile(*, user_id: str) -> dict[str, Any]:
    def operation() -> tuple[UserEntity, UserOnboardingState]:
        user = load_learner_profile_user(user_id)
        if user.learner_profile or user.learner_profile_updated_at is not None:
            user.learner_profile = ""
            user.learner_profile_updated_at = None
        state = _apply_completed_state(user_id=user_id, trigger_source="settings")
        return user, state

    user, state = _commit_with_state_race_retry(operation, user_id=user_id)
    return {
        **_serialize_completed_state(state),
        **serialize_learner_profile(user),
    }
