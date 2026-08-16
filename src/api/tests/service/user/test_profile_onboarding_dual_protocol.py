from __future__ import annotations

import json
from types import SimpleNamespace

from flaskr.dao import db
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.models import UserInfo, UserOnboardingState
from flaskr.service.user.repository import create_user_entity

VALID_GUIDED_FLOW = (
    "?[%{{learning_goal}}...What would you most like to learn right now?]"
)
LEGACY_NONASSIGNMENT_FLOW = "Welcome.\n\n---\n\n?[Continue]"
LEGACY_PROJECTED_FLOW = (
    "Welcome.\n\n---\n\n?[%{{__profile_onboarding_legacy_answer_0}}Continue]"
)


def _create_user(user_bid: str, *, learner_profile: str = "") -> None:
    create_user_entity(
        user_bid=user_bid,
        identify=user_bid,
        nickname="Test learner",
        language="en-US",
        learner_profile=learner_profile,
    )
    db.session.commit()


def _set_config(monkeypatch, payload: dict) -> None:
    from flaskr.service.common import profile_onboarding as config_module

    monkeypatch.setattr(
        config_module,
        "get_config",
        lambda *_args, **_kwargs: payload,
    )


def test_legacy_projection_assigns_mixed_nonassignment_blocks_without_collisions():
    from flaskr.service.profile.onboarding import (
        _project_legacy_profile_onboarding_markdownflow,
    )
    from flaskr.service.profile_research.api import (
        validate_profile_research_document,
    )

    document = (
        "Welcome.\n\n---\n\n"
        "?[%{{__profile_onboarding_legacy_answer_0}}...Assigned question]\n\n---\n\n"
        "?[Continue]\n\n---\n\n"
        "?[Yes | No]"
    )

    projected = _project_legacy_profile_onboarding_markdownflow(document)

    assert projected == (
        "Welcome.\n\n---\n\n"
        "?[%{{__profile_onboarding_legacy_answer_0}}...Assigned question]\n\n---\n\n"
        "?[%{{__profile_onboarding_legacy_answer_0_1}}Continue]\n\n---\n\n"
        "?[%{{__profile_onboarding_legacy_answer_1}}Yes | No]"
    )
    assert validate_profile_research_document(projected)["variables"] == [
        "__profile_onboarding_legacy_answer_0",
        "__profile_onboarding_legacy_answer_0_1",
        "__profile_onboarding_legacy_answer_1",
    ]


def test_legacy_projection_failure_keeps_status_fail_open(app, monkeypatch):
    from flaskr.service.profile import onboarding as onboarding_service

    def raise_projection_error(_document: str) -> str:
        raise RuntimeError("projection failed")

    _set_config(
        monkeypatch,
        {
            "enabled": True,
            "markdownflow": LEGACY_NONASSIGNMENT_FLOW,
            "revision": 9,
        },
    )
    monkeypatch.setattr(
        onboarding_service,
        "_project_legacy_profile_onboarding_markdownflow",
        raise_projection_error,
    )

    with app.app_context():
        _create_user("legacy-projection-failure")
        status = onboarding_service.get_profile_onboarding_status(
            app,
            user_id="legacy-projection-failure",
        )

    assert status["enabled"] is False
    assert status["should_show"] is False
    assert status["profile_v2"]["guided_available"] is False
    assert status["profile_v2"]["should_show"] is False
    assert status["profile_v2"]["presentation"] == "hidden"


def test_dual_get_contract_covers_fresh_legacy_canonical_v2_and_fail_open(
    app, monkeypatch
):
    from flaskr.service.common.profile_onboarding import (
        PROFILE_ONBOARDING_SCENE_KEY,
        PROFILE_ONBOARDING_STATE_KEY,
        PROFILE_ONBOARDING_VERSION,
    )
    from flaskr.service.profile.onboarding import (
        complete_profile_onboarding,
        get_profile_onboarding_status,
    )

    enabled_config = {
        "enabled": True,
        "markdownflow": VALID_GUIDED_FLOW,
        "document_prompt": "Keep the result concise.",
        "revision": 9,
    }
    _set_config(monkeypatch, enabled_config)

    with app.app_context():
        _create_user("dual-fresh")
        _create_user("dual-legacy")
        _create_user("dual-canonical", learner_profile="Prefers concise diagrams.")
        _create_user("dual-v2")
        _create_user("dual-disabled")
        _create_user("dual-broken")

        complete_profile_onboarding(
            app,
            user_id="dual-legacy",
            skipped=True,
            variables={},
        )
        db.session.add(
            UserOnboardingState(
                user_bid="dual-v2",
                scene_key=PROFILE_ONBOARDING_SCENE_KEY,
                version=PROFILE_ONBOARDING_VERSION,
                status="skipped",
                trigger_source="skipped",
            )
        )
        db.session.commit()

        fresh = get_profile_onboarding_status(app, user_id="dual-fresh")
        legacy = get_profile_onboarding_status(app, user_id="dual-legacy")
        canonical = get_profile_onboarding_status(app, user_id="dual-canonical")
        v2 = get_profile_onboarding_status(app, user_id="dual-v2")

        enabled_config.update(enabled=False)
        disabled = get_profile_onboarding_status(app, user_id="dual-disabled")
        enabled_config.update(enabled=True, markdownflow="Plain Markdown only")
        broken = get_profile_onboarding_status(app, user_id="dual-broken")

        legacy_state = VariableValue.query.filter_by(
            user_bid="dual-legacy",
            key=PROFILE_ONBOARDING_STATE_KEY,
            deleted=0,
        ).one()

    assert fresh["enabled"] is True
    assert fresh["should_show"] is True
    assert fresh["contract_version"] == PROFILE_ONBOARDING_VERSION
    assert fresh["profile_v2"]["presentation"] == "blocking"
    assert fresh["profile_v2"]["should_show"] is True
    assert fresh["profile_v2"]["config_revision"] == 9

    assert legacy["should_show"] is False
    assert legacy["profile_v2"]["presentation"] == "non_blocking"
    assert legacy["profile_v2"]["should_show"] is True
    assert legacy["profile_v2"]["legacy_handled"] is True
    assert json.loads(legacy_state.value)["version"] == 9

    for handled in (canonical, v2):
        assert handled["should_show"] is False
        assert handled["profile_v2"]["handled"] is True
        assert handled["profile_v2"]["should_show"] is False
        assert handled["profile_v2"]["presentation"] == "hidden"

    for unavailable in (disabled, broken):
        assert unavailable["enabled"] is False
        assert unavailable["should_show"] is False
        assert unavailable["profile_v2"]["guided_available"] is False
        assert unavailable["profile_v2"]["should_show"] is False
        assert unavailable["profile_v2"]["presentation"] == "hidden"


def test_legacy_projection_completion_writes_only_the_legacy_sentinel(
    app, monkeypatch, test_client
):
    from flaskr.service.common.profile_onboarding import (
        PROFILE_ONBOARDING_STATE_KEY,
    )
    from flaskr.service.profile.onboarding import get_profile_onboarding_status

    _set_config(
        monkeypatch,
        {
            "enabled": True,
            "markdownflow": LEGACY_NONASSIGNMENT_FLOW,
            "revision": 10,
        },
    )
    moderated_values = []
    monkeypatch.setattr(
        "flaskr.service.profile.onboarding.check_text_content",
        lambda _app, _user_id, value: moderated_values.append(value) or True,
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: SimpleNamespace(
            user_id="protocol-arbitrary-only",
            language="en-US",
            is_operator=False,
        ),
    )

    with app.app_context():
        _create_user("protocol-arbitrary-only")
        fresh = get_profile_onboarding_status(
            app,
            user_id="protocol-arbitrary-only",
        )

    response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "skipped": False,
            "variables": {
                "__profile_onboarding_legacy_answer_0": "Continue",
            },
        },
    )

    with app.app_context():
        user = UserInfo.query.filter_by(user_bid="protocol-arbitrary-only").one()
        values = {
            row.key: row.value
            for row in VariableValue.query.filter_by(
                user_bid="protocol-arbitrary-only",
                deleted=0,
            ).all()
        }
        v2_state = UserOnboardingState.query.filter_by(
            user_bid="protocol-arbitrary-only"
        ).first()
        handled = get_profile_onboarding_status(
            app,
            user_id="protocol-arbitrary-only",
        )

    body = response.get_json(force=True)
    assert body["code"] == 0
    assert body["data"]["variables"] == {}
    assert moderated_values == []
    assert user.learner_profile == ""
    assert set(values) == {PROFILE_ONBOARDING_STATE_KEY}
    assert json.loads(values[PROFILE_ONBOARDING_STATE_KEY])["version"] == 10
    assert v2_state is None

    assert fresh["should_show"] is True
    assert fresh["markdownflow"] == LEGACY_PROJECTED_FLOW
    assert fresh["contract_version"] == "profile-v2"
    assert fresh["profile_v2"]["guided_available"] is True
    assert fresh["profile_v2"]["should_show"] is True
    assert fresh["profile_v2"]["presentation"] == "blocking"
    assert handled["should_show"] is False
    assert handled["profile_v2"]["should_show"] is True
    assert handled["profile_v2"]["legacy_handled"] is True
    assert handled["profile_v2"]["presentation"] == "non_blocking"


def test_legacy_complete_filters_unknown_variables_before_moderation_and_storage(
    app, monkeypatch, test_client
):
    from flaskr.service.common.profile_onboarding import (
        PROFILE_ONBOARDING_STATE_KEY,
    )

    _set_config(
        monkeypatch,
        {
            "enabled": True,
            "markdownflow": VALID_GUIDED_FLOW,
            "revision": 11,
        },
    )
    moderated_values = []
    monkeypatch.setattr(
        "flaskr.service.profile.onboarding.check_text_content",
        lambda _app, _user_id, value: moderated_values.append(value) or True,
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: SimpleNamespace(
            user_id="protocol-arbitrary-and-system",
            language="en-US",
            is_operator=False,
        ),
    )

    with app.app_context():
        _create_user("protocol-arbitrary-and-system")

    response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "skipped": False,
            "variables": {
                "learning_goal": "This must be discarded.",
                "sys_user_nickname": "Legacy learner",
            },
        },
    )

    with app.app_context():
        user = UserInfo.query.filter_by(user_bid="protocol-arbitrary-and-system").one()
        values = {
            row.key: row.value
            for row in VariableValue.query.filter_by(
                user_bid="protocol-arbitrary-and-system",
                deleted=0,
            ).all()
        }
        v2_state = UserOnboardingState.query.filter_by(
            user_bid="protocol-arbitrary-and-system"
        ).first()

    body = response.get_json(force=True)
    assert body["code"] == 0
    assert body["data"]["variables"] == {"sys_user_nickname": "Legacy learner"}
    assert moderated_values == ["Legacy learner"]
    assert set(values) == {"sys_user_nickname", PROFILE_ONBOARDING_STATE_KEY}
    assert values["sys_user_nickname"] == "Legacy learner"
    assert json.loads(values[PROFILE_ONBOARDING_STATE_KEY])["version"] == 11
    assert "learning_goal" not in values
    assert user.learner_profile == ""
    assert v2_state is None


def test_complete_routes_keep_legacy_and_v2_persistence_strictly_isolated(
    app, monkeypatch, test_client
):
    from flaskr.service.common.profile_onboarding import (
        PROFILE_ONBOARDING_SCENE_KEY,
        PROFILE_ONBOARDING_STATE_KEY,
        PROFILE_ONBOARDING_VERSION,
    )

    _set_config(
        monkeypatch,
        {
            "enabled": True,
            "markdownflow": VALID_GUIDED_FLOW,
            "revision": 4,
        },
    )
    monkeypatch.setattr(
        "flaskr.service.profile.onboarding.check_text_content",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    active_user = {"user_id": "protocol-legacy"}
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: SimpleNamespace(
            user_id=active_user["user_id"],
            language="en-US",
            is_operator=False,
        ),
    )

    with app.app_context():
        _create_user("protocol-legacy")
        _create_user("protocol-v2")
        _create_user("protocol-mixed")

    legacy_response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "skipped": False,
            "variables": {
                "sys_user_nickname": "Legacy learner",
                "sys_user_background": "Legacy background",
            },
        },
    )
    active_user["user_id"] = "protocol-v2"
    v2_response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "learner_profile": "Prefers short examples and practical exercises.",
            "trigger_source": "guided",
        },
    )
    active_user["user_id"] = "protocol-mixed"
    mixed_response = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={
            "skipped": False,
            "learner_profile": "This payload must never be written.",
            "trigger_source": "guided",
        },
    )

    assert legacy_response.get_json(force=True)["code"] == 0
    assert v2_response.get_json(force=True)["code"] == 0
    assert mixed_response.get_json(force=True)["code"] != 0

    with app.app_context():
        legacy_user = UserInfo.query.filter_by(user_bid="protocol-legacy").one()
        legacy_values = {
            row.key: row.value
            for row in VariableValue.query.filter_by(
                user_bid="protocol-legacy",
                deleted=0,
            ).all()
        }
        legacy_v2_state = UserOnboardingState.query.filter_by(
            user_bid="protocol-legacy",
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
            version=PROFILE_ONBOARDING_VERSION,
        ).first()

        v2_user = UserInfo.query.filter_by(user_bid="protocol-v2").one()
        v2_values = VariableValue.query.filter_by(
            user_bid="protocol-v2",
            deleted=0,
        ).all()
        v2_state = UserOnboardingState.query.filter_by(
            user_bid="protocol-v2",
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
            version=PROFILE_ONBOARDING_VERSION,
        ).one()

        mixed_user = UserInfo.query.filter_by(user_bid="protocol-mixed").one()
        mixed_values = VariableValue.query.filter_by(
            user_bid="protocol-mixed",
            deleted=0,
        ).all()
        mixed_state = UserOnboardingState.query.filter_by(
            user_bid="protocol-mixed"
        ).first()

    assert legacy_user.learner_profile == ""
    assert legacy_v2_state is None
    assert legacy_values["sys_user_nickname"] == "Legacy learner"
    assert legacy_values["sys_user_background"] == "Legacy background"
    assert PROFILE_ONBOARDING_STATE_KEY in legacy_values

    assert v2_user.learner_profile == (
        "Prefers short examples and practical exercises."
    )
    assert v2_state.status == "completed"
    assert v2_state.trigger_source == "guided"
    assert v2_values == []

    assert mixed_user.learner_profile == ""
    assert mixed_values == []
    assert mixed_state is None


def test_status_fails_open_when_profile_config_cannot_be_loaded(app, monkeypatch):
    from flaskr.service.profile import onboarding as onboarding_module

    def raise_unavailable_config():
        raise RuntimeError("config unavailable")

    monkeypatch.setattr(
        onboarding_module,
        "load_profile_onboarding_config_payload",
        raise_unavailable_config,
    )

    with app.app_context():
        _create_user("protocol-config-unavailable")
        status = onboarding_module.get_profile_onboarding_status(
            app,
            user_id="protocol-config-unavailable",
        )

    assert status["enabled"] is False
    assert status["should_show"] is False
    assert status["profile_v2"]["guided_available"] is False
    assert status["profile_v2"]["should_show"] is False
    assert status["profile_v2"]["presentation"] == "hidden"


def test_late_v2_skip_never_downgrades_a_completed_profile(app, monkeypatch):
    from flaskr.service.profile.onboarding import (
        complete_profile_onboarding_v2,
        skip_profile_onboarding_v2,
    )

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    with app.app_context():
        _create_user("protocol-late-skip")
        completed = complete_profile_onboarding_v2(
            app,
            user_id="protocol-late-skip",
            learner_profile="Keep the completed profile.",
            trigger_source="guided",
        )
        skipped = skip_profile_onboarding_v2(user_id="protocol-late-skip")
        state = UserOnboardingState.query.filter_by(user_bid="protocol-late-skip").one()

    assert completed["status"] == "completed"
    assert skipped["status"] == "completed"
    assert skipped["skipped"] is False
    assert state.status == "completed"
    assert state.trigger_source == "guided"


def test_v2_complete_accepts_dormant_canonical_pasted_trigger(app, monkeypatch):
    from flaskr.service.profile.onboarding import complete_profile_onboarding_v2

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    with app.app_context():
        _create_user("protocol-dormant-pasted")
        completed = complete_profile_onboarding_v2(
            app,
            user_id="protocol-dormant-pasted",
            learner_profile="Imported canonical profile.",
            trigger_source="pasted",
        )
        state = UserOnboardingState.query.filter_by(
            user_bid="protocol-dormant-pasted"
        ).one()

    assert completed["status"] == "completed"
    assert completed["trigger_source"] == "pasted"
    assert state.status == "completed"
    assert state.trigger_source == "pasted"


def test_late_v2_skip_reconstructs_completed_state_before_session_cleanup(
    app, monkeypatch, test_client
):
    user_id = "protocol-profile-without-state"
    session_id = "0123456789abcdef0123456789abcdef"

    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: SimpleNamespace(
            user_id=user_id,
            language="en-US",
            is_operator=False,
        ),
    )

    with app.app_context():
        _create_user(user_id, learner_profile="Keep this canonical profile.")
        assert UserOnboardingState.query.filter_by(user_bid=user_id).first() is None

    cleanup_observations: list[tuple[str, str, str]] = []

    def observe_cleanup(_app, *, user_bid: str, session_id: str | None) -> None:
        # Force a fresh ORM session so cleanup can only observe committed state.
        db.session.remove()
        state = UserOnboardingState.query.filter_by(user_bid=user_bid).one()
        cleanup_observations.append((user_bid, session_id or "", state.status))

    monkeypatch.setattr(
        "flaskr.route.user._delete_profile_onboarding_session",
        observe_cleanup,
    )

    response = test_client.post(
        "/api/user/profile-onboarding/skip",
        headers={"Token": "token"},
        json={"session_id": session_id},
    )

    data = response.get_json(force=True)
    assert data["code"] == 0
    assert data["data"]["status"] == "completed"
    assert data["data"]["completed"] is True
    assert data["data"]["skipped"] is False
    assert data["data"]["trigger_source"] == "settings"
    assert cleanup_observations == [(user_id, session_id, "completed")]

    with app.app_context():
        state = UserOnboardingState.query.filter_by(user_bid=user_id).one()
        assert state.status == "completed"
        assert state.trigger_source == "settings"
