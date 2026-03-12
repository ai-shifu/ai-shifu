import json


def _post_json(client, path: str, payload: dict, headers: dict | None = None):
    resp = client.post(
        path,
        data=json.dumps(payload),
        content_type="application/json",
        headers=headers or {},
    )
    return resp, json.loads(resp.data)


def _insert_phone_verify_code(app, *, phone: str, code: str) -> None:
    from flaskr.dao import db
    from flaskr.service.user.models import UserVerifyCode

    record = UserVerifyCode(
        phone=phone,
        mail="",
        verify_code=code,
        verify_code_type=1,
        verify_code_send=1,
        verify_code_used=0,
        user_ip="",
    )
    db.session.add(record)
    db.session.commit()


def _reset_user_storage(app) -> None:
    from flaskr.dao import db
    from flaskr.service.user.models import (
        AuthCredential,
        UserInfo as UserEntity,
        UserToken,
        UserVerifyCode,
    )

    db.session.query(AuthCredential).delete()
    db.session.query(UserToken).delete()
    db.session.query(UserVerifyCode).delete()
    db.session.query(UserEntity).delete()
    db.session.commit()


def test_reset_password_does_not_create_new_user(test_client, app):
    from flaskr.service.user.models import UserInfo as UserEntity

    phone = "15500009999"

    # No user exists yet for this phone number.
    with app.app_context():
        _reset_user_storage(app)
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
    from flaskr.dao import db

    phone = "15500001111"

    with app.app_context():
        _reset_user_storage(app)
        _insert_phone_verify_code(app, phone=phone, code="9999")
        user_token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=phone, code="9999"
        )
        db.session.commit()

    token_value = user_token.token
    headers = {"Token": token_value}

    with app.app_context():
        _insert_phone_verify_code(app, phone=phone, code="9999")

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
    from flaskr.dao import db

    phone = "15500002222"
    password = "Abcd1234"

    with app.app_context():
        _reset_user_storage(app)
        _insert_phone_verify_code(app, phone=phone, code="9999")
        user_token, _created, _ctx = phone_flow.verify_phone_code(
            app, user_id=None, phone=phone, code="9999"
        )
        db.session.commit()

    # Set password (logged in)
    with app.app_context():
        _insert_phone_verify_code(app, phone=phone, code="9999")
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


def test_bootstrap_admin_login_creates_first_creator_user(test_client, app):
    from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity

    identifier = "admin@example.com"
    password = "BootstrapAbcd1234"

    with app.app_context():
        _reset_user_storage(app)
        app.config["BOOTSTRAP_ADMIN_PASSWORD"] = password
        app.config["BOOTSTRAP_ADMIN_IDENTIFIER"] = identifier
        assert (
            UserEntity.query.filter(
                UserEntity.deleted == 0, UserEntity.is_creator == 1
            ).count()
            == 0
        )

    resp, body = _post_json(
        test_client,
        "/api/user/login_password",
        {
            "identifier": identifier,
            "password": password,
            "login_context": "admin",
            "language": "en-US",
        },
    )

    assert resp.status_code == 200
    assert body["code"] == 0
    assert body["data"]["token"]

    with app.app_context():
        entity = UserEntity.query.filter_by(user_identify=identifier.lower()).first()
        assert entity is not None
        assert int(entity.is_creator or 0) == 1
        assert (
            AuthCredential.query.filter_by(
                user_bid=entity.user_bid, provider_name="password", deleted=0
            ).count()
            == 1
        )


def test_bootstrap_admin_login_requires_admin_context(test_client, app):
    from flaskr.service.user.models import UserInfo as UserEntity

    identifier = "admin2@example.com"
    password = "BootstrapAbcd1234"

    with app.app_context():
        _reset_user_storage(app)
        app.config["BOOTSTRAP_ADMIN_PASSWORD"] = password
        app.config["BOOTSTRAP_ADMIN_IDENTIFIER"] = identifier
        assert UserEntity.query.filter(UserEntity.deleted == 0).count() == 0

    resp, body = _post_json(
        test_client,
        "/api/user/login_password",
        {"identifier": identifier, "password": password},
    )

    assert resp.status_code == 200
    assert body["code"] != 0

    with app.app_context():
        assert UserEntity.query.filter(UserEntity.deleted == 0).count() == 0


def test_bootstrap_admin_login_only_works_once(test_client, app):
    from flaskr.service.user.models import UserInfo as UserEntity

    password = "BootstrapAbcd1234"

    with app.app_context():
        _reset_user_storage(app)
        app.config["BOOTSTRAP_ADMIN_PASSWORD"] = password
        app.config["BOOTSTRAP_ADMIN_IDENTIFIER"] = ""
        assert (
            UserEntity.query.filter(
                UserEntity.deleted == 0, UserEntity.is_creator == 1
            ).count()
            == 0
        )

    # First bootstrap succeeds
    resp1, body1 = _post_json(
        test_client,
        "/api/user/login_password",
        {
            "identifier": "first-admin@example.com",
            "password": password,
            "login_context": "admin",
        },
    )
    assert resp1.status_code == 200
    assert body1["code"] == 0

    # Second bootstrap should fail because a creator user exists now
    resp2, body2 = _post_json(
        test_client,
        "/api/user/login_password",
        {
            "identifier": "second-admin@example.com",
            "password": password,
            "login_context": "admin",
        },
    )
    assert resp2.status_code == 200
    assert body2["code"] != 0

    with app.app_context():
        assert (
            UserEntity.query.filter(
                UserEntity.deleted == 0, UserEntity.is_creator == 1
            ).count()
            == 1
        )
