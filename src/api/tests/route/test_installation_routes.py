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


@pytest.fixture
def password_http_app(
    installation_http_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> Flask:
    from flaskr.route import user as user_routes
    from flaskr.service.user import email_flow

    app = installation_http_app
    user_routes.register_user_handler(app, "/api/user")
    monkeypatch.setattr(user_routes, "run_post_auth_extensions", Mock())
    monkeypatch.setattr(email_flow, "consume_verification_code", Mock())
    monkeypatch.setattr(email_flow, "ensure_admin_creator_and_demo_permissions", Mock())
    return app


def _password_login(app: Flask, path: str, identifier: str, password: str) -> dict:
    return (
        app.test_client()
        .post(
            path,
            json={"identifier": identifier, "password": password},
            headers={"Origin": "http://localhost:8080"},
        )
        .get_json(force=True)
    )


def _post(app: Flask, path: str, payload: object, **kwargs: object) -> object:
    kwargs.setdefault("headers", {"Origin": "http://localhost:8080"})
    return app.test_client().post("/api/installation/" + path, json=payload, **kwargs)


def _setup_payload(app: Flask) -> dict[str, str]:
    return {
        "setup_token": installation.issue_setup_token(app),
        "identifier": "owner@example.com",
        "password": "OwnerPassword123",
    }


def _create_password_user(
    app: Flask, *, user_bid: str, identifier: str, operator: bool = False
) -> str:
    from flaskr.service.user.consts import USER_STATE_REGISTERED
    from flaskr.service.user.password_flow import write_password_credential
    from flaskr.service.user.repository import create_user_entity

    with app.app_context(), unit_of_work():
        user = create_user_entity(
            user_bid=user_bid, identify=identifier, state=USER_STATE_REGISTERED
        )
        user.is_operator = int(operator)
        write_password_credential(
            app, user_bid=user_bid, identifier=identifier, new_password="Attacker123"
        )
    return user_bid


def _unverified_contact_payload(identifier: str) -> dict[str, str]:
    return (
        {"email": identifier.upper()}
        if "@" in identifier
        else {"mobile": f"+86 {identifier}"}
    )


def _assert_unverified_contact_claim(user_bid: str, identifier: str) -> None:
    from flaskr.service.user.consts import CREDENTIAL_STATE_UNVERIFIED

    credential = AuthCredential.query.filter_by(
        user_bid=user_bid,
        provider_name="email" if "@" in identifier else "phone",
        identifier=identifier,
        deleted=0,
    ).one()
    assert credential.state == CREDENTIAL_STATE_UNVERIFIED


@pytest.mark.parametrize("identifier", ["owner@example.com", "13800138000"])
@pytest.mark.parametrize(
    ("owner_kind", "path"),
    [
        ("ordinary", "/api/user/login_password"),
        ("setup", "/api/user/login_password"),
        ("setup", "/api/installation/login"),
    ],
)
def test_unverified_profile_claim_cannot_block_the_password_owner(
    password_http_app: Flask, identifier: str, owner_kind: str, path: str
) -> None:
    from flaskr.service.user.password_flow import write_password_credential
    from flaskr.service.user.repository import find_password_identity_user_bids

    app = password_http_app
    payload = {**_setup_payload(app), "identifier": identifier}
    if owner_kind == "ordinary":
        payload["identifier"] = "bootstrap@example.com"
    setup = _post(app, "initialize", payload).get_json()
    assert setup["code"] == 0
    owner_bid = setup["data"]["userInfo"]["user_id"]
    if owner_kind == "ordinary":
        owner_bid = _create_password_user(
            app, user_bid="ordinary-owner", identifier=identifier
        )
        with app.app_context(), unit_of_work():
            write_password_credential(
                app,
                user_bid=owner_bid,
                identifier=identifier,
                new_password=payload["password"],
            )
    initial_login = _password_login(app, path, identifier, payload["password"])
    assert initial_login["code"] == 0
    assert initial_login["data"]["userInfo"]["user_id"] == owner_bid

    attacker_bid = _create_password_user(
        app, user_bid="attacker", identifier="attacker@example.net"
    )
    attacker_login = _password_login(
        app, "/api/user/login_password", "attacker@example.net", "Attacker123"
    )
    assert attacker_login["code"] == 0
    assert attacker_login["data"]["userInfo"]["user_id"] == attacker_bid
    claim = (
        app.test_client()
        .post(
            "/api/user/update_info",
            json=_unverified_contact_payload(identifier),
            headers={"Token": attacker_login["data"]["token"]},
        )
        .get_json(force=True)
    )
    assert claim["code"] == 0
    with app.app_context():
        _assert_unverified_contact_claim(attacker_bid, identifier)

    owner_login = _password_login(app, path, identifier, payload["password"])
    assert owner_login["code"] == 0
    assert owner_login["data"]["userInfo"]["user_id"] == owner_bid
    assert _password_login(app, path, identifier, "Attacker123")["code"] != 0
    own_login = _password_login(
        app, "/api/user/login_password", "attacker@example.net", "Attacker123"
    )
    assert own_login["code"] == 0
    assert own_login["data"]["userInfo"]["user_id"] == attacker_bid
    with app.app_context(), unit_of_work():
        assert find_password_identity_user_bids(identifier) == {owner_bid}
        assert find_password_identity_user_bids(identifier, for_update=True) == {
            owner_bid
        }


@pytest.mark.parametrize("identifier", ["owner@example.com", "13800138000"])
@pytest.mark.parametrize(
    "path", ["/api/user/login_password", "/api/installation/login"]
)
def test_locked_password_confirmation_ignores_a_new_unverified_profile_claim(
    password_http_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    identifier: str,
    path: str,
) -> None:
    from flaskr.dao.uow import in_unit_of_work
    from flaskr.route import user as user_routes
    from flaskr.service.user.common import update_user_info
    from flaskr.service.user.repository import (
        build_user_info_from_aggregate,
        load_user_aggregate,
    )

    app = password_http_app
    payload = {**_setup_payload(app), "identifier": identifier}
    setup = _post(app, "initialize", payload).get_json()
    assert setup["code"] == 0
    owner_bid = setup["data"]["userInfo"]["user_id"]
    attacker_bid = _create_password_user(
        app, user_bid="attacker", identifier="attacker@example.net"
    )
    with app.app_context(), unit_of_work():
        UserToken.query.filter_by(user_id=owner_bid).delete()
    route_module = user_routes if path.startswith("/api/user/") else routes
    original_confirm = route_module.confirm_password_login_for_token_issue
    injected: list[bool] = []

    def claim_before_confirmation(**kwargs: object) -> None:
        assert in_unit_of_work()
        attacker = build_user_info_from_aggregate(load_user_aggregate(attacker_bid))
        update_user_info(
            app, attacker, name=None, **_unverified_contact_payload(identifier)
        )
        _assert_unverified_contact_claim(attacker_bid, identifier)
        injected.append(True)
        original_confirm(**kwargs)

    monkeypatch.setattr(
        route_module,
        "confirm_password_login_for_token_issue",
        claim_before_confirmation,
    )
    owner_login = _password_login(app, path, identifier, payload["password"])
    assert injected == [True]
    assert owner_login["code"] == 0
    assert owner_login["data"]["userInfo"]["user_id"] == owner_bid
    with app.app_context():
        _assert_unverified_contact_claim(attacker_bid, identifier)
        assert UserToken.query.filter_by(user_id=owner_bid).count() == 1


@pytest.mark.parametrize(
    "path", ["/api/user/login_password", "/api/installation/login"]
)
def test_locked_password_confirmation_ignores_an_unverified_google_canonical_copy(
    password_http_app: Flask, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    from flaskr.route import user as user_routes
    from flaskr.service.user.consts import (
        CREDENTIAL_STATE_UNVERIFIED,
        USER_STATE_UNREGISTERED,
    )
    from flaskr.service.user.models import UserInfo
    from flaskr.service.user.repository import create_user_entity, upsert_credential

    app = password_http_app
    payload = _setup_payload(app)
    setup = _post(app, "initialize", payload).get_json()
    assert setup["code"] == 0
    owner_bid = setup["data"]["userInfo"]["user_id"]
    with app.app_context(), unit_of_work():
        UserInfo.query.filter_by(
            user_bid=owner_bid
        ).one().user_identify = "current@example.com"
        UserToken.query.delete()
    route_module = user_routes if path.startswith("/api/user/") else routes
    original_confirm = route_module.confirm_password_login_for_token_issue

    def create_unverified_copy(**kwargs: object) -> None:
        # Model the persisted new-account shape of an unverified Google
        # callback completed after password verification, before token issue.
        claimant = create_user_entity(
            user_bid="unverified-google-claimant",
            identify=payload["identifier"],
            state=USER_STATE_UNREGISTERED,
        )
        upsert_credential(
            app,
            user_bid=claimant.user_bid,
            provider_name="google",
            subject_id="unverified-google-subject",
            subject_format="google",
            identifier=payload["identifier"],
            metadata={"email_verified": False},
            verified=False,
        )
        original_confirm(**kwargs)

    monkeypatch.setattr(
        route_module, "confirm_password_login_for_token_issue", create_unverified_copy
    )
    result = _password_login(app, path, payload["identifier"], payload["password"])
    assert result["code"] == 0
    assert result["data"]["userInfo"]["user_id"] == owner_bid
    with app.app_context():
        assert UserInfo.query.filter_by(user_bid="unverified-google-claimant").one()
        assert AuthCredential.query.filter_by(provider_name="google").one().state == (
            CREDENTIAL_STATE_UNVERIFIED
        )
        assert UserToken.query.filter_by(user_id=owner_bid).count() == 1


@pytest.mark.parametrize("identifier", ["unowned@example.com", "13800138000"])
def test_an_unverified_profile_contact_is_not_a_password_login_alias(
    password_http_app: Flask, identifier: str
) -> None:
    from flaskr.service.user.repository import find_password_identity_user_bids

    app = password_http_app
    assert _post(app, "initialize", _setup_payload(app)).get_json()["code"] == 0
    attacker_bid = _create_password_user(
        app, user_bid="attacker", identifier="attacker@example.net", operator=True
    )
    login = _password_login(
        app, "/api/user/login_password", "attacker@example.net", "Attacker123"
    )
    assert login["code"] == 0
    assert login["data"]["userInfo"]["user_id"] == attacker_bid
    response = app.test_client().post(
        "/api/user/update_info",
        json=_unverified_contact_payload(identifier),
        headers={"Token": login["data"]["token"]},
    )
    assert response.get_json(force=True)["code"] == 0
    with app.app_context(), unit_of_work():
        _assert_unverified_contact_claim(attacker_bid, identifier)
        assert find_password_identity_user_bids(identifier) == set()
        assert find_password_identity_user_bids(identifier, for_update=True) == set()
    for path in ("/api/user/login_password", "/api/installation/login"):
        assert _password_login(app, path, identifier, "Attacker123")["code"] != 0
        own_login = _password_login(app, path, "attacker@example.net", "Attacker123")
        assert own_login["code"] == 0
        assert own_login["data"]["userInfo"]["user_id"] == attacker_bid


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


@pytest.mark.parametrize("identifier", ["owner@example.com", "13800138000"])
def test_setup_password_identifier_survives_binding_a_second_contact_and_recovery(
    password_http_app: Flask,
    identifier: str,
) -> None:
    from flaskr.service.user import email_flow
    from flaskr.service.user.local_accounts import reset_local_admin_password
    from flaskr.service.user.models import UserInfo

    app = password_http_app
    payload = {**_setup_payload(app), "identifier": identifier}
    setup = _post(app, "initialize", payload).get_json()
    assert setup["code"] == 0
    user_bid = setup["data"]["userInfo"]["user_id"]
    with app.app_context():
        token, _created, _context = email_flow.verify_email_code(
            app,
            user_id=user_bid,
            email="second@example.com",
            code="delivered-test-code",
        )
        assert token.userInfo.user_id == user_bid
        assert UserInfo.query.one().user_identify == "second@example.com"
        assert [
            credential.identifier
            for credential in AuthCredential.query.filter(
                AuthCredential.provider_name.in_(["phone", "email"])
            ).all()
        ] == ["second@example.com"]

    paths = ("/api/user/login_password", "/api/installation/login")
    for path in paths:
        result = _password_login(app, path, identifier, payload["password"])
        assert result["code"] == 0
        assert result["data"]["userInfo"]["user_id"] == user_bid
    reset_local_admin_password(app, identifier=identifier, new_password="Recovered123")
    for path in paths:
        assert _password_login(app, path, identifier, "Recovered123")["code"] == 0
        assert _password_login(app, path, identifier, payload["password"])["code"] != 0


def test_ordinary_password_labels_and_contact_aliases_share_the_existing_password(
    password_http_app: Flask,
) -> None:
    from flaskr.service.user.consts import USER_STATE_REGISTERED
    from flaskr.service.user.password_flow import write_password_credential
    from flaskr.service.user.repository import create_user_entity, upsert_credential

    app = password_http_app
    with app.app_context(), unit_of_work():
        user = create_user_entity(
            user_bid="ordinary-user",
            identify="current@example.com",
            state=USER_STATE_REGISTERED,
        )
        write_password_credential(
            app,
            user_bid=user.user_bid,
            identifier="original@example.com",
            new_password="Shared123",
        )
        upsert_credential(
            app,
            user_bid=user.user_bid,
            provider_name="phone",
            subject_id="13800138000",
            subject_format="phone",
            identifier="13800138000",
            metadata={},
            verified=True,
        )
    for identifier in ("original@example.com", "current@example.com", "13800138000"):
        result = _password_login(
            app, "/api/user/login_password", identifier, "Shared123"
        )
        assert result["code"] == 0
        assert result["data"]["userInfo"]["user_id"] == "ordinary-user"
    assert (
        _password_login(
            app, "/api/installation/login", "original@example.com", "Shared123"
        )["code"]
        != 0
    )
    with app.app_context():
        assert LocalAdminAccount.query.count() == 0


@pytest.mark.parametrize(
    "invalid",
    [
        "deleted_user",
        "deleted_credential",
        "unverified",
        "empty_hash",
        "unknown",
        "internal",
        "username",
    ],
)
def test_persisted_password_identifiers_require_a_usable_ordinary_credential(
    password_http_app: Flask, invalid: str
) -> None:
    from flaskr.service.user.consts import (
        CREDENTIAL_STATE_UNVERIFIED,
        USER_STATE_REGISTERED,
    )
    from flaskr.service.user.password_flow import write_password_credential
    from flaskr.service.user.repository import create_user_entity, set_password_hash

    app = password_http_app
    identifier = "original@example.com"
    with app.app_context(), unit_of_work():
        user = create_user_entity(
            user_bid="password-user",
            identify="current@example.com",
            state=USER_STATE_REGISTERED,
        )
        user.is_operator = 1
        credential = write_password_credential(
            app, user_bid=user.user_bid, identifier=identifier, new_password="Shared123"
        )
        if invalid == "deleted_user":
            user.deleted = 1
        elif invalid == "deleted_credential":
            credential.deleted = 1
        elif invalid == "unverified":
            credential.state = CREDENTIAL_STATE_UNVERIFIED
        elif invalid == "empty_hash":
            set_password_hash(credential, "")
        elif invalid == "unknown":
            identifier = "unknown@example.com"
        else:
            identifier = "local:password-user" if invalid == "internal" else "old_owner"
            credential.identifier = identifier
            if invalid == "internal":
                user.user_identify = identifier
    for path in ("/api/user/login_password", "/api/installation/login"):
        assert _password_login(app, path, identifier, "Shared123")["code"] != 0
    with app.app_context():
        assert UserToken.query.count() == 0


@pytest.mark.parametrize("collision", ["canonical", "email", "phone", "password"])
def test_password_identifiers_reject_conflicting_account_ownership(
    password_http_app: Flask, collision: str
) -> None:
    from flaskr.service.user.consts import USER_STATE_REGISTERED
    from flaskr.service.user.password_flow import write_password_credential
    from flaskr.service.user.repository import (
        create_user_entity,
        find_password_identity_user_bids,
        upsert_credential,
    )

    app = password_http_app
    identifier = "13800138000" if collision == "phone" else "original@example.com"
    with app.app_context(), unit_of_work():
        owner = create_user_entity(
            user_bid="password-owner",
            identify="current@example.com",
            state=USER_STATE_REGISTERED,
        )
        owner.is_operator = 1
        write_password_credential(
            app, user_bid=owner.user_bid, identifier=identifier, new_password="Owner123"
        )
        other = create_user_entity(
            user_bid="other-user",
            identify=identifier if collision == "canonical" else "other@example.com",
            state=USER_STATE_REGISTERED,
        )
        if collision == "password":
            write_password_credential(
                app,
                user_bid=other.user_bid,
                identifier=identifier,
                new_password="Other123",
            )
        elif collision in {"email", "phone"}:
            upsert_credential(
                app,
                user_bid=other.user_bid,
                provider_name=collision,
                subject_id=identifier,
                subject_format=collision,
                identifier=identifier,
                metadata={},
                verified=True,
            )
        assert find_password_identity_user_bids(identifier) == {
            owner.user_bid,
            other.user_bid,
        }
    for path in ("/api/user/login_password", "/api/installation/login"):
        for password in ("Owner123", "Other123"):
            assert _password_login(app, path, identifier, password)["code"] != 0
    with app.app_context():
        assert UserToken.query.count() == 0


@pytest.mark.parametrize(
    "path", ["/api/user/login_password", "/api/installation/login"]
)
@pytest.mark.parametrize(
    "mutation", ["conflict", "verified_contact", "delete_alias", "unverify_alias"]
)
def test_password_identity_is_resolved_again_before_token_persistence(
    password_http_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    mutation: str,
) -> None:
    from flaskr.route import user as user_routes
    from flaskr.service.user.consts import (
        CREDENTIAL_STATE_UNVERIFIED,
        USER_STATE_REGISTERED,
    )
    from flaskr.service.user.models import UserInfo
    from flaskr.service.user.password_flow import write_password_credential
    from flaskr.service.user.repository import create_user_entity, upsert_credential

    app = password_http_app
    payload = _setup_payload(app)
    assert _post(app, "initialize", payload).get_json()["code"] == 0
    with app.app_context(), unit_of_work():
        user = UserInfo.query.one()
        user.user_identify = "current@example.com"
        # The requested label may be backed by a different password row from
        # the oldest shared password that the provider actually verifies.
        AuthCredential.query.one().identifier = "shared-password@example.com"
        label_credential = write_password_credential(
            app,
            user_bid=user.user_bid,
            identifier=payload["identifier"],
            new_password=payload["password"],
        )
        label_credential_bid = label_credential.credential_bid
        UserToken.query.delete()
    route_module = user_routes if path.startswith("/api/user/") else routes
    original_confirm = route_module.confirm_password_login_for_token_issue

    def change_identity(**kwargs: object) -> None:
        if mutation in {"conflict", "verified_contact"}:
            create_user_entity(
                user_bid="new-conflicting-account",
                identify=(
                    payload["identifier"]
                    if mutation == "conflict"
                    else "other@example.com"
                ),
                state=USER_STATE_REGISTERED,
            )
            if mutation == "verified_contact":
                upsert_credential(
                    app,
                    user_bid="new-conflicting-account",
                    provider_name="email",
                    subject_id=payload["identifier"],
                    subject_format="email",
                    identifier=payload["identifier"],
                    metadata={},
                    verified=True,
                )
        else:
            credential = AuthCredential.query.filter_by(
                credential_bid=label_credential_bid
            ).one()
            if mutation == "delete_alias":
                credential.deleted = 1
            else:
                credential.state = CREDENTIAL_STATE_UNVERIFIED
            db.session.flush()
        original_confirm(**kwargs)

    monkeypatch.setattr(
        route_module, "confirm_password_login_for_token_issue", change_identity
    )
    assert (
        _password_login(app, path, payload["identifier"], payload["password"])["code"]
        != 0
    )
    with app.app_context():
        assert UserToken.query.count() == 0


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
