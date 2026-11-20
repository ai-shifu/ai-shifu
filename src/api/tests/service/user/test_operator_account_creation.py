"""Verify operator-created username + password accounts."""

from __future__ import annotations

import json
import secrets

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.user.consts import CREDENTIAL_STATE_VERIFIED, USER_STATE_REGISTERED
from flaskr.service.user.models import AuthCredential, UserInfo, UserToken
from flaskr.service.user.operator_account_creation import (
    create_operator_password_account,
)
from flaskr.service.user.repository import get_password_hash
from flaskr.service.user.usernames import (
    is_username,
    normalize_login_identifier,
    validate_username,
)

# Generated per run so disposable fixtures are never mistaken for credentials.
PASSWORD = f"Pw{secrets.token_hex(8)}1"
WRONG_PASSWORD = f"Wrong{secrets.token_hex(8)}1"


@pytest.fixture(autouse=True)
def _isolate_user_tables(app: object) -> object:
    def _clear() -> None:
        with app.app_context():
            db.session.query(UserToken).delete()
            db.session.query(AuthCredential).delete()
            db.session.query(UserInfo).delete()
            db.session.commit()

    _clear()
    yield
    _clear()


def _login(client: object, identifier: str, password: str = PASSWORD) -> dict:
    response = client.post(
        "/api/user/login_password",
        data=json.dumps({"identifier": identifier, "password": password}),
        content_type="application/json",
    )
    assert response.status_code == 200
    return json.loads(response.data)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Alice", "alice"),
        ("  bob.smith  ", "bob.smith"),
        ("Learner@Example.com", "learner@example.com"),
        ("13800138000", "13800138000"),
        ("+86 13800138000", "13800138000"),
    ],
)
def test_login_identifier_normalization_keeps_formats_disjoint(
    raw: str, expected: str
) -> None:
    assert normalize_login_identifier(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["ab", "1alice", "alice@example", "al ice", "a" * 33, "_alice", "alice!"],
)
def test_malformed_usernames_are_rejected(raw: str) -> None:
    assert not is_username(raw)
    with pytest.raises(AppError):
        validate_username(raw)


def test_operator_creates_account_that_signs_in_with_username(
    app: object, test_client: object
) -> None:
    with app.app_context():
        result = create_operator_password_account(
            app,
            operator_user_bid="operator-1",
            username="  Alice.Chen ",
            password=PASSWORD,
            nickname="Alice",
        )

        assert result["username"] == "alice.chen"
        user = UserInfo.query.filter_by(user_bid=result["user_bid"]).one()
        assert user.user_identify == "alice.chen"
        assert user.nickname == "Alice"
        assert user.state == USER_STATE_REGISTERED
        credentials = {
            row.provider_name: row
            for row in AuthCredential.query.filter_by(user_bid=result["user_bid"])
        }
        assert set(credentials) == {"username", "password"}
        assert credentials["username"].identifier == "alice.chen"
        assert credentials["username"].state == CREDENTIAL_STATE_VERIFIED
        assert credentials["password"].subject_format == "username"
        stored_hash = get_password_hash(credentials["password"])
        assert stored_hash
        assert PASSWORD not in stored_hash

    body = _login(test_client, "ALICE.CHEN")
    assert body["code"] == 0
    assert body["data"]["token"]
    assert body["data"]["userInfo"]["user_id"] == result["user_bid"]
    assert body["data"]["userInfo"]["username"] == "alice.chen"
    assert body["data"]["userInfo"]["mobile"] == ""
    assert body["data"]["userInfo"]["email"] == ""
    assert body["data"]["userInfo"]["has_password"] is True

    assert _login(test_client, "alice.chen", WRONG_PASSWORD)["code"] != 0


def test_nickname_defaults_to_username(app: object) -> None:
    with app.app_context():
        result = create_operator_password_account(
            app, operator_user_bid="operator-1", username="bob", password=PASSWORD
        )
        user = UserInfo.query.filter_by(user_bid=result["user_bid"]).one()
        assert user.nickname == "bob"


def test_duplicate_username_is_rejected_without_writes(app: object) -> None:
    with app.app_context():
        create_operator_password_account(
            app, operator_user_bid="operator-1", username="carol", password=PASSWORD
        )
        with pytest.raises(AppError) as exc_info:
            create_operator_password_account(
                app,
                operator_user_bid="operator-1",
                username="CAROL",
                password=PASSWORD,
            )
        assert exc_info.value.code == 1047
        assert UserInfo.query.count() == 1
        assert AuthCredential.query.count() == 2


def test_username_matching_an_existing_identity_is_rejected(app: object) -> None:
    with app.app_context():
        db.session.add(
            UserInfo(
                user_bid="legacy-user",
                user_identify="dave",
                nickname="Legacy",
                state=USER_STATE_REGISTERED,
                deleted=0,
            )
        )
        db.session.commit()

        with pytest.raises(AppError):
            create_operator_password_account(
                app, operator_user_bid="operator-1", username="dave", password=PASSWORD
            )
        assert UserInfo.query.count() == 1
        assert AuthCredential.query.count() == 0


@pytest.mark.parametrize(
    ("username", "password", "nickname"),
    [
        ("9lives", PASSWORD, ""),
        ("erin", "short1", ""),
        ("erin", "lettersonly", ""),
        ("erin", PASSWORD, "n" * 51),
    ],
    # Explicit IDs keep collection identical across xdist workers, because the
    # password fixture value is generated per process.
    ids=[
        "username-starts-with-digit",
        "password-too-short",
        "password-no-digit",
        "nickname-too-long",
    ],
)
def test_invalid_input_is_rejected_without_writes(
    app: object, username: str, password: str, nickname: str
) -> None:
    with app.app_context():
        with pytest.raises(AppError):
            create_operator_password_account(
                app,
                operator_user_bid="operator-1",
                username=username,
                password=password,
                nickname=nickname,
            )
        assert UserInfo.query.count() == 0
        assert AuthCredential.query.count() == 0


def test_phone_and_email_password_login_still_resolve(
    app: object, test_client: object
) -> None:
    from flaskr.service.user.password_utils import hash_password

    with app.app_context():
        for user_bid, provider, identifier in (
            ("phone-user", "phone", "13800138000"),
            ("email-user", "email", "learner@example.com"),
        ):
            db.session.add(
                UserInfo(
                    user_bid=user_bid,
                    user_identify=identifier,
                    nickname="Learner",
                    state=USER_STATE_REGISTERED,
                    deleted=0,
                )
            )
            for provider_name in (provider, "password"):
                db.session.add(
                    AuthCredential(
                        credential_bid=f"{provider_name}-{user_bid}",
                        user_bid=user_bid,
                        provider_name=provider_name,
                        subject_id=identifier,
                        subject_format=provider,
                        identifier=identifier,
                        raw_profile=(
                            json.dumps({"password_hash": hash_password(PASSWORD)})
                            if provider_name == "password"
                            else "{}"
                        ),
                        state=CREDENTIAL_STATE_VERIFIED,
                        deleted=0,
                    )
                )
        db.session.commit()

    phone_body = _login(test_client, "+8613800138000")
    assert phone_body["code"] == 0
    assert phone_body["data"]["userInfo"]["user_id"] == "phone-user"
    email_body = _login(test_client, "Learner@Example.com")
    assert email_body["code"] == 0
    assert email_body["data"]["userInfo"]["user_id"] == "email-user"


def test_username_account_can_change_its_initial_password(
    app: object, test_client: object
) -> None:
    with app.app_context():
        create_operator_password_account(
            app, operator_user_bid="operator-1", username="frank", password=PASSWORD
        )
    token = _login(test_client, "frank")["data"]["token"]
    new_value = f"Next{secrets.token_hex(8)}2"

    response = test_client.post(
        "/api/user/change_password",
        data=json.dumps({"old_password": PASSWORD, "new_password": new_value}),
        content_type="application/json",
        headers={"Token": token},
    )

    assert json.loads(response.data)["code"] == 0
    assert _login(test_client, "frank")["code"] != 0
    assert _login(test_client, "frank", new_value)["code"] == 0
