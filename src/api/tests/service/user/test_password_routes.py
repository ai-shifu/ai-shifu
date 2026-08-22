"""Verify password HTTP route behavior."""

import json
import time
from datetime import UTC, datetime

import jwt


def _post_json(client: object, path: str, payload: dict, headers: dict | None = None):
    resp = client.post(
        path,
        data=json.dumps(payload),
        content_type="application/json",
        headers=headers or {},
    )
    return resp, json.loads(resp.data)


def test_reset_password_does_not_create_new_user(
    test_client: object, app: object
) -> None:
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


def test_set_password_requires_login_and_verification_code(
    test_client: object, app: object
) -> None:
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


def test_password_login_after_setting_password(
    test_client: object, app: object
) -> None:
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


def test_password_login_merges_authenticated_guest_learner_profile(
    test_client: object, app: object
) -> None:
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


def test_password_login_never_merges_from_a_registered_account(
    test_client: object, app: object
) -> None:
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


def test_password_login_ignores_invalid_and_expired_optional_tokens(
    test_client: object, app: object
) -> None:
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


def test_sms_login_route_logs_in_with_phone_code(test_client: object) -> None:
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


def test_sms_login_route_does_not_rebind_authenticated_account_phone(
    test_client: object, app: object
) -> None:
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


def test_sms_login_route_normalizes_cn_prefix(test_client: object, app: object) -> None:
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


def test_sms_login_referral_metadata_helper_hashes_client_context() -> None:
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
