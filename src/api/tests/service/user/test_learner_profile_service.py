from __future__ import annotations

import hashlib
import json
from datetime import datetime

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppException
from flaskr.service.common.profile_onboarding import PROFILE_ONBOARDING_STATE_KEY
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.models import UserInfo, UserOnboardingState
from flaskr.service.user.repository import create_user_entity, load_user_aggregate

PROFILE_UPDATED_AT = datetime.fromisoformat("2026-08-01T08:30:00")


def _create_user(user_bid: str, *, learner_profile: str = "") -> UserInfo:
    user = create_user_entity(
        user_bid=user_bid,
        identify=user_bid,
        nickname="Test learner",
        language="zh-CN",
        learner_profile=learner_profile,
        learner_profile_updated_at=PROFILE_UPDATED_AT if learner_profile else None,
    )
    db.session.commit()
    return user


def _allow_profile_safety(monkeypatch) -> list[tuple[str, str]]:
    checked: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda _app, user_id, text: checked.append((user_id, text)) or True,
    )
    return checked


def _add_profile_value(
    *,
    value_bid: str,
    user_bid: str,
    key: str,
    value: str,
    shifu_bid: str = "",
) -> VariableValue:
    row = VariableValue(
        variable_value_bid=value_bid,
        variable_bid="",
        shifu_bid=shifu_bid,
        user_bid=user_bid,
        key=key,
        value=value,
        deleted=0,
    )
    db.session.add(row)
    return row


def test_repository_aggregate_exposes_learner_profile(app):
    with app.app_context():
        _create_user("profile-aggregate", learner_profile="偏好图表和简洁表达")
        aggregate = load_user_aggregate("profile-aggregate")

    assert aggregate is not None
    assert aggregate.learner_profile == "偏好图表和简洁表达"
    assert aggregate.learner_profile_updated_at == PROFILE_UPDATED_AT


def test_replace_and_clear_learner_profile(app, monkeypatch):
    from flaskr.service.profile.learner_profile import (
        clear_learner_profile,
        get_learner_profile,
        replace_learner_profile,
    )

    checked = _allow_profile_safety(monkeypatch)
    with app.app_context():
        _create_user("profile-replace")
        saved = replace_learner_profile(
            app,
            user_id="profile-replace",
            learner_profile="  称呼：小明\n幻灯片风格：留白多  ",
        )
        first_updated_at = saved["learner_profile_updated_at"]
        unchanged = replace_learner_profile(
            app,
            user_id="profile-replace",
            learner_profile="称呼：小明\n幻灯片风格：留白多",
        )
        loaded = get_learner_profile(user_id="profile-replace")
        cleared = clear_learner_profile(user_id="profile-replace")

    assert loaded["learner_profile"] == "称呼：小明\n幻灯片风格：留白多"
    assert loaded["has_learner_profile"] is True
    assert loaded["max_length"] == 1000
    assert first_updated_at is not None and first_updated_at.endswith("Z")
    assert unchanged["learner_profile_updated_at"] == first_updated_at
    assert cleared == {
        "learner_profile": "",
        "learner_profile_updated_at": None,
        "has_learner_profile": False,
        "max_length": 1000,
    }
    assert checked == [
        ("profile-replace", "称呼：小明\n幻灯片风格：留白多"),
        ("profile-replace", "称呼：小明\n幻灯片风格：留白多"),
    ]


@pytest.mark.parametrize(
    "value",
    [None, 1, "", "   ", "🙂" * 1001],
)
def test_replace_rejects_invalid_profile_without_overwriting(app, monkeypatch, value):
    from flaskr.service.profile.learner_profile import (
        get_learner_profile,
        replace_learner_profile,
    )

    _allow_profile_safety(monkeypatch)
    user_bid = f"profile-invalid-{type(value).__name__}-{len(str(value))}"
    with app.app_context():
        _create_user(user_bid, learner_profile="existing profile")
        with pytest.raises(AppException):
            replace_learner_profile(
                app,
                user_id=user_bid,
                learner_profile=value,
            )
        loaded = get_learner_profile(user_id=user_bid)

    assert loaded["learner_profile"] == "existing profile"


def test_replace_accepts_exactly_1000_unicode_code_points(app, monkeypatch):
    from flaskr.service.profile.learner_profile import replace_learner_profile

    _allow_profile_safety(monkeypatch)
    with app.app_context():
        _create_user("profile-unicode-limit")
        result = replace_learner_profile(
            app,
            user_id="profile-unicode-limit",
            learner_profile="🙂" * 1000,
        )

    assert len(result["learner_profile"]) == 1000


def test_safety_rejection_preserves_existing_profile(app, monkeypatch):
    from flaskr.service.profile.learner_profile import (
        get_learner_profile,
        replace_learner_profile,
    )

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda _app, _user_id, _text: False,
    )
    with app.app_context():
        _create_user("profile-safety-reject", learner_profile="existing profile")
        with pytest.raises(AppException):
            replace_learner_profile(
                app,
                user_id="profile-safety-reject",
                learner_profile="rejected profile",
            )
        loaded = get_learner_profile(user_id="profile-safety-reject")

    assert loaded["learner_profile"] == "existing profile"


def test_profile_safety_audit_redacts_local_text_and_provider_response(
    app, monkeypatch
):
    from flaskr.api.check.dto import CHECK_RESULT_PASS, CheckResultDTO
    from flaskr.service.check_risk.models import RiskControlResult
    from flaskr.service.profile.learner_profile import replace_learner_profile

    profile = "称呼：小明\n职业背景：医疗产品经理"
    checked: dict[str, str] = {}

    def fake_check_text(_app, check_id, text, user_id):
        checked.update(check_id=check_id, text=text, user_id=user_id)
        return CheckResultDTO(
            check_result=CHECK_RESULT_PASS,
            risk_labels=["safe-label"],
            risk_label_ids=[100],
            provider="test-provider",
            raw_data={"echo": text, "provider_request_id": "private-provider-id"},
        )

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text", fake_check_text
    )

    with app.app_context():
        _create_user("profile-redacted-audit")
        replace_learner_profile(
            app,
            user_id="profile-redacted-audit",
            learner_profile=profile,
        )
        audit_row = RiskControlResult.query.filter_by(
            user_id="profile-redacted-audit"
        ).one()

    assert checked["text"] == profile
    assert checked["user_id"] == "profile-redacted-audit"
    assert audit_row.chat_id == checked["check_id"]
    assert audit_row.check_vendor == "test-provider"
    assert audit_row.check_result == CHECK_RESULT_PASS
    assert audit_row.check_strategy == "check_learner_profile"
    assert profile not in audit_row.text
    assert profile not in audit_row.check_resp
    assert "private-provider-id" not in audit_row.check_resp
    assert json.loads(audit_row.text) == {
        "content": "[redacted]",
        "sha256": hashlib.sha256(profile.encode("utf-8")).hexdigest(),
        "unicode_code_points": len(profile),
    }
    assert json.loads(audit_row.check_resp) == {
        "risk_label_ids": [100],
        "risk_labels": ["safe-label"],
    }


def test_status_distinguishes_blocking_legacy_and_v2_states(app):
    from flaskr.service.profile.onboarding import (
        PRESENTATION_BLOCKING,
        PRESENTATION_HIDDEN,
        PRESENTATION_NON_BLOCKING,
        PROFILE_ONBOARDING_SCENE_KEY,
        PROFILE_ONBOARDING_VERSION,
        get_profile_onboarding_state,
        skip_profile_onboarding,
    )

    with app.app_context():
        _create_user("profile-status-new")
        new_status = get_profile_onboarding_state(user_id="profile-status-new")

        _create_user("profile-status-legacy")
        db.session.add(
            VariableValue(
                variable_value_bid="legacy-state-bid",
                user_bid="profile-status-legacy",
                shifu_bid="",
                variable_bid="",
                key=PROFILE_ONBOARDING_STATE_KEY,
                value='{"status":"skipped","version":1}',
                deleted=0,
            )
        )
        db.session.commit()
        legacy_status = get_profile_onboarding_state(user_id="profile-status-legacy")

        skipped = skip_profile_onboarding(user_id="profile-status-legacy")
        v2_status = get_profile_onboarding_state(user_id="profile-status-legacy")

        _create_user("profile-status-completed")
        db.session.add(
            UserOnboardingState(
                user_bid="profile-status-completed",
                scene_key=PROFILE_ONBOARDING_SCENE_KEY,
                version=PROFILE_ONBOARDING_VERSION,
                status="completed",
                trigger_source="pasted",
                completed_at=PROFILE_UPDATED_AT,
            )
        )
        db.session.commit()
        completed_status = get_profile_onboarding_state(
            user_id="profile-status-completed"
        )

    assert new_status["should_show"] is True
    assert new_status["presentation"] == PRESENTATION_BLOCKING
    assert new_status["legacy_handled"] is False
    assert legacy_status["should_show"] is True
    assert legacy_status["presentation"] == PRESENTATION_NON_BLOCKING
    assert legacy_status["legacy_handled"] is True
    assert skipped["status"] == "skipped"
    assert v2_status["should_show"] is False
    assert v2_status["presentation"] == PRESENTATION_HIDDEN
    assert completed_status["completed"] is True


def test_complete_atomically_writes_profile_and_fixed_v2_state(app, monkeypatch):
    from flaskr.service.profile.onboarding import (
        PROFILE_ONBOARDING_SCENE_KEY,
        PROFILE_ONBOARDING_VERSION,
        complete_profile_onboarding,
    )

    checked = _allow_profile_safety(monkeypatch)
    with app.app_context():
        _create_user("profile-complete")
        result = complete_profile_onboarding(
            app,
            user_id="profile-complete",
            learner_profile="称呼：小明\n表达风格：简洁",
            trigger_source="guided",
        )
        user = UserInfo.query.filter_by(user_bid="profile-complete").one()
        state = UserOnboardingState.query.filter_by(
            user_bid="profile-complete",
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
            version=PROFILE_ONBOARDING_VERSION,
        ).one()
        variable_values = VariableValue.query.filter_by(
            user_bid="profile-complete",
            deleted=0,
        ).all()

    assert result["completed"] is True
    assert result["skipped"] is False
    assert result["status"] == "completed"
    assert result["trigger_source"] == "guided"
    assert user.learner_profile == "称呼：小明\n表达风格：简洁"
    assert state.status == "completed"
    assert state.completed_at is not None
    assert variable_values == []
    assert checked == [("profile-complete", "称呼：小明\n表达风格：简洁")]


def test_complete_preserves_legacy_variable_values_for_old_courses(app, monkeypatch):
    from flaskr.service.profile.onboarding import complete_profile_onboarding

    _allow_profile_safety(monkeypatch)
    with app.app_context():
        user_bid = "profile-preserve-legacy"
        _create_user(user_bid)
        _add_profile_value(
            value_bid="preserve-global-bg",
            user_bid=user_bid,
            key="sys_user_background",
            value="旧全局背景",
        )
        _add_profile_value(
            value_bid="preserve-global-style",
            user_bid=user_bid,
            key="sys_user_style",
            value="旧全局风格",
        )
        _add_profile_value(
            value_bid="preserve-global-name",
            user_bid=user_bid,
            key="sys_user_nickname",
            value="小明",
        )
        _add_profile_value(
            value_bid="preserve-course-bg",
            user_bid=user_bid,
            shifu_bid="course-1",
            key="sys_user_background",
            value="课程背景",
        )
        _add_profile_value(
            value_bid="preserve-course-style",
            user_bid=user_bid,
            shifu_bid="course-1",
            key="sys_user_style",
            value="课程风格",
        )
        db.session.commit()

        complete_profile_onboarding(
            app,
            user_id=user_bid,
            learner_profile="统一画像",
            trigger_source="settings",
        )
        rows = VariableValue.query.filter_by(user_bid=user_bid).all()

    deleted_by_scope_and_key = {(row.shifu_bid, row.key): row.deleted for row in rows}
    assert deleted_by_scope_and_key == {
        ("", "sys_user_background"): 0,
        ("", "sys_user_style"): 0,
        ("", "sys_user_nickname"): 0,
        ("course-1", "sys_user_background"): 0,
        ("course-1", "sys_user_style"): 0,
    }


def test_clear_profile_keeps_v2_completed_and_preserves_legacy_values(app):
    from flaskr.service.profile.onboarding import (
        PROFILE_ONBOARDING_SCENE_KEY,
        PROFILE_ONBOARDING_VERSION,
        clear_profile_onboarding,
    )

    with app.app_context():
        user_bid = "profile-clear-preserved"
        _create_user(user_bid, learner_profile="existing profile")
        _add_profile_value(
            value_bid="clear-global-bg",
            user_bid=user_bid,
            key="sys_user_background",
            value="旧全局背景",
        )
        _add_profile_value(
            value_bid="clear-global-style",
            user_bid=user_bid,
            key="sys_user_style",
            value="旧全局风格",
        )
        _add_profile_value(
            value_bid="clear-global-name",
            user_bid=user_bid,
            key="sys_user_nickname",
            value="小明",
        )
        _add_profile_value(
            value_bid="clear-course-style",
            user_bid=user_bid,
            shifu_bid="course-1",
            key="sys_user_style",
            value="课程风格",
        )
        db.session.commit()

        result = clear_profile_onboarding(user_id=user_bid)
        user = UserInfo.query.filter_by(user_bid=user_bid).one()
        state = UserOnboardingState.query.filter_by(
            user_bid=user_bid,
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
            version=PROFILE_ONBOARDING_VERSION,
        ).one()
        rows = VariableValue.query.filter_by(user_bid=user_bid).all()

    assert result["completed"] is True
    assert result["trigger_source"] == "settings"
    assert result["learner_profile"] == ""
    assert result["learner_profile_updated_at"] is None
    assert user.learner_profile == ""
    assert user.learner_profile_updated_at is None
    assert state.status == "completed"
    assert {(row.shifu_bid, row.key): row.deleted for row in rows} == {
        ("", "sys_user_background"): 0,
        ("", "sys_user_style"): 0,
        ("", "sys_user_nickname"): 0,
        ("course-1", "sys_user_style"): 0,
    }


def test_late_skip_does_not_downgrade_completed_profile(app, monkeypatch):
    from flaskr.service.profile.onboarding import (
        complete_profile_onboarding,
        skip_profile_onboarding,
    )

    _allow_profile_safety(monkeypatch)
    with app.app_context():
        _create_user("profile-complete-then-skip")
        completed = complete_profile_onboarding(
            app,
            user_id="profile-complete-then-skip",
            learner_profile="最近关注：AI 教育",
            trigger_source="pasted",
        )
        skipped = skip_profile_onboarding(user_id="profile-complete-then-skip")
        user = UserInfo.query.filter_by(user_bid="profile-complete-then-skip").one()

    assert skipped["status"] == "completed"
    assert skipped["completed"] is True
    assert skipped["skipped"] is False
    assert skipped["completed_at"] == completed["completed_at"]
    assert user.learner_profile == "最近关注：AI 教育"


def test_repeated_completion_preserves_profile_and_state_timestamps(app, monkeypatch):
    from flaskr.service.profile.onboarding import complete_profile_onboarding

    _allow_profile_safety(monkeypatch)
    with app.app_context():
        _create_user("profile-repeat-complete")
        first = complete_profile_onboarding(
            app,
            user_id="profile-repeat-complete",
            learner_profile="表达风格：直接",
            trigger_source="guided",
        )
        second = complete_profile_onboarding(
            app,
            user_id="profile-repeat-complete",
            learner_profile="表达风格：直接",
            trigger_source="guided",
        )

    assert second["learner_profile_updated_at"] == first["learner_profile_updated_at"]
    assert second["completed_at"] == first["completed_at"]


def test_complete_rolls_back_profile_and_state_together(app, monkeypatch):
    from flaskr.service.profile.onboarding import (
        PROFILE_ONBOARDING_SCENE_KEY,
        complete_profile_onboarding,
    )

    _allow_profile_safety(monkeypatch)
    with app.app_context():
        _create_user("profile-atomic-failure", learner_profile="old profile")
        legacy_background = _add_profile_value(
            value_bid="rollback-global-bg",
            user_bid="profile-atomic-failure",
            key="sys_user_background",
            value="old background",
        )
        db.session.commit()
        original_commit = db.session.commit

        def fail_commit():
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(db.session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="database unavailable"):
            complete_profile_onboarding(
                app,
                user_id="profile-atomic-failure",
                learner_profile="new profile",
                trigger_source="settings",
            )
        monkeypatch.setattr(db.session, "commit", original_commit)

        user = UserInfo.query.filter_by(user_bid="profile-atomic-failure").one()
        state = UserOnboardingState.query.filter_by(
            user_bid="profile-atomic-failure",
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
        ).first()
        legacy_background = db.session.get(VariableValue, legacy_background.id)

    assert user.learner_profile == "old profile"
    assert state is None
    assert legacy_background.deleted == 0


def test_clear_rolls_back_profile_and_state_together(app, monkeypatch):
    from flaskr.service.profile.onboarding import (
        PROFILE_ONBOARDING_SCENE_KEY,
        clear_profile_onboarding,
    )

    with app.app_context():
        user_bid = "profile-clear-atomic-failure"
        _create_user(user_bid, learner_profile="old profile")
        legacy_style = _add_profile_value(
            value_bid="rollback-global-style",
            user_bid=user_bid,
            key="sys_user_style",
            value="old style",
        )
        db.session.commit()
        original_commit = db.session.commit

        def fail_commit():
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(db.session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="database unavailable"):
            clear_profile_onboarding(user_id=user_bid)
        monkeypatch.setattr(db.session, "commit", original_commit)

        user = UserInfo.query.filter_by(user_bid=user_bid).one()
        state = UserOnboardingState.query.filter_by(
            user_bid=user_bid,
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
        ).first()
        legacy_style = db.session.get(VariableValue, legacy_style.id)

    assert user.learner_profile == "old profile"
    assert user.learner_profile_updated_at == PROFILE_UPDATED_AT
    assert state is None
    assert legacy_style.deleted == 0
