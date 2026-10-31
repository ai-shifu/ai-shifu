"""Keep ordinary password validation, writes, and sessions consistent."""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from flask import current_app
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import password_flow
from flaskr.service.user import utils as user_utils
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.models import AuthCredential, UserToken, UserVerifyCode
from flaskr.service.user.password_utils import verify_password
from flaskr.service.user.repository import (
    create_user_entity,
    get_password_hash,
    upsert_credential,
)
from flaskr.service.user.token_store import token_store
from flaskr.service.user.verification_codes import clear_verification_attempts
from flaskr.util.datetime import now_utc

from tests.common.fixtures.fake_redis import FakeRedis

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask

_OLD_PASSWORD = "Initial12345"
_NEW_PASSWORD = "Changed12345"
_WINNER_PASSWORD = "Winner12345"
_CODE = "623751"


def _issue_code(identifier: str, *, expired: bool = False) -> None:
    """Commit a real verification challenge without external delivery."""
    is_email = "@" in identifier
    db.session.add(
        UserVerifyCode(
            phone="" if is_email else identifier,
            mail=identifier if is_email else "",
            verify_code=_CODE,
            verify_code_type=2 if is_email else 1,
            verify_code_send=1,
            verify_code_used=0,
            created=now_utc() - timedelta(days=1) if expired else now_utc(),
        )
    )
    db.session.commit()
    clear_verification_attempts(
        current_app, kind="email" if is_email else "sms", identifier=identifier
    )


def _worker(app: Flask, operation: Callable[[], object]) -> object:
    """Run a competing service call with its own ORM session and UOW context."""

    def execute() -> object:
        with app.app_context():
            return operation()

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(execute).result(timeout=10)


@pytest.fixture
def password_account(app: Flask, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    user_bid = uuid.uuid4().hex
    identifier = f"{user_bid[:12]}@example.com"
    monkeypatch.setitem(app.config, "UNIVERSAL_VERIFICATION_CODE", "")
    monkeypatch.setattr(token_store, "_cache", FakeRedis())
    with app.app_context():
        create_user_entity(
            user_bid=user_bid,
            identify=identifier,
            state=USER_STATE_REGISTERED,
            language="en-US",
        )
        upsert_credential(
            app,
            user_bid=user_bid,
            provider_name="email",
            subject_id=identifier,
            subject_format="email",
            identifier=identifier,
            metadata={},
            verified=True,
        )
        db.session.commit()
        _issue_code(identifier)
        password_flow.set_password(
            app,
            user_bid=user_bid,
            identifier=identifier,
            code=_CODE,
            new_password=_OLD_PASSWORD,
        )
    return user_bid, identifier


def _login(app: Flask, identifier: str, password: str) -> dict:
    with app.test_client() as client:
        response = client.post(
            "/api/user/login_password",
            json={"identifier": identifier, "password": password},
        )
    assert response.status_code == 200
    return json.loads(response.data)


def _credential(user_bid: str) -> AuthCredential:
    return (
        AuthCredential.query.filter_by(
            user_bid=user_bid, provider_name="password", deleted=0
        )
        .order_by(AuthCredential.id.asc())
        .first()
    )


def _save_session(app: Flask, user_bid: str, *, expired: bool = False) -> str:
    token = user_utils.create_token_value(app, user_bid)
    with unit_of_work():
        user_utils.persist_token(app, user_id=user_bid, token=token)
    if expired:
        UserToken.query.filter_by(token=token).one().token_expired_at = (
            now_utc() - timedelta(seconds=1)
        )
        db.session.commit()
    token_store._cache.set(token_store._refresh_marker_key(app, token), "1", ex=120)
    return token


@pytest.mark.parametrize("competing_action", ["reset", "change"])
def test_login_rejects_password_changed_after_verification_before_issue(
    app: Flask,
    password_account: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
    competing_action: str,
) -> None:
    import flaskr.route.user as user_route

    user_bid, identifier = password_account
    with app.app_context():
        _issue_code(identifier)
    original_confirm = user_route.confirm_password_login_for_token_issue
    confirmations: list[bool] = []

    def confirm_after_competing_write(**evidence: object) -> None:
        def write() -> None:
            if competing_action == "reset":
                password_flow.reset_password(
                    app, identifier=identifier, code=_CODE, new_password=_NEW_PASSWORD
                )
            else:
                password_flow.change_password(
                    app,
                    user_bid=user_bid,
                    old_password=_OLD_PASSWORD,
                    new_password=_NEW_PASSWORD,
                )

        _worker(app, write)
        confirmations.append(True)
        original_confirm(**evidence)

    monkeypatch.setattr(
        user_route,
        "confirm_password_login_for_token_issue",
        confirm_after_competing_write,
    )
    body = _login(app, identifier, _OLD_PASSWORD)
    assert confirmations == [True]
    assert body["code"] == ERROR_CODE["server.user.invalidCredentials"]
    with app.app_context():
        assert UserToken.query.filter_by(user_id=user_bid).count() == 0
        assert verify_password(_NEW_PASSWORD, get_password_hash(_credential(user_bid)))


def test_change_rejects_stale_old_password_instead_of_overwriting_winner(
    app: Flask,
    password_account: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_bid, _identifier = password_account
    original_verify = password_flow.verify_password
    competed = False

    def verify_then_compete(plain_text: str, stored_hash: str) -> bool:
        nonlocal competed
        matched = original_verify(plain_text, stored_hash)
        if matched and not competed:
            competed = True
            _worker(
                app,
                lambda: password_flow.change_password(
                    app,
                    user_bid=user_bid,
                    old_password=_OLD_PASSWORD,
                    new_password=_WINNER_PASSWORD,
                ),
            )
        return matched

    monkeypatch.setattr(password_flow, "verify_password", verify_then_compete)
    with app.app_context(), pytest.raises(AppError) as error:
        password_flow.change_password(
            app,
            user_bid=user_bid,
            old_password=_OLD_PASSWORD,
            new_password=_NEW_PASSWORD,
        )
    assert competed
    assert error.value.code == ERROR_CODE["server.user.invalidCredentials"]
    with app.app_context():
        assert verify_password(
            _WINNER_PASSWORD, get_password_hash(_credential(user_bid))
        )


@pytest.mark.parametrize("expired", [False, True])
def test_reset_revokes_every_durable_session_and_cache_only_after_commit(
    app: Flask,
    password_account: tuple[str, str],
    expired: bool,
) -> None:
    user_bid, identifier = password_account
    with app.app_context():
        token = _save_session(app, user_bid, expired=expired)
        _issue_code(identifier)
        key = token_store._cache_key(app, token)
        marker = token_store._refresh_marker_key(app, token)
        with unit_of_work():
            password_flow.reset_password(
                app, identifier=identifier, code=_CODE, new_password=_NEW_PASSWORD
            )
            assert token_store._cache.get(key) == user_bid.encode()
            assert token_store._cache.get(marker) == b"1"
            assert UserToken.query.filter_by(user_id=user_bid).count() == 0
        assert token_store._cache.get(key) is None
        assert token_store._cache.get(marker) is None
        assert (
            token_store.get_and_refresh(
                app, token=token, expected_user_id=user_bid, ttl_seconds=120
            )
            is None
        )


def test_normal_login_change_and_reset_preserve_distinct_session_policies(
    app: Flask, password_account: tuple[str, str]
) -> None:
    user_bid, identifier = password_account
    logged_in = _login(app, identifier, _OLD_PASSWORD)
    assert logged_in["code"] == 0
    token = logged_in["data"]["token"]
    with app.app_context():
        password_flow.change_password(
            app,
            user_bid=user_bid,
            old_password=_OLD_PASSWORD,
            new_password=_NEW_PASSWORD,
        )
        assert (
            token_store.get_and_refresh(
                app, token=token, expected_user_id=user_bid, ttl_seconds=120
            ).user_id
            == user_bid
        )
        db.session.commit()
    assert (
        _login(app, identifier, _OLD_PASSWORD)["code"]
        == ERROR_CODE["server.user.invalidCredentials"]
    )
    assert _login(app, identifier, _NEW_PASSWORD)["code"] == 0
    with app.app_context():
        _issue_code(identifier)
        password_flow.reset_password(
            app, identifier=identifier, code=_CODE, new_password=_WINNER_PASSWORD
        )
        assert UserToken.query.filter_by(user_id=user_bid).count() == 0
        assert (
            token_store.get_and_refresh(
                app, token=token, expected_user_id=user_bid, ttl_seconds=120
            )
            is None
        )
    assert (
        _login(app, identifier, _NEW_PASSWORD)["code"]
        == ERROR_CODE["server.user.invalidCredentials"]
    )
    assert _login(app, identifier, _WINNER_PASSWORD)["code"] == 0


def test_wrong_old_password_changes_neither_credentials_nor_sessions(
    app: Flask, password_account: tuple[str, str]
) -> None:
    user_bid, _identifier = password_account
    with app.app_context():
        token = _save_session(app, user_bid)
        with pytest.raises(AppError) as error:
            password_flow.change_password(
                app,
                user_bid=user_bid,
                old_password="Wrong12345",
                new_password=_NEW_PASSWORD,
            )
        assert error.value.code == ERROR_CODE["server.user.invalidCredentials"]
        assert verify_password(_OLD_PASSWORD, get_password_hash(_credential(user_bid)))
        assert UserToken.query.filter_by(token=token).count() == 1
        assert (
            token_store._cache.get(token_store._cache_key(app, token))
            == user_bid.encode()
        )


@pytest.mark.parametrize("code_state", ["wrong", "expired", "missing"])
def test_invalid_recovery_code_never_changes_password_or_revokes_sessions(
    app: Flask, password_account: tuple[str, str], code_state: str
) -> None:
    user_bid, identifier = password_account
    with app.app_context():
        token = _save_session(app, user_bid)
        if code_state != "missing":
            _issue_code(identifier, expired=code_state == "expired")
        with pytest.raises(AppError) as error:
            password_flow.reset_password(
                app,
                identifier=identifier,
                code="bad-code" if code_state == "wrong" else _CODE,
                new_password=_NEW_PASSWORD,
            )
        expected = (
            "server.user.mailCheckError"
            if code_state == "wrong"
            else "server.user.mailSendExpired"
        )
        assert error.value.code == ERROR_CODE[expected]
        assert verify_password(_OLD_PASSWORD, get_password_hash(_credential(user_bid)))
        assert UserToken.query.filter_by(token=token).count() == 1
        assert (
            token_store._cache.get(token_store._cache_key(app, token))
            == user_bid.encode()
        )


@pytest.mark.parametrize("failure_kind", ["after_reset", "commit"])
def test_reset_failure_rolls_back_password_and_sessions_without_cache_eviction(
    app: Flask,
    password_account: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    user_bid, identifier = password_account
    with app.app_context():
        token = _save_session(app, user_bid)
        _issue_code(identifier)
        key = token_store._cache_key(app, token)
        marker = token_store._refresh_marker_key(app, token)

        def fail_commit() -> None:
            message = "reset commit failed"
            raise RuntimeError(message)

        if failure_kind == "commit":
            monkeypatch.setattr(db.session, "commit", fail_commit)

        def reset_and_fail() -> None:
            with unit_of_work():
                password_flow.reset_password(
                    app, identifier=identifier, code=_CODE, new_password=_NEW_PASSWORD
                )
                if failure_kind == "after_reset":
                    message = "reset followup failed"
                    raise RuntimeError(message)

        with pytest.raises(RuntimeError, match=r"reset .*failed"):
            reset_and_fail()
        assert verify_password(_OLD_PASSWORD, get_password_hash(_credential(user_bid)))
        assert UserToken.query.filter_by(token=token).count() == 1
        assert token_store._cache.get(key) == user_bid.encode()
        assert token_store._cache.get(marker) == b"1"


@pytest.mark.parametrize("failing_operation", ["delete", "getex"])
def test_reset_durable_revocation_survives_cache_failures(
    app: Flask,
    password_account: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
    failing_operation: str,
) -> None:
    user_bid, identifier = password_account
    with app.app_context():
        token = _save_session(app, user_bid)
        _issue_code(identifier)

        def unavailable(*_args: object, **_kwargs: object) -> None:
            message = "cache unavailable"
            raise RuntimeError(message)

        monkeypatch.setattr(token_store._cache, failing_operation, unavailable)
        password_flow.reset_password(
            app, identifier=identifier, code=_CODE, new_password=_NEW_PASSWORD
        )
        assert UserToken.query.filter_by(user_id=user_bid).count() == 0
        assert (
            token_store.get_and_refresh(
                app, token=token, expected_user_id=user_bid, ttl_seconds=120
            )
            is None
        )
        assert verify_password(_NEW_PASSWORD, get_password_hash(_credential(user_bid)))


def test_reset_through_another_contact_replaces_the_effective_account_password(
    app: Flask, password_account: tuple[str, str]
) -> None:
    user_bid, identifier = password_account
    phone = f"155{int(user_bid[:8], 16) % 100000000:08d}"
    with app.app_context():
        upsert_credential(
            app,
            user_bid=user_bid,
            provider_name="phone",
            subject_id=phone,
            subject_format="phone",
            identifier=phone,
            metadata={},
            verified=True,
        )
        db.session.commit()
        _issue_code(phone)
        password_flow.reset_password(
            app, identifier=phone, code=_CODE, new_password=_NEW_PASSWORD
        )
        assert verify_password(_NEW_PASSWORD, get_password_hash(_credential(user_bid)))
        assert (
            AuthCredential.query.filter_by(
                user_bid=user_bid, provider_name="password", deleted=0
            ).count()
            == 1
        )
    assert (
        _login(app, identifier, _OLD_PASSWORD)["code"]
        == ERROR_CODE["server.user.invalidCredentials"]
    )
    assert _login(app, phone, _NEW_PASSWORD)["code"] == 0


def test_change_rechecks_a_stale_orm_credential_inside_an_outer_transaction(
    app: Flask, password_account: tuple[str, str]
) -> None:
    user_bid, _identifier = password_account

    def change_after_competing_commit() -> None:
        with unit_of_work():
            stale = _credential(user_bid)
            _worker(
                app,
                lambda: password_flow.change_password(
                    app,
                    user_bid=user_bid,
                    old_password=_OLD_PASSWORD,
                    new_password=_WINNER_PASSWORD,
                ),
            )
            assert verify_password(_OLD_PASSWORD, get_password_hash(stale))
            password_flow.change_password(
                app,
                user_bid=user_bid,
                old_password=_OLD_PASSWORD,
                new_password=_NEW_PASSWORD,
            )

    with app.app_context(), pytest.raises(AppError) as error:
        change_after_competing_commit()
    assert error.value.code == ERROR_CODE["server.user.invalidCredentials"]
    with app.app_context():
        assert verify_password(
            _WINNER_PASSWORD, get_password_hash(_credential(user_bid))
        )


def _move_email(user_bid: str, identifier: str) -> None:
    from flaskr.service.user.models import UserInfo

    UserInfo.query.filter_by(user_bid=user_bid).one().user_identify = identifier
    contact = AuthCredential.query.filter_by(
        user_bid=user_bid, provider_name="email", deleted=0
    ).one()
    contact.identifier = identifier
    contact.subject_id = identifier


@pytest.mark.parametrize(
    "transition",
    [
        "credential_deleted",
        "credential_replaced",
        "credential_unverified",
        "user_deleted",
        "contact_moved",
    ],
)
def test_login_rejects_changed_account_or_credential_after_verification(
    app: Flask,
    password_account: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
    transition: str,
) -> None:
    import flaskr.route.user as user_route
    from flaskr.service.user.consts import CREDENTIAL_STATE_UNVERIFIED
    from flaskr.service.user.models import UserInfo

    user_bid, identifier = password_account
    original_confirm = user_route.confirm_password_login_for_token_issue
    transitions: list[str] = []

    def confirm_after_transition(**evidence: object) -> None:
        def mutate() -> None:
            with unit_of_work():
                credential = _credential(user_bid)
                if transition == "credential_deleted":
                    credential.deleted = 1
                elif transition == "credential_replaced":
                    credential.deleted = 1
                    db.session.add(
                        AuthCredential(
                            credential_bid=uuid.uuid4().hex,
                            user_bid=user_bid,
                            provider_name="password",
                            subject_id=identifier,
                            subject_format="email",
                            identifier=identifier,
                            raw_profile=credential.raw_profile,
                            state=credential.state,
                            deleted=0,
                        )
                    )
                elif transition == "credential_unverified":
                    credential.state = CREDENTIAL_STATE_UNVERIFIED
                elif transition == "user_deleted":
                    UserInfo.query.filter_by(user_bid=user_bid).one().deleted = 1
                else:
                    _move_email(user_bid, f"moved-{identifier}")

        _worker(app, mutate)
        transitions.append(transition)
        original_confirm(**evidence)

    monkeypatch.setattr(
        user_route, "confirm_password_login_for_token_issue", confirm_after_transition
    )
    assert (
        _login(app, identifier, _OLD_PASSWORD)["code"]
        == ERROR_CODE["server.user.invalidCredentials"]
    )
    assert transitions == [transition]
    with app.app_context():
        assert UserToken.query.filter_by(user_id=user_bid).count() == 0


def test_old_password_credential_identifier_does_not_become_a_login_alias(
    app: Flask, password_account: tuple[str, str]
) -> None:
    user_bid, old_identifier = password_account
    new_identifier = f"moved-{old_identifier}"
    with app.app_context(), unit_of_work():
        _move_email(user_bid, new_identifier)
    assert (
        _login(app, old_identifier, _OLD_PASSWORD)["code"]
        == ERROR_CODE["server.user.invalidCredentials"]
    )
    assert _login(app, new_identifier, _OLD_PASSWORD)["code"] == 0
    with app.app_context():
        assert _credential(user_bid).identifier == old_identifier


def test_delayed_login_cache_population_cannot_revive_a_reset_session(
    app: Flask,
    password_account: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_bid, identifier = password_account
    with app.app_context():
        _issue_code(identifier)
    original_set = token_store._cache.set
    delayed: list[str] = []

    def populate_after_reset(
        key: str, value: object, *args: object, **kwargs: object
    ) -> object:
        if not delayed and value == user_bid:
            delayed.append(key)
            _worker(
                app,
                lambda: password_flow.reset_password(
                    app, identifier=identifier, code=_CODE, new_password=_NEW_PASSWORD
                ),
            )
        return original_set(key, value, *args, **kwargs)

    monkeypatch.setattr(token_store._cache, "set", populate_after_reset)
    body = _login(app, identifier, _OLD_PASSWORD)
    assert body["code"] == 0
    token = body["data"]["token"]
    with app.app_context():
        key = token_store._cache_key(app, token)
        assert delayed == [key]
        assert token_store._cache.get(key) == user_bid.encode()
        assert UserToken.query.filter_by(token=token).count() == 0
        assert (
            token_store.get_and_refresh(
                app, token=token, expected_user_id=user_bid, ttl_seconds=120
            )
            is None
        )
