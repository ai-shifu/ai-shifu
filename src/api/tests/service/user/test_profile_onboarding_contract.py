"""Verify the canonical profile-v2 onboarding contract."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Never

import pytest
from flaskr.dao import db
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.models import UserInfo, UserOnboardingState
from flaskr.service.user.repository import create_user_entity


def _create_user(user_bid: str, *, learner_profile: str = "") -> None:
    create_user_entity(
        user_bid=user_bid,
        identify=user_bid,
        nickname="Test learner",
        language="en-US",
        learner_profile=learner_profile,
    )
    db.session.commit()


def test_status_fails_open_when_profile_config_cannot_be_loaded(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile import onboarding as onboarding_module

    def raise_unavailable_config() -> Never:
        msg = "config unavailable"
        raise RuntimeError(msg)

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

    assert status["contract_version"] == "profile-v2"
    assert status["enabled"] is False
    assert status["guided_available"] is False
    assert status["should_show"] is False
    assert status["presentation"] == "hidden"


def test_old_sentinel_is_ignored_and_fresh_user_remains_blocking(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile import onboarding as onboarding_module

    monkeypatch.setattr(
        onboarding_module,
        "load_profile_onboarding_config_payload",
        lambda: {
            "enabled": True,
            "markdownflow": "?[%{{learning_goal}}...What do you want to learn?]",
            "revision": 8,
        },
    )
    monkeypatch.setattr(
        onboarding_module,
        "validate_profile_onboarding_markdownflow",
        lambda _document: {"block_count": 1},
    )

    with app.app_context():
        user_id = "protocol-sentinel-only"
        _create_user(user_id)
        db.session.add(
            VariableValue(
                variable_value_bid="retired-sentinel-value",
                user_bid=user_id,
                shifu_bid="",
                variable_bid="",
                key="_sys_profile_onboarding_state",
                value='{"status":"completed","version":8}',
                deleted=0,
            )
        )
        db.session.commit()

        status = onboarding_module.get_profile_onboarding_status(
            app,
            user_id=user_id,
        )

    assert status["contract_version"] == "profile-v2"
    assert status["config_revision"] == 8
    assert status["handled"] is False
    assert status["should_show"] is True
    assert status["presentation"] == "blocking"
    assert "profile_v2" not in status
    assert "legacy_handled" not in status
    assert "markdownflow" not in status


def test_late_skip_never_downgrades_a_completed_profile(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile.onboarding import (
        complete_profile_onboarding,
        skip_profile_onboarding,
    )

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    with app.app_context():
        _create_user("protocol-late-skip")
        completed = complete_profile_onboarding(
            app,
            user_id="protocol-late-skip",
            learner_profile="Keep the completed profile.",
            trigger_source="guided",
        )
        skipped = skip_profile_onboarding(user_id="protocol-late-skip")
        state = UserOnboardingState.query.filter_by(user_bid="protocol-late-skip").one()

    assert completed["status"] == "completed"
    assert skipped["status"] == "completed"
    assert skipped["skipped"] is False
    assert state.status == "completed"
    assert state.trigger_source == "guided"


def test_skip_locks_user_then_state_before_deciding_status(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile import onboarding as onboarding_module

    lock_reads: list[tuple[str, bool]] = []
    original_load_user = onboarding_module.load_learner_profile_user
    original_load_state = onboarding_module.load_learner_profile_state

    def load_user(user_id: str, *, for_update: bool = False) -> object:
        lock_reads.append(("user", for_update))
        return original_load_user(user_id, for_update=for_update)

    def load_state(user_id: str, *, for_update: bool = False) -> object:
        lock_reads.append(("state", for_update))
        return original_load_state(user_id, for_update=for_update)

    with app.app_context():
        user_id = "protocol-skip-lock-order"
        _create_user(user_id, learner_profile="Keep the completed profile.")
        monkeypatch.setattr(onboarding_module, "load_learner_profile_user", load_user)
        monkeypatch.setattr(onboarding_module, "load_learner_profile_state", load_state)

        result = onboarding_module.skip_profile_onboarding(user_id=user_id)

    assert lock_reads[:2] == [("user", True), ("state", True)]
    assert result["status"] == "completed"
    assert result["skipped"] is False


def test_complete_accepts_dormant_canonical_pasted_trigger(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile.onboarding import complete_profile_onboarding

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    with app.app_context():
        _create_user("protocol-dormant-pasted")
        completed = complete_profile_onboarding(
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


def test_complete_atomically_saves_optional_nickname_semantics(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile.onboarding import complete_profile_onboarding

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    with app.app_context():
        _create_user("protocol-nickname-preserve")
        _create_user("protocol-nickname-clear")
        _create_user("protocol-nickname-replace")

        preserved = complete_profile_onboarding(
            app,
            user_id="protocol-nickname-preserve",
            learner_profile="Keep my existing display name.",
            trigger_source="guided",
        )
        cleared = complete_profile_onboarding(
            app,
            user_id="protocol-nickname-clear",
            learner_profile="Do not use a display name.",
            trigger_source="guided",
            nickname="",
        )
        replaced = complete_profile_onboarding(
            app,
            user_id="protocol-nickname-replace",
            learner_profile="Call me River.",
            trigger_source="guided",
            nickname="River",
        )

        users = {
            user.user_bid: user
            for user in UserInfo.query.filter(
                UserInfo.user_bid.in_(
                    {
                        "protocol-nickname-preserve",
                        "protocol-nickname-clear",
                        "protocol-nickname-replace",
                    }
                )
            ).all()
        }
        states = {
            state.user_bid: state
            for state in UserOnboardingState.query.filter(
                UserOnboardingState.user_bid.in_(users)
            ).all()
        }

    assert preserved["nickname"] == "Test learner"
    assert cleared["nickname"] == ""
    assert replaced["nickname"] == "River"
    assert users["protocol-nickname-preserve"].nickname == "Test learner"
    assert users["protocol-nickname-clear"].nickname == ""
    assert users["protocol-nickname-replace"].nickname == "River"
    assert all(state.status == "completed" for state in states.values())
    assert all(state.trigger_source == "guided" for state in states.values())


def test_complete_rolls_back_profile_nickname_and_state_together(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.profile.onboarding import complete_profile_onboarding

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args, **_kwargs: True,
    )

    with app.app_context():
        user_id = "protocol-nickname-atomic-failure"
        _create_user(user_id, learner_profile="Existing profile.")
        original_commit = db.session.commit

        def fail_commit() -> Never:
            msg = "database unavailable"
            raise RuntimeError(msg)

        monkeypatch.setattr(db.session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="database unavailable"):
            complete_profile_onboarding(
                app,
                user_id=user_id,
                learner_profile="Replacement profile.",
                trigger_source="guided",
                nickname="Replacement name",
            )
        monkeypatch.setattr(db.session, "commit", original_commit)

        user = UserInfo.query.filter_by(user_bid=user_id).one()
        state = UserOnboardingState.query.filter_by(user_bid=user_id).first()

    assert user.learner_profile == "Existing profile."
    assert user.nickname == "Test learner"
    assert state is None


def test_late_skip_reconstructs_completed_state_before_session_cleanup(
    app: object, monkeypatch: object, test_client: object
) -> None:
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

    def observe_cleanup(_app: object, *, user_bid: str, session_id: str | None) -> None:
        db.session.remove()
        state = UserOnboardingState.query.filter_by(user_bid=user_bid).one()
        cleanup_observations.append((user_bid, session_id or "", state.status))

    monkeypatch.setattr(
        "flaskr.route.profile._delete_profile_onboarding_session",
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
