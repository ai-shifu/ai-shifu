from __future__ import annotations

from typing import Any, Callable, TypeVar

from flask import Flask

from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import raise_param_error
from flaskr.service.common.profile_onboarding import (
    PROFILE_ONBOARDING_SCENE_KEY,
    PROFILE_ONBOARDING_STATE_KEY,
    PROFILE_ONBOARDING_VERSION,
)
from flaskr.service.profile.learner_profile import (
    LEARNER_PROFILE_MAX_LENGTH,
    apply_learner_profile,
    load_learner_profile_user,
    serialize_learner_profile,
    validate_learner_profile_content,
)
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.models import UserOnboardingState
from flaskr.util.datetime import now_utc, to_utc_iso
from sqlalchemy.exc import IntegrityError

STATUS_COMPLETED = "completed"
STATUS_SKIPPED = "skipped"

PRESENTATION_HIDDEN = "hidden"
PRESENTATION_BLOCKING = "blocking"
PRESENTATION_NON_BLOCKING = "non_blocking"

COMPLETE_TRIGGER_SOURCES = {
    "guided",
    "pasted",
    "settings",
}
SKIP_TRIGGER_SOURCE = "skipped"

_T = TypeVar("_T")


def _serialize_datetime(value) -> str | None:
    return to_utc_iso(value)


def _load_v2_state(user_id: str) -> UserOnboardingState | None:
    return UserOnboardingState.query.filter(
        UserOnboardingState.user_bid == str(user_id or "").strip(),
        UserOnboardingState.scene_key == PROFILE_ONBOARDING_SCENE_KEY,
        UserOnboardingState.version == PROFILE_ONBOARDING_VERSION,
    ).first()


def _has_legacy_state(user_id: str) -> bool:
    return (
        VariableValue.query.filter(
            VariableValue.user_bid == str(user_id or "").strip(),
            VariableValue.shifu_bid == "",
            VariableValue.key == PROFILE_ONBOARDING_STATE_KEY,
            VariableValue.deleted == 0,
        ).first()
        is not None
    )


def _apply_v2_state(
    *,
    user_id: str,
    status: str,
    trigger_source: str,
) -> UserOnboardingState:
    state = _load_v2_state(user_id)
    now = now_utc()
    if state is None:
        state = UserOnboardingState(
            user_bid=user_id,
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
            version=PROFILE_ONBOARDING_VERSION,
            status=status,
            trigger_source=trigger_source,
            completed_at=now,
        )
        db.session.add(state)
        return state

    # Completion is monotonic. A delayed duplicate skip request must not
    # downgrade a successfully saved profile to a skipped state.
    if state.status == STATUS_COMPLETED and status == STATUS_SKIPPED:
        return state

    if state.status != status:
        state.status = status
    if state.trigger_source != trigger_source:
        state.trigger_source = trigger_source
    if state.completed_at is None:
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
            # Surface the fixed-state unique-key race inside this boundary so
            # unit_of_work rolls back the complete profile/state mutation.
            db.session.flush()
        return result

    try:
        return run_once()
    except IntegrityError:
        # The only expected integrity race is the fixed state row's unique
        # key. If no winner is visible, preserve the original failure.
        with unit_of_work():
            winner = _load_v2_state(user_id)
        if winner is None:
            raise
        return run_once()


def _serialize_state(state: UserOnboardingState) -> dict[str, Any]:
    return {
        "handled": True,
        "completed": state.status == STATUS_COMPLETED,
        "skipped": state.status == STATUS_SKIPPED,
        "status": state.status,
        "trigger_source": state.trigger_source,
        "completed_at": _serialize_datetime(state.completed_at),
        "version": state.version,
    }


def get_profile_onboarding_state(*, user_id: str) -> dict[str, Any]:
    user = load_learner_profile_user(user_id)
    state = _load_v2_state(user_id)
    legacy_handled = _has_legacy_state(user_id)

    if state is not None:
        presentation = PRESENTATION_HIDDEN
    elif legacy_handled:
        presentation = PRESENTATION_NON_BLOCKING
    else:
        presentation = PRESENTATION_BLOCKING

    learner_profile = serialize_learner_profile(user)
    return {
        "handled": state is not None,
        "completed": state is not None and state.status == STATUS_COMPLETED,
        "skipped": state is not None and state.status == STATUS_SKIPPED,
        "status": state.status if state is not None else None,
        "trigger_source": state.trigger_source if state is not None else None,
        "completed_at": _serialize_datetime(state.completed_at) if state else None,
        "version": PROFILE_ONBOARDING_VERSION,
        "should_show": state is None,
        "presentation": presentation,
        "legacy_handled": legacy_handled,
        "has_learner_profile": learner_profile["has_learner_profile"],
        "learner_profile_updated_at": learner_profile["learner_profile_updated_at"],
        "max_length": LEARNER_PROFILE_MAX_LENGTH,
    }


def get_profile_onboarding_status(
    _app: Flask | None = None,
    *,
    user_id: str,
) -> dict[str, Any]:
    """Compatibility name for callers while the learner route is upgraded."""

    return get_profile_onboarding_state(user_id=user_id)


def complete_profile_onboarding(
    app: Flask,
    *,
    user_id: str,
    learner_profile: str,
    trigger_source: str,
) -> dict[str, Any]:
    normalized_trigger_source = str(trigger_source or "").strip()
    if normalized_trigger_source not in COMPLETE_TRIGGER_SOURCES:
        raise_param_error("trigger_source")

    normalized_profile = validate_learner_profile_content(
        app,
        user_id=user_id,
        learner_profile=learner_profile,
    )

    def operation() -> tuple[Any, UserOnboardingState]:
        user = load_learner_profile_user(user_id)
        apply_learner_profile(user, normalized_profile)
        state = _apply_v2_state(
            user_id=user_id,
            status=STATUS_COMPLETED,
            trigger_source=normalized_trigger_source,
        )
        return user, state

    user, state = _commit_with_state_race_retry(operation, user_id=user_id)
    return {
        **_serialize_state(state),
        **serialize_learner_profile(user),
    }


def clear_profile_onboarding(*, user_id: str) -> dict[str, Any]:
    """Clear the canonical profile without making onboarding eligible again."""

    # Load first so an invalid/deleted user cannot create a detached state row.
    load_learner_profile_user(user_id)

    def operation() -> tuple[Any, UserOnboardingState]:
        user = load_learner_profile_user(user_id)
        user.learner_profile = ""
        user.learner_profile_updated_at = None
        state = _apply_v2_state(
            user_id=user_id,
            status=STATUS_COMPLETED,
            trigger_source="settings",
        )
        return user, state

    user, state = _commit_with_state_race_retry(operation, user_id=user_id)
    return {
        **_serialize_state(state),
        **serialize_learner_profile(user),
    }


def skip_profile_onboarding(
    *,
    user_id: str,
    trigger_source: str = SKIP_TRIGGER_SOURCE,
) -> dict[str, Any]:
    normalized_trigger_source = str(trigger_source or "").strip()
    if normalized_trigger_source != SKIP_TRIGGER_SOURCE:
        raise_param_error("trigger_source")

    # Load first so an invalid/deleted user cannot create a detached state row.
    load_learner_profile_user(user_id)

    def operation() -> UserOnboardingState:
        return _apply_v2_state(
            user_id=user_id,
            status=STATUS_SKIPPED,
            trigger_source=normalized_trigger_source,
        )

    state = _commit_with_state_race_retry(operation, user_id=user_id)
    return _serialize_state(state)
