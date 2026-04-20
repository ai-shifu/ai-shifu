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
