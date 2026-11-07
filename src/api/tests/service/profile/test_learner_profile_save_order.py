"""Keep explicit profile saves independent of questionnaire creation order."""

import pytest
from flask import Flask
from flaskr.dao.uow import unit_of_work
from flaskr.service.profile.learner_profile import (
    PROFILE_ONBOARDING_SCENE_KEY,
    PROFILE_ONBOARDING_STATE_VERSION,
    get_learner_profile,
)
from flaskr.service.profile.onboarding import complete_profile_onboarding
from flaskr.service.user.models import UserOnboardingState
from flaskr.service.user.repository import create_user_entity


@pytest.mark.parametrize("save_order", [("older", "newer"), ("newer", "older")])
def test_last_explicit_save_replaces_an_already_completed_profile(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    save_order: tuple[str, str],
) -> None:
    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args: True,
    )
    user_bid = f"profile-independent-saves-{save_order[0]}"
    # Both browsers have reviewed their own draft before either saves it.
    reviewed_drafts = {
        "older": "Prefers practical exercises with detailed explanations.",
        "newer": "Prefers diagrams with concise explanations.",
    }
    with app.app_context(), unit_of_work():
        create_user_entity(user_bid=user_bid, identify=user_bid, nickname="Learner")

    with app.app_context():
        first = complete_profile_onboarding(
            app,
            user_id=user_bid,
            learner_profile=reviewed_drafts[save_order[0]],
            trigger_source="guided",
        )
    with app.app_context():
        saved = get_learner_profile(user_id=user_bid)
        assert saved["learner_profile"] == reviewed_drafts[save_order[0]]
        second = complete_profile_onboarding(
            app,
            user_id=user_bid,
            learner_profile=reviewed_drafts[save_order[1]],
            trigger_source="guided",
        )

    with app.app_context():
        loaded = get_learner_profile(user_id=user_bid)
        state = UserOnboardingState.query.filter_by(
            user_bid=user_bid,
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
            version=PROFILE_ONBOARDING_STATE_VERSION,
        ).one()
        assert loaded["learner_profile"] == reviewed_drafts[save_order[1]]
        assert state.status == "completed"

    assert first["completed"] is True
    assert second["completed"] is True
    assert second["learner_profile"] == reviewed_drafts[save_order[1]]
    assert second["completed_at"] == first["completed_at"]
