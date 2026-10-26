"""Exercise the first-run HTTP boundary with real local credentials and state."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.common.http import init_sensitive_body_policy
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.route import installation as routes
from flaskr.route.common import register_common_handler
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import installation, post_auth, utils
from flaskr.service.user.installation_models import InstallationState, LocalAdminAccount
from flaskr.service.user.models import AuthCredential, UserToken
from flaskr.service.user.verification_codes import consume_verification_code

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def installation_http_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Flask]:
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'http-installation.db'}",
        SECRET_KEY="installation-route-test-secret-with-enough-bytes",
        TOKEN_EXPIRE_TIME=3600,
        ENV="production",
        LOGIN_METHODS_ENABLED="phone",
    )
    db.init_app(app)
    init_sensitive_body_policy(app)
    register_common_handler(app)
    routes.register_installation_routes(app, "/api/installation")
    monkeypatch.setattr(utils, "ensure_demo_course_permissions", Mock())
    monkeypatch.setattr(post_auth, "run_post_auth_extensions", Mock())
    monkeypatch.setattr(routes, "run_post_auth_extensions", Mock())
    with app.app_context():
        db.create_all(bind_key=None)
        db.session.add(InstallationState(id=1, mode="managed"))
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all(bind_key=None)


def _post(app: Flask, path: str, payload: object, **kwargs: object) -> object:
    kwargs.setdefault("headers", {"Origin": "http://localhost:8080"})
    return app.test_client().post("/api/installation/" + path, json=payload, **kwargs)


def _setup_payload(app: Flask) -> dict[str, str]:
    return {
        "setup_token": installation.issue_setup_token(app),
        "identifier": "owner@example.com",
        "password": "OwnerPassword123",
    }


def test_status_is_minimal_and_not_cached(installation_http_app: Flask) -> None:
    response = installation_http_app.test_client().get("/api/installation/status")
    assert response.get_json() == {
        "code": 0,
        "message": "success",
        "data": {"setup_required": True, "local_admin_login_enabled": False},
    }
    assert response.headers["Cache-Control"] == "no-store"


def test_setup_returns_normal_session_and_local_login_ignores_learner_switches(
    installation_http_app: Flask,
) -> None:
    app = installation_http_app
    payload = _setup_payload(app)
    response = _post(app, "initialize", payload)
    body = response.get_json()
    assert body["code"] == 0
    assert body["data"]["token"]
    assert body["data"]["userInfo"]["username"] == "owner@example.com"
    assert body["data"]["userInfo"]["email"] == "owner@example.com"
    assert body["data"]["userInfo"]["has_password"] is True
    assert body["data"]["userInfo"]["mobile"] == ""
    assert response.headers["Cache-Control"] == "no-store"
    login = _post(
        app,
        "login",
        {"identifier": "OWNER@EXAMPLE.COM", "password": payload["password"]},
    )
    assert login.get_json()["code"] == 0
    assert (
        login.get_json()["data"]["userInfo"]["user_id"]
        == body["data"]["userInfo"]["user_id"]
    )
    assert installation.get_installation_status(app) == {
        "setup_required": False,
        "local_admin_login_enabled": True,
    }
    with app.app_context():
        assert LocalAdminAccount.query.count() == 1
        assert UserToken.query.count() == 2
        assert (
            AuthCredential.query.filter(
                AuthCredential.provider_name.in_(["phone", "email"])
            ).count()
            == 0
        )


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "null"},
        {"Origin": "http://public.example"},
        {"Origin": "http://localhost.evil.example"},
        {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "localhost:8080"},
    ],
)
def test_setup_requires_explicit_safe_browser_origin(
    installation_http_app: Flask, headers: dict[str, str]
) -> None:
    app = installation_http_app
    response = _post(app, "initialize", _setup_payload(app), headers=headers)
    assert (
        response.get_json()["code"]
        == ERROR_CODE["server.installation.invalidSetupOrigin"]
    )
    assert installation.get_installation_status(app)["setup_required"] is True


def test_valid_but_wrong_origin_cannot_spend_the_setup_code(
    installation_http_app: Flask,
) -> None:
    app = installation_http_app
    payload = _setup_payload(app)
    wrong = _post(
        app,
        "initialize",
        payload,
        headers={"Origin": "https://other.example"},
    )
    assert (
        wrong.get_json()["code"] == ERROR_CODE["server.installation.invalidSetupOrigin"]
    )
    assert _post(app, "initialize", payload).get_json()["code"] == 0


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("identifier", None),
        ("identifier", ["owner@example.com"]),
        ("identifier", "x" * 65),
        ("password", False),
        ("password", "Valid123" + "字" * 22),
        ("setup_token", {"token": "not-a-string"}),
        ("setup_token", "x" * 257),
        ("language", ["en-US"]),
    ],
)
def test_invalid_json_fields_cannot_initialize(
    installation_http_app: Flask, key: str, value: object
) -> None:
    app = installation_http_app
    payload = _setup_payload(app)
    payload[key] = value
    response = _post(app, "initialize", payload)
    assert response.get_json()["code"] != 0
    assert installation.get_installation_status(app)["setup_required"] is True
    with app.app_context():
        assert LocalAdminAccount.query.count() == 0


def test_sensitive_body_is_bounded_before_parsing(installation_http_app: Flask) -> None:
    response = installation_http_app.test_client().post(
        "/api/installation/initialize",
        data=b"x" * (32 * 1024 + 1),
        content_type="application/json",
        headers={"Origin": "http://localhost:8080"},
    )
    assert response.get_json()["code"] == 413
    assert response.headers["Cache-Control"] == "no-store"


def test_invalid_setup_attempts_are_limited_without_consuming_the_claim(
    installation_http_app: Flask,
) -> None:
    app = installation_http_app
    app.config["PASSWORD_LOGIN_MAX_FAILURES"] = 2
    payload = _setup_payload(app)
    wrong_payload = {**payload, "setup_token": "x" * 43}
    errors = [
        _post(app, "initialize", wrong_payload).get_json()["code"] for _ in range(3)
    ]
    assert errors == [
        ERROR_CODE["server.installation.invalidSetupToken"],
        ERROR_CODE["server.installation.invalidSetupToken"],
        ERROR_CODE["server.installation.setupRateLimited"],
    ]
    assert installation.get_installation_status(app)["setup_required"] is True
    response = _post(
        app, "initialize", payload, environ_overrides={"REMOTE_ADDR": "127.0.0.2"}
    )
    assert response.get_json()["code"] == 0


def test_invalid_unicode_password_is_rejected_before_bcrypt(
    installation_http_app: Flask,
) -> None:
    app = installation_http_app
    payload = _setup_payload(app)
    payload["password"] = "Valid123\ud800"
    response = _post(app, "initialize", payload)
    assert response.get_json()["code"] != 0
    assert installation.get_installation_status(app)["setup_required"] is True


def test_a_session_failure_leaves_setup_closed_and_password_login_available(
    installation_http_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = installation_http_app
    payload = _setup_payload(app)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            routes, "persist_token", Mock(side_effect=RuntimeError("offline"))
        )
        response = _post(app, "initialize", payload)
    assert response.get_json()["code"] != 0
    assert installation.get_installation_status(app) == {
        "setup_required": False,
        "local_admin_login_enabled": True,
    }
    with app.app_context():
        assert LocalAdminAccount.query.count() == 1
        assert UserToken.query.count() == 0
    assert (
        _post(
            app,
            "login",
            {"identifier": payload["identifier"], "password": payload["password"]},
        ).get_json()["code"]
        == 0
    )
    assert _post(app, "initialize", payload).get_json()["code"] != 0


def test_setup_secrets_are_not_accepted_as_regular_verification_codes(
    installation_http_app: Flask,
) -> None:
    app = installation_http_app
    setup_token = installation.issue_setup_token(app)
    with app.app_context(), pytest.raises(AppError):
        consume_verification_code(
            app, identifier="operator@example.com", code=setup_token
        )
    assert installation.get_installation_status(app)["setup_required"] is True


def test_missing_installation_state_never_opens_setup(
    installation_http_app: Flask,
) -> None:
    app = installation_http_app
    with app.app_context(), unit_of_work():
        InstallationState.query.delete()
    assert installation.get_installation_status(app) == {
        "setup_required": False,
        "local_admin_login_enabled": False,
    }


@pytest.mark.parametrize(
    "identifier",
    [
        "13800138000",
        "+86 13800138000",
        "OWNER+tag@EXAMPLE.COM",
        "a" * 64 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * 61,
    ],
)
def test_contact_setup_login_and_recovery_accepts_normalized_long_identifiers(
    installation_http_app: Flask, identifier: str
) -> None:
    from flaskr.service.user.local_accounts import reset_local_admin_password

    app = installation_http_app
    payload = _setup_payload(app)
    payload["identifier"] = identifier
    response = _post(app, "initialize", payload).get_json()
    assert response["code"] == 0
    assert response["data"]["userInfo"]["has_password"] is True
    assert (
        _post(
            app, "login", {"identifier": identifier, "password": payload["password"]}
        ).get_json()["code"]
        == 0
    )
    reset_local_admin_password(app, identifier=identifier, new_password="Recovered123")
    assert (
        _post(
            app, "login", {"identifier": identifier, "password": "Recovered123"}
        ).get_json()["code"]
        == 0
    )
    assert (
        _post(
            app, "login", {"identifier": identifier, "password": payload["password"]}
        ).get_json()["code"]
        != 0
    )


def test_old_username_payload_only_signs_in_existing_legacy_mapping(
    installation_http_app: Flask,
) -> None:
    app = installation_http_app
    payload = _setup_payload(app)
    old_setup = dict(payload)
    old_setup["username"] = old_setup.pop("identifier")
    assert _post(app, "initialize", old_setup).get_json()["code"] != 0
    assert _post(app, "initialize", payload).get_json()["code"] == 0
    with app.app_context(), unit_of_work():
        binding = LocalAdminAccount.query.one()
        binding.identifier = "old_owner"
        binding.identifier_kind = "legacy_username"
        credential = AuthCredential.query.filter_by(
            credential_bid=binding.credential_bid
        ).one()
        credential.identifier = credential.subject_id = "old_owner"
        credential.subject_format = "local_username"
        from flaskr.service.user.models import UserInfo

        UserInfo.query.filter_by(
            user_bid=binding.user_bid
        ).one().user_identify = f"local:{binding.user_bid}"
    assert (
        _post(
            app, "login", {"username": "OLD_OWNER", "password": payload["password"]}
        ).get_json()["code"]
        == 0
    )
    assert (
        _post(
            app, "login", {"identifier": "old_owner", "password": payload["password"]}
        ).get_json()["code"]
        == 0
    )


@pytest.mark.parametrize("operator", [False, True])
def test_existing_standard_password_accounts_use_admin_login_only_with_operator_role(
    installation_http_app: Flask, operator: bool
) -> None:
    from flaskr.service.user.consts import USER_STATE_REGISTERED
    from flaskr.service.user.password_flow import write_password_credential
    from flaskr.service.user.repository import create_user_entity

    app = installation_http_app
    with app.app_context(), unit_of_work():
        user = create_user_entity(
            user_bid="ordinary-password-user",
            identify="existing@example.com",
            state=USER_STATE_REGISTERED,
        )
        user.is_operator = int(operator)
        write_password_credential(
            app,
            user_bid=user.user_bid,
            identifier="existing@example.com",
            new_password="Existing123",
        )
    assert (
        installation.get_installation_status(app)["local_admin_login_enabled"]
        is operator
    )
    result = _post(
        app, "login", {"identifier": "existing@example.com", "password": "Existing123"}
    ).get_json()
    assert (result["code"] == 0) is operator
    with app.app_context():
        assert LocalAdminAccount.query.count() == 0
        assert UserToken.query.count() == int(operator)
        assert AuthCredential.query.one().provider_name == "password"


def test_inactive_operator_cannot_use_password_admin_login(
    installation_http_app: Flask,
) -> None:
    from flaskr.service.user.consts import USER_STATE_UNREGISTERED
    from flaskr.service.user.models import UserInfo

    app = installation_http_app
    payload = _setup_payload(app)
    assert _post(app, "initialize", payload).get_json()["code"] == 0
    with app.app_context(), unit_of_work():
        UserInfo.query.one().state = USER_STATE_UNREGISTERED
        UserToken.query.delete()
    assert (
        installation.get_installation_status(app)["local_admin_login_enabled"] is False
    )
    assert (
        _post(
            app,
            "login",
            {"identifier": payload["identifier"], "password": payload["password"]},
        ).get_json()["code"]
        != 0
    )
    with app.app_context():
        assert UserToken.query.count() == 0
