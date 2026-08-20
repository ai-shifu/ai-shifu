"""Verify learner profile service behavior."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from flaskr.api.check.dto import (
    CHECK_RESULT_REJECT,
    CHECK_RESULT_REVIEW,
    CHECK_RESULT_UNCONF,
    CHECK_RESULT_UNKNOWN,
)
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.models import UserInfo, UserOnboardingState
from flaskr.service.user.repository import (
    create_user_entity,
    load_user_aggregate,
    upsert_credential,
)

PROFILE_UPDATED_AT = datetime(2026, 8, 1, 8, 30, tzinfo=UTC)


def _assert_orm_utc(value: datetime | None, expected: datetime) -> None:
    assert value is not None
    assert value.replace(tzinfo=UTC) == expected


def _create_user(
    user_bid: str,
    *,
    identify: str | None = None,
    learner_profile: str = "",
    nickname: str = "Test learner",
) -> UserInfo:
    user = create_user_entity(
        user_bid=user_bid,
        identify=identify or user_bid,
        nickname=nickname,
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


def _track_profile_lock_reads(monkeypatch) -> list[tuple[str, str, bool, bool]]:
    query_type = type(UserInfo.query)
    original_first = query_type.first
    read_order: list[tuple[str, str, bool, bool]] = []

    def track_first(query):
        statement = str(query.statement)
        parameters = query.statement.compile().params
        table = (
            "user_onboarding_states"
            if "user_onboarding_states" in statement
            else "user_users"
            if "user_users" in statement
            else "other"
        )
        read_order.append(
            (
                table,
                str(parameters.get("user_bid_1", "")),
                query._for_update_arg is not None,
                bool(query.load_options._populate_existing),
            )
        )
        return original_first(query)

    monkeypatch.setattr(query_type, "first", track_first)
    return read_order


def test_repository_aggregate_exposes_learner_profile(app):
    with app.app_context():
        _create_user("profile-aggregate", learner_profile="偏好图表和简洁表达")
        aggregate = load_user_aggregate("profile-aggregate")

    assert aggregate is not None
    assert aggregate.learner_profile == "偏好图表和简洁表达"
    _assert_orm_utc(aggregate.learner_profile_updated_at, PROFILE_UPDATED_AT)


def test_empty_profile_prefill_uses_canonical_nickname_and_latest_legacy_values(app):
    from flaskr.service.profile.learner_profile import get_learner_profile

    with app.app_context():
        user_bid = "profile-legacy-prefill"
        _create_user(user_bid, nickname="当前称呼")
        _add_profile_value(
            value_bid="legacy-name-old",
            user_bid=user_bid,
            key="sys_user_nickname",
            value="旧称呼",
        )
        _add_profile_value(
            value_bid="legacy-name-new",
            user_bid=user_bid,
            key="sys_user_nickname",
            value="小林",
        )
        _add_profile_value(
            value_bid="legacy-background",
            user_bid=user_bid,
            key="sys_user_background",
            value="办公室工作",
        )
        _add_profile_value(
            value_bid="legacy-style",
            user_bid=user_bid,
            key="sys_user_style",
            value="亲切直接",
        )
        _add_profile_value(
            value_bid="course-style",
            user_bid=user_bid,
            shifu_bid="course-1",
            key="sys_user_style",
            value="仅属于旧课程的风格",
        )
        db.session.commit()

        loaded = get_learner_profile(user_id=user_bid)

    assert loaded["learner_profile"] == ""
    assert loaded["nickname"] == "当前称呼"
    assert loaded["nickname_max_length"] == 64
    assert loaded["legacy_profile_values"] == {
        "sys_user_nickname": "当前称呼",
        "sys_user_background": "办公室工作",
        "sys_user_style": "亲切直接",
    }


@pytest.mark.parametrize(
    ("identifier", "legacy_nickname", "suffix", "expected_nickname"),
    [
        ("13800138007", "13800138007", "phone-same", None),
        ("13800138007", "13900139007", "phone-different", "13900139007"),
        (
            "nickname@example.com",
            "nickname@example.com",
            "email-same",
            None,
        ),
        (
            "account@example.com",
            "nickname@example.net",
            "email-different",
            "nickname@example.net",
        ),
    ],
)
def test_legacy_nickname_account_identifier_filter_is_exact(
    app,
    identifier,
    legacy_nickname,
    suffix,
    expected_nickname,
):
    from flaskr.service.profile.learner_profile import get_learner_profile

    with app.app_context():
        user_bid = f"profile-explicit-{suffix}"
        _create_user(user_bid, identify=identifier, nickname=identifier)
        _add_profile_value(
            value_bid=f"legacy-explicit-{suffix}",
            user_bid=user_bid,
            key="sys_user_nickname",
            value=legacy_nickname,
        )
        db.session.commit()

        loaded = get_learner_profile(user_id=user_bid)

    assert loaded["legacy_profile_values"].get("sys_user_nickname") == expected_nickname
    assert loaded["nickname"] == ""


@pytest.mark.parametrize(
    ("identifier", "nickname", "suffix"),
    [
        ("13800138007", "13900139007", "phone"),
        ("account@example.com", "nickname@example.net", "email"),
    ],
)
def test_identifier_shaped_canonical_nickname_for_different_value_is_prefilled(
    app,
    identifier,
    nickname,
    suffix,
):
    from flaskr.service.profile.learner_profile import get_learner_profile

    with app.app_context():
        user_bid = f"profile-shaped-{suffix}"
        _create_user(user_bid, identify=identifier, nickname=nickname)
        db.session.commit()

        loaded = get_learner_profile(user_id=user_bid)

    assert loaded["legacy_profile_values"]["sys_user_nickname"] == nickname


@pytest.mark.parametrize(
    ("nickname", "suffix", "expected_nickname"),
    [
        ("credential@example.com", "same", None),
        ("other@example.net", "different", "other@example.net"),
    ],
)
def test_credential_identifier_filter_is_exact(
    app,
    nickname,
    suffix,
    expected_nickname,
):
    from flaskr.service.profile.learner_profile import get_learner_profile

    with app.app_context():
        user_bid = f"profile-credential-{suffix}"
        _create_user(user_bid, identify=user_bid, nickname=nickname)
        upsert_credential(
            app,
            user_bid=user_bid,
            provider_name="email",
            subject_id="credential@example.com",
            subject_format="email",
            identifier="credential@example.com",
            metadata={},
            verified=True,
        )
        db.session.commit()

        loaded = get_learner_profile(user_id=user_bid)

    assert loaded["legacy_profile_values"].get("sys_user_nickname") == expected_nickname
    assert loaded["nickname"] == (nickname if expected_nickname else "")


def test_identifier_fallback_prefers_explicit_legacy_nickname(app):
    from flaskr.service.profile.learner_profile import get_learner_profile

    with app.app_context():
        user_bid = "profile-identifier-with-legacy-name"
        identifier = "legacy-name@example.com"
        _create_user(user_bid, identify=identifier, nickname=identifier)
        _add_profile_value(
            value_bid="legacy-name-user-choice",
            user_bid=user_bid,
            key="sys_user_nickname",
            value="小林",
        )
        db.session.commit()

        loaded = get_learner_profile(user_id=user_bid)

    assert loaded["legacy_profile_values"]["sys_user_nickname"] == "小林"


def test_identifier_fallback_does_not_revive_cleared_legacy_nickname(app):
    from flaskr.service.profile.learner_profile import get_learner_profile

    with app.app_context():
        user_bid = "1234567890abcdef1234567890abcdef"
        _create_user(user_bid, identify=user_bid, nickname=user_bid)
        _add_profile_value(
            value_bid="legacy-uuid-name-old",
            user_bid=user_bid,
            key="sys_user_nickname",
            value="旧称呼",
        )
        _add_profile_value(
            value_bid="legacy-uuid-name-cleared",
            user_bid=user_bid,
            key="sys_user_nickname",
            value="  ",
        )
        db.session.commit()

        loaded = get_learner_profile(user_id=user_bid)

    assert "sys_user_nickname" not in loaded["legacy_profile_values"]


def test_user_bid_fallback_is_not_profile_prefill_after_identifier_changes(app):
    from flaskr.service.profile.learner_profile import get_learner_profile

    with app.app_context():
        user_bid = "abcdef1234567890abcdef1234567890"
        _create_user(
            user_bid,
            identify="current-account@example.com",
            nickname=user_bid,
        )
        db.session.commit()

        loaded = get_learner_profile(user_id=user_bid)

    assert "sys_user_nickname" not in loaded["legacy_profile_values"]


def test_empty_legacy_values_do_not_revive_older_prefill_values(app):
    from flaskr.service.profile.learner_profile import get_learner_profile

    with app.app_context():
        user_bid = "profile-legacy-prefill-cleared"
        _create_user(user_bid, nickname="")
        for key, old_value in (
            ("sys_user_nickname", "旧称呼"),
            ("sys_user_background", "旧背景"),
            ("sys_user_style", "旧风格"),
        ):
            _add_profile_value(
                value_bid=f"{key}-old",
                user_bid=user_bid,
                key=key,
                value=old_value,
            )
            _add_profile_value(
                value_bid=f"{key}-cleared",
                user_bid=user_bid,
                key=key,
                value="  ",
            )
        db.session.commit()

        loaded = get_learner_profile(user_id=user_bid)

    assert loaded["learner_profile"] == ""
    assert loaded["legacy_profile_values"] == {}


def test_canonical_profile_does_not_expose_legacy_prefill_values(app):
    from flaskr.service.profile.learner_profile import get_learner_profile

    with app.app_context():
        user_bid = "profile-no-legacy-prefill"
        _create_user(user_bid, learner_profile="正式学习者画像")
        _add_profile_value(
            value_bid="legacy-background-hidden",
            user_bid=user_bid,
            key="sys_user_background",
            value="旧背景不应返回",
        )
        db.session.commit()

        loaded = get_learner_profile(user_id=user_bid)

    assert loaded["learner_profile"] == "正式学习者画像"
    assert loaded["legacy_profile_values"] == {}


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
            nickname="小明",
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
    assert loaded["nickname"] == "小明"
    assert loaded["max_length"] == 1000
    assert first_updated_at is not None
    assert first_updated_at.endswith("Z")
    assert unchanged["learner_profile_updated_at"] == first_updated_at
    assert cleared["learner_profile"] == ""
    assert cleared["learner_profile_updated_at"] is None
    assert cleared["has_learner_profile"] is False
    assert cleared["nickname"] == "小明"
    assert cleared["max_length"] == 1000
    assert cleared["completed"] is True
    assert cleared["trigger_source"] == "settings"
    assert checked == [
        ("profile-replace", "称呼：小明\n幻灯片风格：留白多"),
        ("profile-replace", "小明"),
    ]


@pytest.mark.parametrize(
    "value",
    [None, 1, "🙂" * 1001],
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
        with pytest.raises(AppError):
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


def test_replace_atomically_saves_explicit_nickname(app, monkeypatch):
    from flaskr.service.profile.learner_profile import replace_learner_profile

    _allow_profile_safety(monkeypatch)
    with app.app_context():
        user_bid = "profile-sync-nickname"
        _create_user(user_bid)
        replace_learner_profile(
            app,
            user_id=user_bid,
            learner_profile=(
                "可以叫我小雨。我是产品经理，希望先讲核心概念，再用实际案例。"
            ),
            nickname="小雨",
        )
        stored = UserInfo.query.filter_by(user_bid=user_bid).one()

    assert stored.nickname == "小雨"


def test_replace_without_nickname_preserves_display_name(app, monkeypatch):
    from flaskr.service.profile.learner_profile import replace_learner_profile

    _allow_profile_safety(monkeypatch)
    with app.app_context():
        user_bid = "profile-preserve-nickname"
        _create_user(user_bid)
        replace_learner_profile(
            app,
            user_id=user_bid,
            learner_profile="我是产品经理，希望先讲核心概念，再用实际案例。",
        )
        stored = UserInfo.query.filter_by(user_bid=user_bid).one()

    assert stored.nickname == "Test learner"


def test_replace_explicit_empty_nickname_clears_display_name(app, monkeypatch):
    from flaskr.service.profile.learner_profile import replace_learner_profile

    checked = _allow_profile_safety(monkeypatch)
    with app.app_context():
        user_bid = "profile-clear-nickname"
        _create_user(user_bid)
        result = replace_learner_profile(
            app,
            user_id=user_bid,
            learner_profile="",
            nickname="",
        )
        stored = UserInfo.query.filter_by(user_bid=user_bid).one()

    assert result["learner_profile"] == ""
    assert result["nickname"] == ""
    assert result["completed"] is True
    assert stored.nickname == ""
    assert checked == []


def test_replace_empty_profile_can_save_nickname_and_handled_state(app, monkeypatch):
    from flaskr.service.profile.learner_profile import replace_learner_profile

    checked = _allow_profile_safety(monkeypatch)
    with app.app_context():
        user_bid = "profile-nickname-only"
        _create_user(user_bid, nickname="")
        result = replace_learner_profile(
            app,
            user_id=user_bid,
            learner_profile="",
            nickname="小林",
        )
        stored = UserInfo.query.filter_by(user_bid=user_bid).one()

    assert result["learner_profile"] == ""
    assert result["nickname"] == "小林"
    assert result["completed"] is True
    assert stored.nickname == "小林"
    assert checked == [(user_bid, "小林")]


@pytest.mark.parametrize("nickname", [1, "🙂" * 65])
def test_replace_rejects_invalid_nickname_without_overwriting(
    app, monkeypatch, nickname
):
    from flaskr.service.profile.learner_profile import replace_learner_profile

    _allow_profile_safety(monkeypatch)
    with app.app_context():
        user_bid = f"profile-invalid-nickname-{type(nickname).__name__}"
        _create_user(user_bid, learner_profile="existing profile")
        with pytest.raises(AppError):
            replace_learner_profile(
                app,
                user_id=user_bid,
                learner_profile="new profile",
                nickname=nickname,
            )
        stored = UserInfo.query.filter_by(user_bid=user_bid).one()

    assert stored.learner_profile == "existing profile"
    assert stored.nickname == "Test learner"


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
        with pytest.raises(AppError) as caught_error:
            replace_learner_profile(
                app,
                user_id="profile-safety-reject",
                learner_profile="rejected profile",
            )
        loaded = get_learner_profile(user_id="profile-safety-reject")
        stored = UserInfo.query.filter_by(user_bid="profile-safety-reject").one()

    assert loaded["learner_profile"] == "existing profile"
    assert stored.nickname == "Test learner"
    assert caught_error.value.message == "please check the content"


@pytest.mark.parametrize(
    "check_result",
    [
        CHECK_RESULT_REVIEW,
        CHECK_RESULT_UNKNOWN,
        CHECK_RESULT_UNCONF,
    ],
)
def test_profile_moderation_allows_every_non_reject_result(
    app, monkeypatch, check_result
):
    from flaskr.api.check.dto import CheckResultDTO
    from flaskr.service.profile.learner_profile import (
        get_learner_profile,
        replace_learner_profile,
    )

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text",
        lambda *_args, **_kwargs: CheckResultDTO(
            check_result=check_result,
            risk_labels=[],
            risk_label_ids=[],
            provider="test-provider",
            raw_data={},
        ),
    )

    with app.app_context():
        user_bid = f"profile-moderation-{check_result}"
        _create_user(user_bid, learner_profile="existing profile")
        replace_learner_profile(
            app,
            user_id=user_bid,
            learner_profile="Please call me Accepted Name.",
            nickname="Accepted Name",
        )
        loaded = get_learner_profile(user_id=user_bid)
        stored = UserInfo.query.filter_by(user_bid=user_bid).one()
        state = UserOnboardingState.query.filter_by(user_bid=user_bid).first()

    assert loaded["learner_profile"] == "Please call me Accepted Name."
    assert stored.nickname == "Accepted Name"
    assert state is not None


def test_profile_moderation_rejects_only_explicit_reject(app, monkeypatch):
    from flaskr.api.check.dto import CheckResultDTO
    from flaskr.service.profile.learner_profile import (
        get_learner_profile,
        replace_learner_profile,
    )

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text",
        lambda *_args, **_kwargs: CheckResultDTO(
            check_result=CHECK_RESULT_REJECT,
            risk_labels=[],
            risk_label_ids=[],
            provider="test-provider",
            raw_data={},
        ),
    )

    with app.app_context():
        user_bid = "profile-moderation-reject"
        _create_user(user_bid, learner_profile="existing profile")
        with pytest.raises(AppError) as caught_error:
            replace_learner_profile(
                app,
                user_id=user_bid,
                learner_profile="Please call me Rejected Name.",
                nickname="Rejected Name",
            )
        loaded = get_learner_profile(user_id=user_bid)
        stored = UserInfo.query.filter_by(user_bid=user_bid).one()
        state = UserOnboardingState.query.filter_by(user_bid=user_bid).first()

    assert caught_error.value.message == "please check the content"
    assert loaded["learner_profile"] == "existing profile"
    assert stored.nickname == "Test learner"
    assert state is None


def test_nickname_rejection_rolls_back_profile_nickname_and_state(app, monkeypatch):
    from flaskr.service.profile.learner_profile import (
        get_learner_profile,
        replace_learner_profile,
    )

    checked: list[str] = []

    def reject_nickname(_app, _user_id, text):
        checked.append(text)
        return text != "Rejected nickname"

    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        reject_nickname,
    )

    with app.app_context():
        user_bid = "profile-nickname-reject"
        _create_user(user_bid, learner_profile="existing profile")
        with pytest.raises(AppError) as caught_error:
            replace_learner_profile(
                app,
                user_id=user_bid,
                learner_profile="accepted new profile",
                nickname="Rejected nickname",
            )
        loaded = get_learner_profile(user_id=user_bid)
        stored = UserInfo.query.filter_by(user_bid=user_bid).one()
        state = UserOnboardingState.query.filter_by(user_bid=user_bid).first()

    assert caught_error.value.message == "please check the content"
    assert checked == ["accepted new profile", "Rejected nickname"]
    assert loaded["learner_profile"] == "existing profile"
    assert stored.nickname == "Test learner"
    assert state is None


def test_profile_moderation_allows_save_when_provider_is_unavailable(app):
    from flaskr.service.profile.learner_profile import (
        get_learner_profile,
        replace_learner_profile,
    )

    app.config["CHECK_PROVIDER"] = "unsupported-provider"
    with app.app_context():
        _create_user("profile-provider-unavailable", learner_profile="existing profile")
        replace_learner_profile(
            app,
            user_id="profile-provider-unavailable",
            learner_profile="Please call me Unchecked Name.",
            nickname="Unchecked Name",
        )
        loaded = get_learner_profile(user_id="profile-provider-unavailable")
        stored = UserInfo.query.filter_by(user_bid="profile-provider-unavailable").one()
        state = UserOnboardingState.query.filter_by(
            user_bid="profile-provider-unavailable"
        ).first()

    assert loaded["learner_profile"] == "Please call me Unchecked Name."
    assert stored.nickname == "Unchecked Name"
    assert state is not None


def test_profile_safety_audit_records_text_and_provider_response(app, monkeypatch):
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
        _create_user("profile-audit")
        replace_learner_profile(
            app,
            user_id="profile-audit",
            learner_profile=profile,
        )
        audit_row = RiskControlResult.query.filter_by(user_id="profile-audit").one()

    assert checked["text"] == profile
    assert checked["user_id"] == "profile-audit"
    assert audit_row.chat_id == checked["check_id"]
    assert audit_row.check_vendor == "test-provider"
    assert audit_row.check_result == CHECK_RESULT_PASS
    assert audit_row.check_strategy == "check_learner_profile"
    assert audit_row.text == profile
    assert audit_row.check_resp == str(
        {"echo": profile, "provider_request_id": "private-provider-id"}
    )


def test_legacy_status_hides_for_canonical_profile_or_fixed_v2_state(app, monkeypatch):
    from flaskr.service.profile import onboarding as onboarding_module
    from flaskr.service.profile.learner_profile import (
        PROFILE_ONBOARDING_SCENE_KEY,
        PROFILE_ONBOARDING_VERSION,
    )
    from flaskr.service.profile.onboarding import get_profile_onboarding_status

    monkeypatch.setattr(
        onboarding_module,
        "load_profile_onboarding_config_payload",
        lambda *_args, **_kwargs: {
            "enabled": True,
            "markdownflow": "?[%{{sys_user_background}}...背景]",
            "version": 7,
        },
    )

    with app.app_context():
        _create_user("profile-status-new")
        _create_user("profile-status-canonical", learner_profile="已有画像")
        _create_user("profile-status-v2")
        db.session.add(
            UserOnboardingState(
                user_bid="profile-status-v2",
                scene_key=PROFILE_ONBOARDING_SCENE_KEY,
                version=PROFILE_ONBOARDING_VERSION,
                status="completed",
                trigger_source="settings",
                completed_at=PROFILE_UPDATED_AT,
            )
        )
        db.session.commit()
        new_status = get_profile_onboarding_status(app, user_id="profile-status-new")
        canonical_status = get_profile_onboarding_status(
            app, user_id="profile-status-canonical"
        )
        v2_status = get_profile_onboarding_status(app, user_id="profile-status-v2")

    assert new_status["should_show"] is True
    assert canonical_status["should_show"] is False
    assert v2_status["should_show"] is False
    assert set(v2_status) == {
        "enabled",
        "should_show",
        "markdownflow",
        "allowed_variable_keys",
        "current_values",
    }


def test_complete_atomically_writes_profile_and_fixed_v2_state(app, monkeypatch):
    from flaskr.service.profile.learner_profile import (
        PROFILE_ONBOARDING_SCENE_KEY,
        PROFILE_ONBOARDING_VERSION,
        save_learner_profile,
    )

    checked = _allow_profile_safety(monkeypatch)
    with app.app_context():
        _create_user("profile-complete")
        result = save_learner_profile(
            app,
            user_id="profile-complete",
            learner_profile="称呼：小明\n表达风格：简洁",
            trigger_source="guided",
            nickname="小明",
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
    assert user.nickname == "小明"
    assert state.status == "completed"
    assert state.completed_at is not None
    assert variable_values == []
    assert checked == [
        ("profile-complete", "称呼：小明\n表达风格：简洁"),
        ("profile-complete", "小明"),
    ]


@pytest.mark.parametrize(
    ("learner_profile", "nickname", "expected_checked"),
    [
        ("Existing profile", "New nickname", ["New nickname"]),
        ("Updated profile", "Existing nickname", ["Updated profile"]),
        ("Existing profile", "Existing nickname", []),
    ],
)
def test_save_moderates_only_changed_nonempty_fields(
    app,
    monkeypatch,
    learner_profile,
    nickname,
    expected_checked,
):
    from flaskr.service.profile.learner_profile import save_learner_profile

    checked = _allow_profile_safety(monkeypatch)
    with app.app_context():
        user_bid = f"profile-moderate-changed-{len(expected_checked)}-{nickname}"
        _create_user(
            user_bid,
            learner_profile="Existing profile",
            nickname="Existing nickname",
        )

        save_learner_profile(
            app,
            user_id=user_bid,
            learner_profile=learner_profile,
            trigger_source="settings",
            nickname=nickname,
        )

    assert checked == [(user_bid, value) for value in expected_checked]


def test_save_locks_user_then_state_before_writing_profile(app, monkeypatch):
    from flaskr.service.profile.learner_profile import save_learner_profile

    with app.app_context():
        user_bid = "profile-save-lock-order"
        _create_user(user_bid)
        read_order = _track_profile_lock_reads(monkeypatch)
        reads_when_moderated: list[tuple[str, str, bool, bool]] = []

        def allow_after_user_lock(_app, _user_id, _text):
            reads_when_moderated.extend(read_order)
            return True

        monkeypatch.setattr(
            "flaskr.service.profile.learner_profile.check_text_content",
            allow_after_user_lock,
        )

        result = save_learner_profile(
            app,
            user_id=user_bid,
            learner_profile="Please call me Locked Learner.",
            trigger_source="settings",
        )

    profile_snapshot_reads = [
        read
        for read in read_order
        if read[0] in {"user_users", "user_onboarding_states"}
    ]
    assert profile_snapshot_reads[:2] == [
        ("user_users", user_bid, True, True),
        ("user_onboarding_states", user_bid, True, True),
    ]
    assert [
        read
        for read in reads_when_moderated
        if read[0] in {"user_users", "user_onboarding_states"}
    ] == [("user_users", user_bid, True, True)]
    assert result["learner_profile"] == "Please call me Locked Learner."


def test_save_moderates_once_when_state_creation_retries(app, monkeypatch):
    from flaskr.service.profile import learner_profile

    moderation_calls: list[str] = []
    operation_calls = 0

    def allow_once(_app, _user_id, text):
        moderation_calls.append(text)
        return True

    def run_twice(operation, *, user_id):
        nonlocal operation_calls
        assert user_id == "profile-save-moderation-retry"
        operation()
        operation_calls += 1
        result = operation()
        operation_calls += 1
        return result

    monkeypatch.setattr(learner_profile, "check_text_content", allow_once)
    monkeypatch.setattr(
        learner_profile,
        "_commit_with_state_race_retry",
        run_twice,
    )

    with app.app_context():
        user_bid = "profile-save-moderation-retry"
        _create_user(user_bid)
        result = learner_profile.save_learner_profile(
            app,
            user_id=user_bid,
            learner_profile="Please call me Retry Learner.",
            trigger_source="settings",
        )

    assert operation_calls == 2
    assert moderation_calls == ["Please call me Retry Learner."]
    assert result["learner_profile"] == "Please call me Retry Learner."


def test_clear_locks_user_then_state_before_clearing_profile(app, monkeypatch):
    from flaskr.service.profile.learner_profile import clear_learner_profile

    with app.app_context():
        user_bid = "profile-clear-lock-order"
        _create_user(user_bid, learner_profile="Profile to clear")
        read_order = _track_profile_lock_reads(monkeypatch)

        result = clear_learner_profile(user_id=user_bid)

    profile_snapshot_reads = [
        read
        for read in read_order
        if read[0] in {"user_users", "user_onboarding_states"}
    ]
    assert profile_snapshot_reads[:2] == [
        ("user_users", user_bid, True, True),
        ("user_onboarding_states", user_bid, True, True),
    ]
    assert result["learner_profile"] == ""


def test_complete_preserves_legacy_variable_values_for_old_courses(app, monkeypatch):
    from flaskr.service.profile.learner_profile import save_learner_profile

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

        save_learner_profile(
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


def test_clear_profile_keeps_v2_completed_and_returns_legacy_prefill(app):
    from flaskr.service.profile.learner_profile import (
        PROFILE_ONBOARDING_SCENE_KEY,
        PROFILE_ONBOARDING_VERSION,
        clear_learner_profile,
        get_learner_profile,
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

        result = clear_learner_profile(user_id=user_bid)
        loaded = get_learner_profile(user_id=user_bid)
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
    assert loaded["legacy_profile_values"] == {
        "sys_user_background": "旧全局背景",
        "sys_user_style": "旧全局风格",
    }
    assert user.learner_profile == ""
    assert user.learner_profile_updated_at is None
    assert user.nickname == "Test learner"
    assert state.status == "completed"
    assert {(row.shifu_bid, row.key): row.deleted for row in rows} == {
        ("", "sys_user_background"): 0,
        ("", "sys_user_style"): 0,
        ("", "sys_user_nickname"): 0,
        ("course-1", "sys_user_style"): 0,
    }


def test_empty_profile_save_returns_legacy_prefill_on_next_get(app, monkeypatch):
    from flaskr.service.profile.learner_profile import (
        PROFILE_ONBOARDING_SCENE_KEY,
        PROFILE_ONBOARDING_VERSION,
        get_learner_profile,
        replace_learner_profile,
    )

    checked = _allow_profile_safety(monkeypatch)
    with app.app_context():
        user_bid = "profile-empty-save-prefill"
        _create_user(user_bid, learner_profile="existing profile", nickname="")
        _add_profile_value(
            value_bid="empty-save-background",
            user_bid=user_bid,
            key="sys_user_background",
            value="办公室工作",
        )
        _add_profile_value(
            value_bid="empty-save-style",
            user_bid=user_bid,
            key="sys_user_style",
            value="亲切直接",
        )
        _add_profile_value(
            value_bid="empty-save-nickname",
            user_bid=user_bid,
            key="sys_user_nickname",
            value="旧称呼",
        )
        db.session.commit()

        saved = replace_learner_profile(
            app,
            user_id=user_bid,
            learner_profile="",
        )
        loaded = get_learner_profile(user_id=user_bid)
        state = UserOnboardingState.query.filter_by(
            user_bid=user_bid,
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
            version=PROFILE_ONBOARDING_VERSION,
        ).one()

    assert saved["learner_profile"] == ""
    assert loaded["learner_profile"] == ""
    assert loaded["legacy_profile_values"] == {
        "sys_user_background": "办公室工作",
        "sys_user_style": "亲切直接",
    }
    assert state.status == "completed"
    assert checked == []


def test_repeated_completion_preserves_profile_and_state_timestamps(app, monkeypatch):
    from flaskr.service.profile.learner_profile import save_learner_profile

    _allow_profile_safety(monkeypatch)
    with app.app_context():
        _create_user("profile-repeat-complete")
        first = save_learner_profile(
            app,
            user_id="profile-repeat-complete",
            learner_profile="表达风格：直接",
            trigger_source="guided",
        )
        second = save_learner_profile(
            app,
            user_id="profile-repeat-complete",
            learner_profile="表达风格：直接",
            trigger_source="guided",
        )

    assert second["learner_profile_updated_at"] == first["learner_profile_updated_at"]
    assert second["completed_at"] == first["completed_at"]


def test_complete_rolls_back_profile_and_state_together(app, monkeypatch):
    from flaskr.service.profile.learner_profile import (
        PROFILE_ONBOARDING_SCENE_KEY,
        save_learner_profile,
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
            save_learner_profile(
                app,
                user_id="profile-atomic-failure",
                learner_profile="可以叫我新名字。新的画像内容。",
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
    assert user.nickname == "Test learner"
    assert state is None
    assert legacy_background.deleted == 0


def test_clear_rolls_back_profile_and_state_together(app, monkeypatch):
    from flaskr.service.profile.learner_profile import (
        PROFILE_ONBOARDING_SCENE_KEY,
        clear_learner_profile,
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
            clear_learner_profile(user_id=user_bid)
        monkeypatch.setattr(db.session, "commit", original_commit)

        user = UserInfo.query.filter_by(user_bid=user_bid).one()
        state = UserOnboardingState.query.filter_by(
            user_bid=user_bid,
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
        ).first()
        legacy_style = db.session.get(VariableValue, legacy_style.id)

    assert user.learner_profile == "old profile"
    _assert_orm_utc(user.learner_profile_updated_at, PROFILE_UPDATED_AT)
    assert user.nickname == "Test learner"
    assert state is None
    assert legacy_style.deleted == 0
