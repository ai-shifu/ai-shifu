"""Verify password HTTP route behavior."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import jwt
from flaskr.service.user import phone_flow
from redis.exceptions import RedisError

if TYPE_CHECKING:
    import pytest
    from flask import Flask
    from flask.testing import FlaskClient

    from tests.common.fixtures.fake_redis import FakeRedis


_HTTP_OK = 200
_INVALID_CREDENTIALS_CODE = 1016
_PASSWORD_LOGIN_RATE_LIMITED_CODE = 1028
_TEST_IDENTIFIER_FAILURE_LIMIT = 2
_TEST_IP_FAILURE_LIMIT = 100
_TEST_FAILURE_WINDOW_SECONDS = 300
_PASSWORD_COUNTER_KEY_COUNT = 2


def _post_json(
    client,
    path: str,
    payload: dict,
    headers: dict | None = None,
    environ_overrides: dict | None = None,
):
    resp = client.post(
        path,
        data=json.dumps(payload),
        content_type="application/json",
        headers=headers or {},
        environ_overrides=environ_overrides,
    )
    return resp, json.loads(resp.data)


def test_reset_password_does_not_create_new_user(test_client, app):
    from flaskr.service.user.models import UserInfo as UserEntity

    phone = "15500009999"

    # No user exists yet for this phone number.
    with app.app_context():
        assert UserEntity.query.filter_by(user_identify=phone).count() == 0

    resp, body = _post_json(
        test_client,
        "/api/user/reset_password",
        {
            "identifier": phone,
            "code": "9999",
            "new_password": "Abcd1234",
        },
    )

    assert resp.status_code == 200
    assert body["code"] == 1001  # server.user.userNotFound

    with app.app_context():
        assert UserEntity.query.filter_by(user_identify=phone).count() == 0


def test_set_password_requires_login_and_verification_code(test_client, app):
    from flaskr.service.user import phone_flow

    phone = "15500001111"

    with app.app_context():
        user_token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=phone, code="9999"
        )

    token_value = user_token.token
    headers = {"Token": token_value}

    resp, body = _post_json(
        test_client,
        "/api/user/set_password",
        {
            "identifier": phone,
            "code": "9999",
            "new_password": "Abcd1234",
        },
        headers=headers,
    )

    assert resp.status_code == 200
    assert body["code"] == 0
    assert body["data"]["success"] is True

    # Second attempt should be rejected as already set.
    resp2, body2 = _post_json(
        test_client,
        "/api/user/set_password",
        {
            "identifier": phone,
            "code": "9999",
            "new_password": "Abcd1234",
        },
        headers=headers,
    )

    assert resp2.status_code == 200
    assert body2["code"] == 1017  # server.user.passwordAlreadySet


def test_password_login_after_setting_password(test_client, app):
    from flaskr.service.user import phone_flow

    phone = "15500002222"
    password = "Abcd1234"

    with app.app_context():
        user_token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=phone, code="9999"
        )

    # Set password (logged in)
    _post_json(
        test_client,
        "/api/user/set_password",
        {"identifier": phone, "code": "9999", "new_password": password},
        headers={"Token": user_token.token},
    )

    # Login via password (logged out)
    resp, body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": phone, "password": password},
    )

    assert resp.status_code == 200
    assert body["code"] == 0
    assert body["data"]["token"]
    assert body["data"]["userInfo"]["mobile"] == phone


def test_password_login_throttles_identifier_and_success_resets_it(
    test_client: FlaskClient,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    mock_redis_client: FakeRedis,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Throttle repeated account failures while allowing a success to reset them."""
    phone = "15500002223"
    password = "Abcd1234"
    monkeypatch.setitem(
        app.config,
        "PASSWORD_LOGIN_IDENTIFIER_FAILURE_LIMIT",
        _TEST_IDENTIFIER_FAILURE_LIMIT,
    )
    monkeypatch.setitem(
        app.config,
        "PASSWORD_LOGIN_IP_FAILURE_LIMIT",
        _TEST_IP_FAILURE_LIMIT,
    )
    monkeypatch.setitem(
        app.config,
        "PASSWORD_LOGIN_FAILURE_WINDOW_SECONDS",
        _TEST_FAILURE_WINDOW_SECONDS,
    )

    with app.app_context():
        user_token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=phone, code="9999"
        )

    _post_json(
        test_client,
        "/api/user/set_password",
        {"identifier": phone, "code": "9999", "new_password": password},
        headers={"Token": user_token.token},
    )

    first_failure, first_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": phone, "password": "wrong-password"},
    )
    assert first_failure.status_code == _HTTP_OK
    assert first_body["code"] == _INVALID_CREDENTIALS_CODE

    success, success_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": phone, "password": password},
    )
    assert success.status_code == _HTTP_OK
    assert success_body["code"] == 0

    after_reset, after_reset_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": phone, "password": "wrong-again"},
    )
    assert after_reset.status_code == _HTTP_OK
    assert after_reset_body["code"] == _INVALID_CREDENTIALS_CODE

    blocked, blocked_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": phone, "password": "wrong-twice"},
    )
    assert blocked.status_code == _HTTP_OK
    assert blocked_body == {
        "code": _PASSWORD_LOGIN_RATE_LIMITED_CODE,
        "message": "Too many failed password attempts. Try again later.",
    }

    correct_while_blocked, correct_while_blocked_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": phone, "password": password},
    )
    assert correct_while_blocked.status_code == _HTTP_OK
    assert correct_while_blocked_body["code"] == _PASSWORD_LOGIN_RATE_LIMITED_CODE

    counter_keys = [
        key
        for key in mock_redis_client.stored_keys()
        if "password_login_failure:" in key
    ]
    assert len(counter_keys) == _PASSWORD_COUNTER_KEY_COUNT
    assert all(phone not in key for key in counter_keys)
    assert all("127.0.0.1" not in key for key in counter_keys)
    assert all(mock_redis_client.ttl(key) > 0 for key in counter_keys)
    assert phone not in caplog.text
    assert "127.0.0.1" not in caplog.text


def test_password_login_throttles_one_ip_across_identifiers(
    test_client: FlaskClient,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Share an IP failure budget across distinct account identifiers."""
    monkeypatch.setitem(
        app.config,
        "PASSWORD_LOGIN_IDENTIFIER_FAILURE_LIMIT",
        _TEST_IP_FAILURE_LIMIT,
    )
    monkeypatch.setitem(
        app.config,
        "PASSWORD_LOGIN_IP_FAILURE_LIMIT",
        _TEST_IDENTIFIER_FAILURE_LIMIT,
    )
    monkeypatch.setitem(
        app.config,
        "PASSWORD_LOGIN_FAILURE_WINDOW_SECONDS",
        _TEST_FAILURE_WINDOW_SECONDS,
    )

    first_failure, first_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": "first@example.com", "password": "wrong-password"},
        headers={"X-Forwarded-For": "203.0.113.10, 198.51.100.8"},
        environ_overrides={"REMOTE_ADDR": "172.18.0.2"},
    )
    assert first_failure.status_code == _HTTP_OK
    assert first_body["code"] == _INVALID_CREDENTIALS_CODE

    blocked, blocked_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": "second@example.com", "password": "wrong-password"},
        headers={"X-Forwarded-For": "203.0.113.11, 198.51.100.8"},
        environ_overrides={"REMOTE_ADDR": "172.18.0.3"},
    )
    assert blocked.status_code == _HTTP_OK
    assert blocked_body["code"] == _PASSWORD_LOGIN_RATE_LIMITED_CODE

    still_blocked, still_blocked_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": "third@example.com", "password": "wrong-password"},
        headers={"X-Forwarded-For": "203.0.113.12, 198.51.100.8"},
        environ_overrides={"REMOTE_ADDR": "172.18.0.4"},
    )
    assert still_blocked.status_code == _HTTP_OK
    assert still_blocked_body["code"] == _PASSWORD_LOGIN_RATE_LIMITED_CODE


def test_password_login_blocks_when_failure_counter_lock_is_busy(
    test_client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
    mock_redis_client: FakeRedis,
) -> None:
    """Do not let concurrent counter updates bypass password throttling."""
    busy_lock = MagicMock()
    busy_lock.acquire.return_value = False
    lock_factory = MagicMock(return_value=busy_lock)
    monkeypatch.setattr(mock_redis_client, "lock", lock_factory)

    blocked, blocked_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": "locked@example.com", "password": "wrong-password"},
    )

    assert blocked.status_code == _HTTP_OK
    assert blocked_body["code"] == _PASSWORD_LOGIN_RATE_LIMITED_CODE
    lock_factory.assert_called_once()
    busy_lock.release.assert_not_called()


def test_password_login_blocks_when_failure_counter_lock_errors(
    test_client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
    mock_redis_client: FakeRedis,
) -> None:
    """Fail closed when Redis errors after returning a lock object."""
    failing_lock = MagicMock()
    failing_lock.acquire.side_effect = RedisError("redis unavailable")
    monkeypatch.setattr(mock_redis_client, "lock", MagicMock(return_value=failing_lock))

    blocked, blocked_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": "redis-error@example.com", "password": "wrong-password"},
    )

    assert blocked.status_code == _HTTP_OK
    assert blocked_body["code"] == _PASSWORD_LOGIN_RATE_LIMITED_CODE
    failing_lock.release.assert_not_called()


def test_password_login_blocks_without_a_shared_counter_backend(
    test_client: FlaskClient,
    mock_redis_client: FakeRedis,
) -> None:
    """Do not weaken throttling to process-local counters when Redis is absent."""
    from flaskr.dao import set_redis_client

    set_redis_client(None)
    try:
        blocked, blocked_body = _post_json(
            test_client,
            "/api/user/login_password",
            {"identifier": "no-redis@example.com", "password": "wrong-password"},
        )
    finally:
        set_redis_client(mock_redis_client)

    assert blocked.status_code == _HTTP_OK
    assert blocked_body["code"] == _PASSWORD_LOGIN_RATE_LIMITED_CODE


def test_password_login_waits_for_redis_before_clearing_failures(
    test_client: FlaskClient,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    mock_redis_client: FakeRedis,
) -> None:
    """Do not report login success until the shared failure count is cleared."""
    phone = "15500002224"
    password = "Abcd1234"
    with app.app_context():
        user_token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=phone, code="9999"
        )
    _post_json(
        test_client,
        "/api/user/set_password",
        {"identifier": phone, "code": "9999", "new_password": password},
        headers={"Token": user_token.token},
    )

    original_delete = mock_redis_client.delete
    monkeypatch.setattr(
        mock_redis_client,
        "delete",
        MagicMock(side_effect=RedisError("redis unavailable")),
    )
    _blocked, blocked_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": phone, "password": password},
    )
    assert blocked_body["code"] == _PASSWORD_LOGIN_RATE_LIMITED_CODE

    monkeypatch.setattr(mock_redis_client, "delete", original_delete)
    recovered, recovered_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": phone, "password": password},
    )
    assert recovered.status_code == _HTTP_OK
    assert recovered_body["code"] == 0


def test_password_reset_clears_identifier_failure_limit(
    test_client: FlaskClient,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restore password access immediately after verified credential recovery."""
    phone = "15500002225"
    old_password = "Abcd1234"
    new_password = "Efgh5678"
    monkeypatch.setitem(
        app.config,
        "PASSWORD_LOGIN_IDENTIFIER_FAILURE_LIMIT",
        _TEST_IDENTIFIER_FAILURE_LIMIT,
    )
    with app.app_context():
        user_token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=phone, code="9999"
        )
    _post_json(
        test_client,
        "/api/user/set_password",
        {"identifier": phone, "code": "9999", "new_password": old_password},
        headers={"Token": user_token.token},
    )
    for wrong_password in ("wrong-one", "wrong-two"):
        _post_json(
            test_client,
            "/api/user/login_password",
            {"identifier": phone, "password": wrong_password},
        )

    reset, reset_body = _post_json(
        test_client,
        "/api/user/reset_password",
        {"identifier": phone, "code": "9999", "new_password": new_password},
    )
    assert reset.status_code == _HTTP_OK
    assert reset_body["code"] == 0

    login, login_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": phone, "password": new_password},
    )
    assert login.status_code == _HTTP_OK
    assert login_body["code"] == 0


def test_first_password_clears_identifier_failure_limit(
    test_client: FlaskClient,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restore password access after verified first-time password setup."""
    phone = "15500002226"
    password = "Abcd1234"
    monkeypatch.setitem(
        app.config,
        "PASSWORD_LOGIN_IDENTIFIER_FAILURE_LIMIT",
        _TEST_IDENTIFIER_FAILURE_LIMIT,
    )
    monkeypatch.setitem(
        app.config,
        "PASSWORD_LOGIN_IP_FAILURE_LIMIT",
        _TEST_IP_FAILURE_LIMIT,
    )
    with app.app_context():
        user_token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=phone, code="9999"
        )

    for wrong_password in ("wrong-one", "wrong-two"):
        _post_json(
            test_client,
            "/api/user/login_password",
            {"identifier": phone, "password": wrong_password},
        )

    created, created_body = _post_json(
        test_client,
        "/api/user/set_password",
        {"identifier": phone, "code": "9999", "new_password": password},
        headers={"Token": user_token.token},
    )
    assert created.status_code == _HTTP_OK
    assert created_body["code"] == 0

    login, login_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": phone, "password": password},
    )
    assert login.status_code == _HTTP_OK
    assert login_body["code"] == 0


def test_password_login_merges_authenticated_guest_learner_profile(test_client, app):
    from flaskr.dao import db
    from flaskr.service.profile.learner_profile import (
        PROFILE_ONBOARDING_SCENE_KEY,
        PROFILE_ONBOARDING_VERSION,
        load_learner_profile_state,
    )
    from flaskr.service.user import phone_flow
    from flaskr.service.user.models import UserInfo, UserOnboardingState
    from flaskr.service.user.repository import create_user_entity
    from flaskr.service.user.utils import generate_token

    target_phone = "15500002332"
    password = "Abcd1234"
    guest_profile = "可以叫我小雨。password merge sentinel"
    profile_updated_at = datetime(2026, 8, 4, 5, 30, tzinfo=UTC)

    with app.app_context():
        guest = create_user_entity(
            user_bid="password-anonymous-guest",
            identify="password-anonymous-guest",
            nickname="小雨",
            learner_profile=guest_profile,
            learner_profile_updated_at=profile_updated_at,
        )
        guest_token = generate_token(app, guest.user_bid)
        target_token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=target_phone, code="9999"
        )
        guest_user_id = guest.user_bid
        target_user_id = target_token.userInfo.user_id
        db.session.add(
            UserOnboardingState(
                user_bid=guest_user_id,
                scene_key=PROFILE_ONBOARDING_SCENE_KEY,
                version=PROFILE_ONBOARDING_VERSION,
                status="completed",
                trigger_source="settings",
                completed_at=profile_updated_at,
            )
        )
        db.session.commit()

    _post_json(
        test_client,
        "/api/user/set_password",
        {"identifier": target_phone, "code": "9999", "new_password": password},
        headers={"Token": target_token.token},
    )

    failed_response, failed_body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": target_phone, "password": "wrong-password"},
        headers={"Token": guest_token},
    )
    assert failed_response.status_code == 200
    assert failed_body["code"] != 0
    with app.app_context():
        target_before_login = UserInfo.query.filter_by(user_bid=target_user_id).one()
        assert target_before_login.learner_profile == ""
        assert load_learner_profile_state(target_user_id) is None

    login_payload = {"identifier": target_phone, "password": password}
    response, body = _post_json(
        test_client,
        f"/api/user/login_password?token={guest_token}",
        login_payload,
    )
    assert response.status_code == 200
    assert body["code"] == 0

    response, body = _post_json(
        test_client,
        "/api/user/login_password",
        {**login_payload, "token": guest_token},
    )
    assert response.status_code == 200
    assert body["code"] == 0

    test_client.set_cookie("token", guest_token)
    response, body = _post_json(
        test_client,
        "/api/user/login_password",
        login_payload,
    )
    test_client.delete_cookie("token")
    assert response.status_code == 200
    assert body["code"] == 0

    with app.app_context():
        target_before_header_login = UserInfo.query.filter_by(
            user_bid=target_user_id
        ).one()
        assert target_before_header_login.learner_profile == ""
        assert target_before_header_login.nickname == ""
        assert load_learner_profile_state(target_user_id) is None

    response, body = _post_json(
        test_client,
        "/api/user/login_password",
        login_payload,
        headers={"Token": guest_token},
    )

    assert response.status_code == 200
    assert body["code"] == 0
    assert body["data"]["token"]
    assert body["data"]["userInfo"]["user_id"] == target_user_id
    assert body["data"]["userInfo"]["name"] == "小雨"
    with app.app_context():
        stored_target = UserInfo.query.filter_by(user_bid=target_user_id).one()
        stored_guest = UserInfo.query.filter_by(user_bid=guest_user_id).one()
        target_state = load_learner_profile_state(target_user_id)
        assert stored_target.learner_profile == guest_profile
        assert stored_target.nickname == "小雨"
        assert stored_target.learner_profile_updated_at is not None
        assert (
            stored_target.learner_profile_updated_at.replace(tzinfo=UTC)
            == profile_updated_at
        )
        assert stored_guest.learner_profile == guest_profile
        assert target_state is not None
        assert target_state.status == "completed"
        assert target_state.trigger_source == "settings"


def test_password_login_never_merges_from_a_registered_account(test_client, app):
    from flaskr.dao import db
    from flaskr.service.user import phone_flow
    from flaskr.service.user.models import UserInfo

    source_phone = "15500002334"
    target_phone = "15500002335"
    password = "Abcd1234"

    with app.app_context():
        source_token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=source_phone, code="9999"
        )
        target_token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=target_phone, code="9999"
        )
        source = UserInfo.query.filter_by(user_bid=source_token.userInfo.user_id).one()
        source.learner_profile = "registered profile must stay isolated"
        source.learner_profile_updated_at = datetime(2026, 8, 4, 5, 45, tzinfo=UTC)
        target_user_id = target_token.userInfo.user_id
        target = UserInfo.query.filter_by(user_bid=target_user_id).one()
        target.nickname = "Existing target"
        db.session.commit()

    _post_json(
        test_client,
        "/api/user/set_password",
        {"identifier": target_phone, "code": "9999", "new_password": password},
        headers={"Token": target_token.token},
    )
    response, body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": target_phone, "password": password},
        headers={"Token": source_token.token},
    )

    assert response.status_code == 200
    assert body["code"] == 0
    assert body["data"]["token"]
    assert body["data"]["userInfo"]["user_id"] == target_user_id
    assert body["data"]["userInfo"]["name"] == "Existing target"
    with app.app_context():
        stored_target = UserInfo.query.filter_by(user_bid=target_user_id).one()
        assert stored_target.learner_profile == ""
        assert stored_target.learner_profile_updated_at is None
        assert stored_target.nickname == "Existing target"


def test_password_login_ignores_invalid_and_expired_optional_tokens(test_client, app):
    from flaskr.dao import db
    from flaskr.service.user import phone_flow
    from flaskr.service.user.models import UserInfo
    from flaskr.service.user.repository import create_user_entity

    target_phone = "15500002333"
    password = "Abcd1234"

    with app.app_context():
        target_token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=target_phone, code="9999"
        )
        target_user_id = target_token.userInfo.user_id
        target = UserInfo.query.filter_by(user_bid=target_user_id).one()
        target.nickname = "Stable target"
        guest = create_user_entity(
            user_bid="password-expired-token-guest",
            identify="password-expired-token-guest",
            nickname="Guest",
            learner_profile="expired token profile",
            learner_profile_updated_at=datetime(2026, 8, 4, 6, 0, tzinfo=UTC),
        )
        db.session.commit()
        expired_token = jwt.encode(
            {
                "user_id": guest.user_bid,
                "exp": int(time.time()) - 60,
            },
            app.config["SECRET_KEY"],
            algorithm="HS256",
        )

    _post_json(
        test_client,
        "/api/user/set_password",
        {"identifier": target_phone, "code": "9999", "new_password": password},
        headers={"Token": target_token.token},
    )

    for stale_token in ("not-a-jwt", expired_token):
        response, body = _post_json(
            test_client,
            "/api/user/login_password",
            {"identifier": target_phone, "password": password},
            headers={"Token": stale_token},
        )
        assert response.status_code == 200
        assert body["code"] == 0
        assert body["data"]["token"]
        assert body["data"]["userInfo"]["user_id"] == target_user_id
        assert body["data"]["userInfo"]["name"] == "Stable target"

    with app.app_context():
        stored_target = UserInfo.query.filter_by(user_bid=target_user_id).one()
        assert stored_target.learner_profile == ""
        assert stored_target.learner_profile_updated_at is None
        assert stored_target.nickname == "Stable target"


def test_sms_login_route_logs_in_with_phone_code(test_client):
    phone = "15500003333"

    resp, body = _post_json(
        test_client,
        "/api/user/login_sms",
        {
            "mobile": phone,
            "sms_code": "9999",
            "language": "zh-CN",
            "login_context": "admin",
        },
    )

    assert resp.status_code == 200
    assert body["code"] == 0
    assert body["data"]["token"]
    assert body["data"]["userInfo"]["mobile"] == phone


def test_sms_login_route_does_not_rebind_authenticated_account_phone(test_client, app):
    from flaskr.service.user import phone_flow
    from flaskr.service.user.models import AuthCredential
    from flaskr.service.user.models import UserInfo as UserEntity

    original_phone = "15500005551"
    next_phone = "15500005552"

    with app.app_context():
        original_token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=original_phone, code="9999"
        )
        original_user_bid = original_token.userInfo.user_id

    resp, body = _post_json(
        test_client,
        "/api/user/login_sms",
        {
            "mobile": next_phone,
            "sms_code": "9999",
            "language": "zh-CN",
            "login_context": "admin",
        },
        headers={"Token": original_token.token},
    )

    assert resp.status_code == 200
    assert body["code"] == 0
    assert body["data"]["userInfo"]["mobile"] == next_phone
    assert body["data"]["userInfo"]["user_id"] != original_user_bid

    with app.app_context():
        original_entity = UserEntity.query.filter_by(user_bid=original_user_bid).first()
        assert original_entity is not None
        assert original_entity.user_identify == original_phone

        original_credentials = AuthCredential.query.filter_by(
            user_bid=original_user_bid,
            provider_name="phone",
            deleted=0,
        ).all()
        assert [credential.identifier for credential in original_credentials] == [
            original_phone
        ]


def test_sms_login_route_normalizes_cn_prefix(test_client, app):
    from flaskr.service.user.models import AuthCredential
    from flaskr.service.user.models import UserInfo as UserEntity

    phone = "15500004444"

    resp, body = _post_json(
        test_client,
        "/api/user/login_sms",
        {
            "mobile": f"+86{phone}",
            "sms_code": "9999",
            "language": "zh-CN",
            "login_context": "admin",
        },
    )

    assert resp.status_code == 200
    assert body["code"] == 0
    assert body["data"]["token"]
    assert body["data"]["userInfo"]["mobile"] == phone

    with app.app_context():
        entity = UserEntity.query.filter_by(user_identify=phone).first()
        assert entity is not None
        credential = AuthCredential.query.filter_by(
            provider_name="phone",
            identifier=phone,
            user_bid=entity.user_bid,
        ).first()
        assert credential is not None


def test_sms_login_referral_metadata_helper_hashes_client_context():
    from flaskr.service.referral.service import extract_referral_post_auth_fields

    fields = extract_referral_post_auth_fields(
        {
            "invite_code": "ABC12345",
            "referral_session_id": "session-from-frontend",
            "referral_entry_source": "manual",
        },
        client_ip="203.0.113.22",
        user_agent="Referral metadata test",
    )

    assert fields["invite_code"] == "ABC12345"
    assert fields["referral_session_id"] == "session-from-frontend"
    assert fields["referral_entry_source"] == "manual"
    assert fields["client_ip_hash"]
    assert fields["client_ip_hash"] != "203.0.113.22"
    assert fields["user_agent_hash"]
    assert fields["user_agent_hash"] != "Referral metadata test"
