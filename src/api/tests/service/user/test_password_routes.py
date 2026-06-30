import json


def _post_json(client, path: str, payload: dict, headers: dict | None = None):
    resp = client.post(
        path,
        data=json.dumps(payload),
        content_type="application/json",
        headers=headers or {},
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
    import flaskr.service.user.phone_flow as phone_flow

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
    import flaskr.service.user.phone_flow as phone_flow

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
    import flaskr.service.user.phone_flow as phone_flow
    from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity

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
    from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity

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
