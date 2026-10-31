"""Prove password-reset ordering with independent InnoDB transactions."""

from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from typing import TYPE_CHECKING

import pytest
from flaskr.common.cache_provider import InMemoryCacheProvider
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import password_flow
from flaskr.service.user.models import AuthCredential, UserToken, UserVerifyCode
from flaskr.service.user.password_utils import hash_password, verify_password
from flaskr.service.user.repository import (
    create_user_entity,
    get_password_hash,
    set_password_hash,
    upsert_credential,
)
from flaskr.service.user.token_store import token_store
from flaskr.service.user.utils import create_token_value
from flaskr.util.datetime import now_utc
from sqlalchemy import text

from tests.common.fixtures.fake_redis import FakeRedis

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

    from flask import Flask
    from sqlalchemy.engine import Engine


pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_SQLALCHEMY_DATABASE_URI", "").startswith("mysql"),
    reason="Set TEST_SQLALCHEMY_DATABASE_URI to a disposable MySQL/InnoDB database.",
)

_OLD_PASSWORD = "Initial12345"
_NEW_PASSWORD = "Changed12345"
_CODE = "623751"
_WAIT_SECONDS = 10


@pytest.fixture
def mysql_password_account(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, str]:
    """Seed real credentials and a real single-use reset code."""
    monkeypatch.setitem(app.config, "UNIVERSAL_VERIFICATION_CODE", "")
    monkeypatch.setattr(token_store, "_cache", FakeRedis())
    user_bid = uuid.uuid4().hex
    identifier = f"{user_bid[:12]}@example.com"
    with app.app_context():
        if db.engine.dialect.name != "mysql":
            pytest.skip("Independent row-lock assertions require MySQL/InnoDB.")
        with db.engine.connect() as observer:
            if observer.execute(text("SELECT @@performance_schema")).scalar() != 1:
                pytest.skip("Enable performance_schema to observe actual lock waits.")
            observer.execute(
                text("SELECT COUNT(*) FROM performance_schema.data_lock_waits")
            )
            engines = (
                observer.execute(
                    text(
                        "SELECT ENGINE FROM information_schema.TABLES "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN "
                        "('user_users', 'user_auth_credentials', 'user_token')"
                    )
                )
                .scalars()
                .all()
            )
            assert len(engines) == 3
            assert set(engines) == {"InnoDB"}
        with unit_of_work():
            create_user_entity(user_bid=user_bid, identify=identifier)
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
            credential = upsert_credential(
                app,
                user_bid=user_bid,
                provider_name="password",
                subject_id=identifier,
                subject_format="email",
                identifier=identifier,
                metadata={},
                verified=True,
            )
            set_password_hash(credential, hash_password(_OLD_PASSWORD))
            db.session.add(
                UserVerifyCode(
                    mail=identifier,
                    verify_code=_CODE,
                    verify_code_type=2,
                    verify_code_send=1,
                    verify_code_used=0,
                    created=now_utc(),
                )
            )
    return user_bid, identifier


def _in_app(app: Flask, operation: Callable[[], object]) -> object:
    """Give each worker its own app-scoped session and fresh UOW ContextVars."""
    with app.app_context():
        return operation()


def _connection_id() -> int:
    return int(db.session.execute(text("SELECT CONNECTION_ID()")).scalar_one())


def _wait_until_set(event: Event, description: str) -> None:
    assert event.wait(_WAIT_SECONDS), f"Timed out waiting for {description}"


def _observe_account_lock_wait(
    engine: Engine,
    *,
    waiter_id: int,
    blocker_id: int,
    contender: Future,
) -> None:
    """Wait for a measured InnoDB lock edge, never infer it from elapsed time."""
    statement = text(
        "SELECT COUNT(*) FROM performance_schema.data_lock_waits AS waits "
        "JOIN performance_schema.threads AS waiter "
        "ON waiter.THREAD_ID = waits.REQUESTING_THREAD_ID "
        "JOIN performance_schema.threads AS blocker "
        "ON blocker.THREAD_ID = waits.BLOCKING_THREAD_ID "
        "JOIN performance_schema.data_locks AS requested "
        "ON requested.ENGINE_LOCK_ID = waits.REQUESTING_ENGINE_LOCK_ID "
        "AND requested.ENGINE = waits.ENGINE "
        "WHERE waiter.PROCESSLIST_ID = :waiter_id "
        "AND blocker.PROCESSLIST_ID = :blocker_id "
        "AND requested.OBJECT_SCHEMA = DATABASE() "
        "AND requested.OBJECT_NAME = 'user_users'"
    )
    deadline = time.monotonic() + _WAIT_SECONDS
    poll = Event()
    with engine.connect() as observer:
        while time.monotonic() < deadline:
            if observer.execute(
                statement, {"waiter_id": waiter_id, "blocker_id": blocker_id}
            ).scalar_one():
                assert not contender.done()
                return
            if contender.done():
                contender.result()
                pytest.fail("Contender completed without waiting for the account lock")
            poll.wait(0.01)
    pytest.fail("No matching InnoDB account-row lock wait was observed")


def _login(app: Flask, identifier: str) -> dict:
    with app.test_client() as client:
        response = client.post(
            "/api/user/login_password",
            json={"identifier": identifier, "password": _OLD_PASSWORD},
        )
    assert response.status_code == 200
    return response.get_json(force=True)


def _reset(app: Flask, identifier: str) -> None:
    password_flow.reset_password(
        app, identifier=identifier, code=_CODE, new_password=_NEW_PASSWORD
    )


def _assert_reset_committed(app: Flask, user_bid: str, revoked_token: str) -> None:
    with app.app_context():
        assert UserToken.query.filter_by(user_id=user_bid).count() == 0
        credential = AuthCredential.query.filter_by(
            user_bid=user_bid, provider_name="password", deleted=0
        ).one()
        assert verify_password(_NEW_PASSWORD, get_password_hash(credential))
        assert (
            token_store.get_and_refresh(
                app, token=revoked_token, expected_user_id=user_bid, ttl_seconds=120
            )
            is None
        )


def test_reset_waits_for_password_issuance_then_revokes_its_committed_token(
    app: Flask,
    mysql_password_account: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_bid, identifier = mysql_password_account
    issued = Event()
    release_issue = Event()
    resetting = Event()
    connections: dict[str, int] = {}
    original_save = token_store.save

    def save_before_commit(*args: object, **kwargs: object) -> None:
        original_save(*args, **kwargs)
        connections["issue"] = _connection_id()
        issued.set()
        _wait_until_set(release_issue, "release of password issuance")

    def reset() -> None:
        connections["reset"] = _connection_id()
        resetting.set()
        _reset(app, identifier)

    monkeypatch.setattr(token_store, "save", save_before_commit)
    with app.app_context():
        engine = db.engine
    with ThreadPoolExecutor(max_workers=2) as executor:
        login = executor.submit(_login, app, identifier)
        reset_future = None
        try:
            _wait_until_set(issued, "staged password session")
            reset_future = executor.submit(_in_app, app, reset)
            _wait_until_set(resetting, "reset contender")
            _observe_account_lock_wait(
                engine,
                waiter_id=connections["reset"],
                blocker_id=connections["issue"],
                contender=reset_future,
            )
        finally:
            release_issue.set()
        body = login.result(timeout=_WAIT_SECONDS)
        assert reset_future is not None
        reset_future.result(timeout=_WAIT_SECONDS)
    assert body["code"] == 0
    _assert_reset_committed(app, user_bid, body["data"]["token"])


def test_password_verified_before_committed_reset_cannot_issue_after_reset(
    app: Flask,
    mysql_password_account: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flaskr.route.user as user_route

    user_bid, identifier = mysql_password_account
    verified = Event()
    release_confirmation = Event()
    original_confirm = user_route.confirm_password_login_for_token_issue

    def confirm_after_reset(**evidence: object) -> None:
        verified.set()
        _wait_until_set(release_confirmation, "password confirmation after reset")
        original_confirm(**evidence)

    monkeypatch.setattr(
        user_route, "confirm_password_login_for_token_issue", confirm_after_reset
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        login = executor.submit(_login, app, identifier)
        try:
            _wait_until_set(verified, "successful password verification")
            reset_future = executor.submit(
                _in_app, app, lambda: _reset(app, identifier)
            )
            reset_future.result(timeout=_WAIT_SECONDS)
        finally:
            release_confirmation.set()
        body = login.result(timeout=_WAIT_SECONDS)
    assert body["code"] == ERROR_CODE["server.user.invalidCredentials"]
    with app.app_context():
        assert UserToken.query.filter_by(user_id=user_bid).count() == 0
        credential = AuthCredential.query.filter_by(
            user_bid=user_bid, provider_name="password", deleted=0
        ).one()
        assert verify_password(_NEW_PASSWORD, get_password_hash(credential))


def test_shared_token_save_waits_for_reset_commit_before_creating_new_session(
    app: Flask, mysql_password_account: tuple[str, str]
) -> None:
    user_bid, identifier = mysql_password_account
    reset_staged = Event()
    release_reset = Event()
    saving = Event()
    connections: dict[str, int] = {}
    token = create_token_value(app, user_bid)
    with app.app_context():
        engine = db.engine

    def hold_reset() -> None:
        with unit_of_work():
            connections["reset"] = _connection_id()
            _reset(app, identifier)
            reset_staged.set()
            _wait_until_set(release_reset, "reset transaction commit")

    def save() -> None:
        with unit_of_work():
            connections["save"] = _connection_id()
            saving.set()
            token_store.save(app, user_id=user_bid, token=token, ttl_seconds=120)

    with ThreadPoolExecutor(max_workers=2) as executor:
        reset_future = executor.submit(_in_app, app, hold_reset)
        save_future = None
        try:
            _wait_until_set(reset_staged, "uncommitted reset")
            save_future = executor.submit(_in_app, app, save)
            _wait_until_set(saving, "token-save contender")
            _observe_account_lock_wait(
                engine,
                waiter_id=connections["save"],
                blocker_id=connections["reset"],
                contender=save_future,
            )
            assert token_store._cache.get(token_store._cache_key(app, token)) is None
        finally:
            release_reset.set()
        reset_future.result(timeout=_WAIT_SECONDS)
        assert save_future is not None
        save_future.result(timeout=_WAIT_SECONDS)
    with app.app_context():
        assert UserToken.query.filter_by(user_id=user_bid, token=token).count() == 1
        assert (
            token_store.get_and_refresh(
                app, token=token, expected_user_id=user_bid, ttl_seconds=120
            )
            is not None
        )


def test_simultaneous_resets_consume_one_real_code_only_once(
    app: Flask,
    mysql_password_account: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_bid, identifier = mysql_password_account
    before_consumption = Barrier(2)
    verification_cache = InMemoryCacheProvider()
    original_consume = password_flow.consume_verification_code
    old_tokens = [create_token_value(app, user_bid) for _index in range(2)]
    with app.app_context(), unit_of_work():
        for token in old_tokens:
            token_store.save(app, user_id=user_bid, token=token, ttl_seconds=120)

    def consume_together(*args: object, **kwargs: object) -> None:
        before_consumption.wait(timeout=_WAIT_SECONDS)
        original_consume(*args, **kwargs, cache_provider=verification_cache)

    def reset_to(password: str) -> tuple[str, AppError | None]:
        try:
            password_flow.reset_password(
                app, identifier=identifier, code=_CODE, new_password=password
            )
        except AppError as error:
            return password, error
        return password, None

    monkeypatch.setattr(password_flow, "consume_verification_code", consume_together)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_in_app, app, lambda password=password: reset_to(password))
            for password in (_NEW_PASSWORD, "OtherWinner12345")
        ]
        outcomes = [future.result(timeout=_WAIT_SECONDS) for future in futures]
    winners = [password for password, error in outcomes if error is None]
    rejected = [(password, error) for password, error in outcomes if error is not None]
    assert len(winners) == 1
    assert len(rejected) == 1
    losing_password, rejection = rejected[0]
    assert isinstance(rejection, AppError)
    assert rejection.code == ERROR_CODE["server.user.mailSendExpired"]
    with app.app_context():
        credential = AuthCredential.query.filter_by(
            user_bid=user_bid, provider_name="password", deleted=0
        ).one()
        current_hash = get_password_hash(credential)
        assert verify_password(winners[0], current_hash)
        assert not verify_password(losing_password, current_hash)
        assert (
            UserVerifyCode.query.filter_by(mail=identifier).one().verify_code_used == 1
        )
        assert UserToken.query.filter_by(user_id=user_bid).count() == 0
        for token in old_tokens:
            assert token_store._cache.get(token_store._cache_key(app, token)) is None
            assert (
                token_store.get_and_refresh(
                    app, token=token, expected_user_id=user_bid, ttl_seconds=120
                )
                is None
            )


def test_mysql_login_rejects_missing_verified_password_evidence(
    app: Flask,
    mysql_password_account: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.user.auth.providers.password import PasswordAuthProvider

    user_bid, identifier = mysql_password_account
    original_verify = PasswordAuthProvider.verify

    def verify_without_version(
        provider: PasswordAuthProvider, route_app: Flask, verification_request: object
    ) -> object:
        result = original_verify(provider, route_app, verification_request)
        # Drop evidence only after the real provider's read UOW and bcrypt check.
        result.metadata.pop("credential_version")
        return result

    with monkeypatch.context() as missing_evidence:
        missing_evidence.setattr(PasswordAuthProvider, "verify", verify_without_version)
        body = _login(app, identifier)
    assert body["code"] == ERROR_CODE["server.user.invalidCredentials"]
    with app.app_context():
        assert UserToken.query.filter_by(user_id=user_bid).count() == 0
    assert _login(app, identifier)["code"] == 0
