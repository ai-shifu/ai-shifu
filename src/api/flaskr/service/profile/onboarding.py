"""Handle onboarding for learner profiles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import raise_param_error
from flaskr.service.common.profile_onboarding import (
    load_profile_onboarding_config_payload,
    validate_profile_onboarding_markdownflow,
)
from flaskr.service.profile.learner_profile import (
    LEARNER_PROFILE_MAX_LENGTH,
    LEARNER_PROFILE_TRIGGER_SOURCES,
    PROFILE_ONBOARDING_SCENE_KEY,
    PROFILE_ONBOARDING_VERSION,
    get_learner_profile,
    load_learner_profile_state,
    load_learner_profile_user,
    save_learner_profile,
)
from flaskr.service.user.models import UserOnboardingState
from flaskr.util.datetime import now_utc, to_utc_iso
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask

__all__ = [
    "complete_profile_onboarding",
    "get_profile_onboarding_status",
    "skip_profile_onboarding",
]

_T = TypeVar("_T")


def get_profile_onboarding_status(app: Flask, *, user_id: str) -> dict[str, Any]:
    """Return the canonical profile-v2 onboarding status."""
    try:
        config_payload = load_profile_onboarding_config_payload()
    except Exception:
        app.logger.warning("profile onboarding config unavailable", exc_info=True)
        config_payload = {}

    configured_enabled = bool(config_payload.get("enabled"))
    markdownflow = str(config_payload.get("markdownflow") or "").strip()
    guided_available = configured_enabled and bool(markdownflow)
    if guided_available:
        try:
            validate_profile_onboarding_markdownflow(markdownflow)
        except Exception:
            app.logger.warning("profile onboarding config is invalid", exc_info=True)
            guided_available = False

    v2_state = load_learner_profile_state(user_id)
    learner_profile = get_learner_profile(user_id=user_id)
    has_learner_profile = bool(learner_profile["has_learner_profile"])
    canonical_handled = v2_state is not None or has_learner_profile
    presentation = "hidden" if not guided_available or canonical_handled else "blocking"

    canonical_completed = bool(
        has_learner_profile or (v2_state and v2_state.status == "completed")
    )
    effective_status = (
        "completed" if has_learner_profile else v2_state.status if v2_state else None
    )
    return {
        "contract_version": PROFILE_ONBOARDING_VERSION,
        "enabled": configured_enabled,
        "guided_available": guided_available,
        "should_show": guided_available and not canonical_handled,
        "presentation": presentation,
        "handled": canonical_handled,
        "completed": canonical_completed,
        "skipped": effective_status == "skipped",
        "status": effective_status,
        "trigger_source": (
            v2_state.trigger_source
            if v2_state and v2_state.status == effective_status
            else None
        ),
        "completed_at": to_utc_iso(v2_state.completed_at) if v2_state else None,
        "max_length": LEARNER_PROFILE_MAX_LENGTH,
        "config_revision": int(config_payload.get("revision") or 0),
        **learner_profile,
    }


def complete_profile_onboarding(
    app: Flask,
    *,
    user_id: str,
    learner_profile: str,
    trigger_source: str,
    nickname: str | None = None,
) -> dict[str, Any]:
    """Persist the canonical v2 profile, optional nickname, and state."""
    if (
        not isinstance(trigger_source, str)
        or trigger_source not in LEARNER_PROFILE_TRIGGER_SOURCES
    ):
        raise_param_error("trigger_source")

    return save_learner_profile(
        app,
        user_id=user_id,
        learner_profile=learner_profile,
        trigger_source=trigger_source,
        nickname=nickname,
    )


def _commit_v2_state_with_race_retry(
    operation: Callable[[], _T], *, user_id: str
) -> _T:
    def run_once() -> _T:
        with unit_of_work():
            result = operation()
            db.session.flush()
        return result

    try:
        return run_once()
    except IntegrityError:
        # A concurrent request may have created the fixed scene row. Retry
        # only when the expected winner exists; otherwise preserve the DB error.
        with unit_of_work():
            winner = load_learner_profile_state(user_id)
        if winner is None:
            raise
        return run_once()


def skip_profile_onboarding(*, user_id: str) -> dict[str, Any]:
    """Durably defer canonical onboarding without downgrading completion."""

    def operation() -> UserOnboardingState:
        # Match canonical completion's user -> state lock order. Besides
        # serializing skip against a concurrent completion, populate_existing
        # prevents an identity-map snapshot from downgrading durable state.
        user = load_learner_profile_user(user_id, for_update=True)
        state = load_learner_profile_state(user_id, for_update=True)
        if state is None:
            has_learner_profile = bool(str(user.learner_profile or "").strip())
            state = UserOnboardingState(
                user_bid=user_id,
                scene_key=PROFILE_ONBOARDING_SCENE_KEY,
                version=PROFILE_ONBOARDING_VERSION,
                status="completed" if has_learner_profile else "skipped",
                trigger_source="settings" if has_learner_profile else "skipped",
                completed_at=now_utc(),
            )
            db.session.add(state)
        elif state.status != "completed":
            state.status = "skipped"
            state.trigger_source = "skipped"
            if state.completed_at is None:
                state.completed_at = now_utc()
        return state

    state = _commit_v2_state_with_race_retry(operation, user_id=user_id)
    return {
        "handled": True,
        "completed": state.status == "completed",
        "skipped": state.status == "skipped",
        "status": state.status,
        "trigger_source": state.trigger_source,
        "completed_at": to_utc_iso(state.completed_at),
        "version": PROFILE_ONBOARDING_VERSION,
    }
