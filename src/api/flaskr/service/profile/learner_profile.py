from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, TypeVar

from flask import Flask
from flaskr.api.check import (
    CHECK_RESULT_PASS,
    CHECK_RESULT_REJECT,
    check_text,
)
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.check_risk.api import add_risk_control_result
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.phone_numbers import (
    is_valid_sms_mobile,
    normalize_phone_identifier,
)
from flaskr.service.profile.constants import (
    LEGACY_LEARNER_PROFILE_KEYS,
    SYS_USER_NICKNAME,
)
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import (
    AuthCredential,
    UserOnboardingState,
)
from flaskr.service.user.models import (
    UserInfo as UserEntity,
)
from flaskr.util.datetime import now_utc, to_utc_iso
from flaskr.util.uuid import generate_id
from sqlalchemy.exc import IntegrityError

LEARNER_PROFILE_MAX_LENGTH = 1000
LEARNER_PROFILE_NICKNAME_MAX_LENGTH = 64
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
    return result.check_result != CHECK_RESULT_REJECT


def load_learner_profile_user(
    user_id: str,
    *,
    for_update: bool = False,
) -> UserEntity:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        raise_error("server.user.userNotLogin")
    query = UserEntity.query.filter(
        UserEntity.user_bid == normalized_user_id,
        UserEntity.deleted == 0,
    )
    if for_update:
        query = query.populate_existing().with_for_update()
    user = query.first()
    if user is None:
        raise_error("server.user.userNotLogin")
    return user


def normalize_learner_profile(raw_profile: Any) -> str:
    if not isinstance(raw_profile, str):
        raise_param_error("learner_profile")
    normalized = raw_profile.strip()
    if len(normalized) > LEARNER_PROFILE_MAX_LENGTH:
        raise_param_error("learner_profile")
    return normalized


def normalize_learner_profile_nickname(raw_nickname: Any) -> str:
    if not isinstance(raw_nickname, str):
        raise_param_error("nickname")
    normalized = raw_nickname.strip()
    if len(normalized) > LEARNER_PROFILE_NICKNAME_MAX_LENGTH:
        raise_param_error("nickname")
    return normalized


def serialize_learner_profile(user: UserEntity) -> dict[str, Any]:
    profile = str(user.learner_profile or "")
    nickname = str(user.nickname or "").strip()
    if nickname and _nickname_matches_account_identifier(user, nickname):
        nickname = ""
    return {
        "learner_profile": profile,
        "learner_profile_updated_at": to_utc_iso(user.learner_profile_updated_at),
        "has_learner_profile": bool(profile),
        "max_length": LEARNER_PROFILE_MAX_LENGTH,
        "nickname": nickname,
        "nickname_max_length": LEARNER_PROFILE_NICKNAME_MAX_LENGTH,
    }


def _identifier_variants(value: Any) -> set[str]:
    normalized = str(value or "").strip()
    if not normalized:
        return set()

    variants = {normalized.casefold()}
    normalized_phone = normalize_phone_identifier(normalized)
    if is_valid_sms_mobile(normalized_phone):
        variants.add(normalized_phone.casefold())
    return variants


def _nickname_matches_account_identifier(user: UserEntity, nickname: str) -> bool:
    nickname_variants = _identifier_variants(nickname)
    if not nickname_variants:
        return False

    account_identifiers = _identifier_variants(user.user_bid)
    account_identifiers.update(_identifier_variants(user.user_identify))
    credentials = AuthCredential.query.filter(
        AuthCredential.user_bid == user.user_bid,
        AuthCredential.provider_name.in_(["phone", "email"]),
        AuthCredential.deleted == 0,
    ).all()
    for credential in credentials:
        account_identifiers.update(_identifier_variants(credential.identifier))
        account_identifiers.update(_identifier_variants(credential.subject_id))
    return not nickname_variants.isdisjoint(account_identifiers)


def _load_legacy_learner_profile_values(user: UserEntity) -> dict[str, str]:
    rows = (
        VariableValue.query.filter(
            VariableValue.user_bid == user.user_bid,
            VariableValue.shifu_bid == "",
            VariableValue.key.in_(LEGACY_LEARNER_PROFILE_KEYS),
            VariableValue.deleted == 0,
        )
        .order_by(VariableValue.id.desc())
        .all()
    )
    latest_values: dict[str, str] = {}
    legacy_nickname = ""
    seen_keys: set[str] = set()
    for row in rows:
        if row.key in seen_keys:
            continue
        seen_keys.add(row.key)
        value = str(row.value or "").strip()
        if row.key == SYS_USER_NICKNAME:
            legacy_nickname = value
            continue
        if value:
            latest_values[row.key] = value

    canonical_nickname = str(user.nickname or "").strip()
    if canonical_nickname and not _nickname_matches_account_identifier(
        user,
        canonical_nickname,
    ):
        latest_values[SYS_USER_NICKNAME] = canonical_nickname
    elif legacy_nickname and not _nickname_matches_account_identifier(
        user,
        legacy_nickname,
    ):
        latest_values[SYS_USER_NICKNAME] = legacy_nickname
    return latest_values


def get_learner_profile(*, user_id: str) -> dict[str, Any]:
    user = load_learner_profile_user(user_id)
    serialized = serialize_learner_profile(user)
    has_handled_profile = (
        not serialized["has_learner_profile"]
        and load_learner_profile_state(user.user_bid) is not None
    )
    serialized["legacy_profile_values"] = (
        {}
        if serialized["has_learner_profile"] or has_handled_profile
        else _load_legacy_learner_profile_values(user)
    )
    return serialized


def apply_learner_profile(user: UserEntity, learner_profile: str) -> bool:
    if learner_profile:
        if str(user.learner_profile or "") == learner_profile:
            return False
        user.learner_profile = learner_profile
        user.learner_profile_updated_at = now_utc()
        return True

    if not user.learner_profile and user.learner_profile_updated_at is None:
        return False
    user.learner_profile = ""
    user.learner_profile_updated_at = None
    return True


def load_learner_profile_state(
    user_id: str,
    *,
    for_update: bool = False,
) -> UserOnboardingState | None:
    query = UserOnboardingState.query.filter(
        UserOnboardingState.user_bid == str(user_id or "").strip(),
        UserOnboardingState.scene_key == PROFILE_ONBOARDING_SCENE_KEY,
        UserOnboardingState.version == PROFILE_ONBOARDING_VERSION,
    )
    if for_update:
        query = query.populate_existing().with_for_update()
    return query.first()


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

    target_user = (
        UserEntity.query.filter(
            UserEntity.user_bid == normalized_target_id,
            UserEntity.deleted == 0,
        )
        .populate_existing()
        .with_for_update()
        .first()
    )
    if target_user is None:
        return

    if load_learner_profile_state(normalized_target_id, for_update=True) is not None:
        return

    source_user = (
        UserEntity.query.filter(
            UserEntity.user_bid == normalized_source_id,
            UserEntity.deleted == 0,
        )
        .populate_existing()
        .with_for_update()
        .first()
    )
    if source_user is None:
        return

    if source_user.state != USER_STATE_UNREGISTERED:
        return

    source_identify = str(source_user.user_identify or "").strip()
    source_has_account_identifier = bool(
        "@" in source_identify
        or is_valid_sms_mobile(source_identify)
        or AuthCredential.query.filter(
            AuthCredential.user_bid == normalized_source_id,
            AuthCredential.provider_name.in_(["phone", "email"]),
            AuthCredential.state == CREDENTIAL_STATE_VERIFIED,
            AuthCredential.deleted == 0,
        ).first()
    )
    if source_has_account_identifier:
        return

    source_state = load_learner_profile_state(
        normalized_source_id,
        for_update=True,
    )
    source_profile = str(source_user.learner_profile or "").strip()
    source_nickname = str(source_user.nickname or "").strip()
    if source_nickname and _nickname_matches_account_identifier(
        source_user,
        source_nickname,
    ):
        source_nickname = ""
    target_profile = str(target_user.learner_profile or "").strip()
    target_nickname = str(target_user.nickname or "").strip()
    target_nickname_is_fallback = bool(
        target_nickname
        and _nickname_matches_account_identifier(target_user, target_nickname)
    )
    should_copy_nickname = not target_nickname or target_nickname_is_fallback
    if source_profile and not target_profile:
        target_user.learner_profile = source_user.learner_profile
        target_user.learner_profile_updated_at = source_user.learner_profile_updated_at
        if source_nickname and should_copy_nickname:
            target_user.nickname = source_nickname

    if source_state is None:
        return

    if (
        source_nickname
        and not target_profile
        and not source_profile
        and should_copy_nickname
    ):
        target_user.nickname = source_nickname

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


def has_learner_profile_or_state(
    user_id: str,
    *,
    for_update: bool = False,
) -> bool:
    user = load_learner_profile_user(user_id, for_update=for_update)
    has_profile = bool(str(user.learner_profile or "").strip())
    if has_profile and not for_update:
        return True
    state = load_learner_profile_state(user_id, for_update=for_update)
    return has_profile or state is not None


def _apply_completed_state(
    *,
    user_id: str,
    trigger_source: str,
) -> UserOnboardingState:
    state = load_learner_profile_state(user_id, for_update=True)
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


def save_learner_profile(
    app: Flask,
    *,
    user_id: str,
    learner_profile: str,
    trigger_source: str,
    nickname: str | None = None,
) -> dict[str, Any]:
    normalized_trigger_source = str(trigger_source or "").strip()
    if normalized_trigger_source not in LEARNER_PROFILE_TRIGGER_SOURCES:
        raise_param_error("trigger_source")
    normalized = normalize_learner_profile(learner_profile)
    normalized_nickname = (
        normalize_learner_profile_nickname(nickname) if nickname is not None else None
    )
    moderation_passed: set[str] = set()

    def operation() -> tuple[UserEntity, UserOnboardingState]:
        user = load_learner_profile_user(user_id, for_update=True)
        moderation_inputs = tuple(
            dict.fromkeys(
                value
                for value in (normalized, normalized_nickname)
                if value and value not in moderation_passed
            )
        )
        for moderation_input in moderation_inputs:
            if not check_text_content(app, user_id, moderation_input):
                raise_error("server.check.checkRiskControlReject")
            moderation_passed.add(moderation_input)
        apply_learner_profile(user, normalized)
        if normalized_nickname is not None:
            user.nickname = normalized_nickname
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
    nickname: str | None = None,
) -> dict[str, Any]:
    return save_learner_profile(
        app,
        user_id=user_id,
        learner_profile=learner_profile,
        trigger_source="settings",
        nickname=nickname,
    )


def clear_learner_profile(*, user_id: str) -> dict[str, Any]:
    def operation() -> tuple[UserEntity, UserOnboardingState]:
        user = load_learner_profile_user(user_id, for_update=True)
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
