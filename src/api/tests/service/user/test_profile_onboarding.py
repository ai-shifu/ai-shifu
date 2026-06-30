from types import SimpleNamespace

import pytest

from flaskr.dao import db
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.repository import create_user_entity


def _create_user(user_bid: str = "user-onboarding") -> None:
    create_user_entity(
        user_bid=user_bid,
        identify=user_bid,
        nickname="",
        language="zh-CN",
    )
    db.session.commit()


def test_profile_onboarding_config_roundtrip(app, monkeypatch):
    from flaskr.service.common import profile_onboarding as module

    saved_payloads = []
    current_config = {
        "enabled": False,
        "markdownflow": "",
        "version": 0,
        "updated_by": "",
        "updated_at": "",
    }

    monkeypatch.setattr(
        module, "load_profile_onboarding_config_payload", lambda: current_config
    )

    def fake_save_config(_app, payload, *, updated_by):
        saved_payloads.append((payload, updated_by))
        current_config.update(payload)

    monkeypatch.setattr(
        module, "save_profile_onboarding_config_payload", fake_save_config
    )

    result = module.update_profile_onboarding_config(
        app,
        payload={
            "enabled": True,
            "markdownflow": "?[%{{sys_user_nickname}}...怎么称呼你？]",
        },
        operator_user_bid="operator-1",
    )

    assert result["enabled"] is True
    assert result["markdownflow"] == "?[%{{sys_user_nickname}}...怎么称呼你？]"
    assert result["allowed_variable_keys"] == [
        "sys_user_nickname",
        "sys_user_style",
        "sys_user_background",
    ]
    assert saved_payloads[0][1] == "operator-1"


def test_profile_onboarding_config_rejects_non_whitelisted_variable(app):
    from flaskr.service.common.profile_onboarding import (
        update_profile_onboarding_config,
    )

    with pytest.raises(Exception):
        update_profile_onboarding_config(
            app,
            payload={
                "enabled": True,
                "markdownflow": "?[%{{sys_user_language}} 中文 | English]",
            },
            operator_user_bid="operator-1",
        )


def test_profile_onboarding_status_hides_after_skip(app):
    from flaskr.service.profile.onboarding import (
        PROFILE_ONBOARDING_STATE_KEY,
        complete_profile_onboarding,
        get_profile_onboarding_status,
    )

    with app.app_context():
        _create_user("user-onboarding-skip")
        result = complete_profile_onboarding(
            app,
            user_id="user-onboarding-skip",
            skipped=True,
            variables={},
        )

        state_row = VariableValue.query.filter_by(
            user_bid="user-onboarding-skip",
            shifu_bid="",
            key=PROFILE_ONBOARDING_STATE_KEY,
            deleted=0,
        ).first()
        status = get_profile_onboarding_status(app, user_id="user-onboarding-skip")

    assert result["completed"] is True
    assert result["skipped"] is True
    assert state_row is not None
    assert status["should_show"] is False


def test_profile_onboarding_complete_writes_allowed_system_profiles(app, monkeypatch):
    from flaskr.service.profile.onboarding import complete_profile_onboarding

    checked_text = []
    monkeypatch.setattr(
        "flaskr.service.profile.onboarding.check_text_content",
        lambda _app, user_id, value: checked_text.append((user_id, value)) or True,
    )

    with app.app_context():
        _create_user("user-onboarding-complete")
        result = complete_profile_onboarding(
            app,
            user_id="user-onboarding-complete",
            skipped=False,
            variables={
                "sys_user_nickname": "小明",
                "sys_user_style": "简洁",
                "sys_user_background": "产品经理",
            },
        )
        saved_values = {
            row.key: row.value
            for row in VariableValue.query.filter_by(
                user_bid="user-onboarding-complete",
                shifu_bid="",
                deleted=0,
            ).all()
        }

    assert result["completed"] is True
    assert result["skipped"] is False
    assert saved_values["sys_user_nickname"] == "小明"
    assert saved_values["sys_user_style"] == "简洁"
    assert saved_values["sys_user_background"] == "产品经理"
    assert checked_text == [
        ("user-onboarding-complete", "小明"),
        ("user-onboarding-complete", "产品经理"),
    ]


def test_profile_onboarding_routes_delegate(monkeypatch, test_client):
    dummy_user = SimpleNamespace(
        user_id="user-onboarding",
        language="zh-CN",
        is_operator=True,
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: dummy_user,
        raising=False,
    )

    monkeypatch.setattr(
        "flaskr.route.user.get_profile_onboarding_status",
        lambda _app, user_id: {"enabled": True, "should_show": True, "user": user_id},
    )
    monkeypatch.setattr(
        "flaskr.route.user.complete_profile_onboarding",
        lambda _app, user_id, skipped, variables: {
            "completed": True,
            "skipped": skipped,
            "variables": variables,
            "user": user_id,
        },
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.route.get_operator_profile_onboarding_config",
        lambda _app: {"enabled": False},
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.admin_operations.route.update_operator_profile_onboarding_config",
        lambda _app, payload, operator_user_bid: {
            "enabled": payload["enabled"],
            "operator": operator_user_bid,
        },
    )

    status_resp = test_client.get(
        "/api/user/profile-onboarding",
        headers={"Token": "token"},
    )
    complete_resp = test_client.post(
        "/api/user/profile-onboarding/complete",
        headers={"Token": "token"},
        json={"skipped": False, "variables": {"sys_user_nickname": "小明"}},
    )
    admin_get_resp = test_client.get(
        "/api/shifu/admin/operations/profile-onboarding",
        headers={"Token": "token"},
    )
    admin_post_resp = test_client.post(
        "/api/shifu/admin/operations/profile-onboarding",
        headers={"Token": "token"},
        json={"enabled": True, "markdownflow": ""},
    )

    assert status_resp.get_json(force=True)["data"]["should_show"] is True
    assert complete_resp.get_json(force=True)["data"]["variables"] == {
        "sys_user_nickname": "小明"
    }
    assert admin_get_resp.get_json(force=True)["data"]["enabled"] is False
    assert admin_post_resp.get_json(force=True)["data"] == {
        "enabled": True,
        "operator": "user-onboarding",
    }
