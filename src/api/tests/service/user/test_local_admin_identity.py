"""Verify local administrator identity isolation and password lifecycle."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import local_accounts, password_flow
from flaskr.service.user.auth import get_provider
from flaskr.service.user.auth.base import VerificationRequest
from flaskr.service.user.auth.providers import local_password
from flaskr.service.user.consts import CREDENTIAL_STATE_UNVERIFIED
from flaskr.service.user.installation_models import LocalAdminAccount
from flaskr.service.user.models import AuthCredential, UserToken
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.password_utils import verify_password
from flaskr.service.user.repository import (
    create_user_entity,
    find_credential,
    get_password_hash,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
)
from flaskr.service.user.token_store import token_store
from flaskr.util.datetime import now_utc
from sqlalchemy import event

from tests.common.fixtures.fake_redis import FakeRedis

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask


@pytest.fixture(params=["email", "phone"])
def local_admin(
    app: Flask, request: pytest.FixtureRequest
) -> Iterator[tuple[str, str]]:
    identifier = (
        f"owner_{uuid.uuid4().hex[:12]}@example.com"
        if request.param == "email"
        else f"138{uuid.uuid4().int % 100_000_000:08d}"
    )
    with app.app_context(), unit_of_work():
        user_bid = local_accounts.provision_local_admin_account(
            app, identifier=identifier, password="Initial123"
        )
    yield user_bid, identifier
    with app.app_context(), unit_of_work():
        UserToken.query.filter_by(user_id=user_bid).delete()
        LocalAdminAccount.query.filter_by(user_bid=user_bid).delete()
        AuthCredential.query.filter_by(user_bid=user_bid).delete()
        UserEntity.query.filter_by(user_bid=user_bid).delete()


def _verify(app: Flask, identifier: str, password: str | None = None) -> object:
    return local_password.LocalPasswordAuthProvider().verify(
        app,
        VerificationRequest(
            identifier=identifier,
            code=password if password is not None else "Initial123",
        ),
    )


def _confirm(result: object) -> None:
    local_password.confirm_local_admin_login_for_token_issue(
        user_bid=result.metadata["user_bid"],
        credential_bid=result.metadata["local_credential_bid"],
        identifier=result.metadata["local_identifier"],
        credential_version=result.metadata["credential_version"],
    )


@pytest.mark.parametrize(
    "identifier",
    [
        "ad",
        "1admin",
        "standalone_owner",
        "person@@example.com",
        "person@example",
        "+12125551234",
        "1１２３４５６７８９０",
        "admin name",
        "用户",
        "a" * 65,
    ],
)
def test_local_identifier_rejects_names_and_invalid_contacts(identifier: str) -> None:
    with pytest.raises(AppError) as error:
        local_accounts.normalize_local_identifier(identifier)
    assert error.value.code == ERROR_CODE["server.installation.invalidIdentifier"]


def test_local_identifier_normalizes_email_and_phone() -> None:
    assert (
        local_accounts.normalize_local_identifier("  OWNER.Name+tag@EXAMPLE.com ")
        == "owner.name+tag@example.com"
    )
    assert (
        local_accounts.normalize_local_identifier(" +86 13800138000 ") == "13800138000"
    )


@pytest.mark.parametrize("password", ["a1" * 37, "Valid123" + "字" * 22])
def test_local_password_refuses_bcrypt_byte_overflow(password: str) -> None:
    with pytest.raises(AppError) as error:
        local_accounts.validate_local_password(password)
    assert error.value.code == ERROR_CODE["server.installation.passwordTooLong"]


def test_local_provisioning_requires_the_bootstrap_transaction(app: Flask) -> None:
    with app.app_context(), pytest.raises(RuntimeError, match="active unit_of_work"):
        local_accounts.provision_local_admin_account(
            app, identifier="transaction_owner", password="Initial123"
        )


def test_provisioning_does_not_fabricate_verified_contact_credentials(
    app: Flask, local_admin: tuple[str, str]
) -> None:
    user_bid, identifier = local_admin
    with app.app_context():
        aggregate = load_user_aggregate(user_bid)
        assert aggregate is not None
        assert aggregate.identify == f"local:{user_bid}"
        assert aggregate.username == user_bid
        assert aggregate.nickname == ""
        assert aggregate.mobile == aggregate.email == ""
        assert aggregate.is_creator is True
        assert aggregate.is_operator is True
        assert [item.provider for item in aggregate.credentials] == ["local_password"]
        credential = find_credential(
            provider_name="local_password", identifier=identifier
        )
        assert credential is not None
        kind = "email" if "@" in identifier else "phone"
        assert credential.subject_format == f"local_{kind}"
        assert aggregate.credentials[0].metadata["contact_verification"] == "unverified"
        assert identifier not in str(aggregate.to_user_info().__json__())
        assert verify_password("Initial123", get_password_hash(credential))
        assert (
            load_user_aggregate_by_identifier(
                aggregate.identify, providers=["phone", "email"]
            )
            is None
        )


def test_duplicate_local_name_does_not_create_a_second_account(
    app: Flask, local_admin: tuple[str, str]
) -> None:
    _user_bid, identifier = local_admin
    with app.app_context():
        before = UserEntity.query.count()
        with pytest.raises(AppError) as error, unit_of_work():
            local_accounts.provision_local_admin_account(
                app, identifier=identifier.upper(), password="Other123"
            )
        assert (
            error.value.code == ERROR_CODE["server.installation.identifierUnavailable"]
        )
        assert UserEntity.query.count() == before


def test_provisioning_joins_the_callers_rollback(app: Flask) -> None:
    identifier = f"rolled_back_{uuid.uuid4().hex[:12]}@example.com"
    user_bids: list[str] = []

    def fail_after_provisioning() -> None:
        with unit_of_work():
            user_bids.append(
                local_accounts.provision_local_admin_account(
                    app, identifier=identifier, password="Initial123"
                )
            )
            message = "later bootstrap failure"
            raise RuntimeError(message)

    with app.app_context():
        with pytest.raises(RuntimeError, match="later bootstrap failure"):
            fail_after_provisioning()
        bid = user_bids[0]
        assert LocalAdminAccount.query.filter_by(identifier=identifier).first() is None
        assert AuthCredential.query.filter_by(user_bid=bid).first() is None
        assert UserEntity.query.filter_by(user_bid=bid).first() is None


def test_local_provider_uses_existing_token_shape_without_persisting_early(
    app: Flask, local_admin: tuple[str, str]
) -> None:
    user_bid, identifier = local_admin
    with app.app_context():
        assert isinstance(
            get_provider("local_password"), local_password.LocalPasswordAuthProvider
        )
        result = _verify(app, identifier.upper())
        assert result.user.user_id == user_bid
        assert result.user.username == user_bid
        assert result.user.email == result.user.mobile == ""
        assert result.user.__json__()["has_local_password"] is True
        assert result.token.userInfo.user_id == user_bid
        assert result.token.token
        assert result.is_new_user is False
        assert UserToken.query.filter_by(user_id=user_bid).count() == 0
        with unit_of_work():
            _confirm(result)


def test_ordinary_user_payload_does_not_claim_a_local_password(app: Flask) -> None:
    user_bid = uuid.uuid4().hex
    with app.app_context(), unit_of_work():
        create_user_entity(user_bid=user_bid, identify=f"{user_bid}@example.com")
        aggregate = load_user_aggregate(user_bid)
        assert aggregate is not None
        assert aggregate.to_user_info().has_local_password is False
        assert "has_local_password" not in aggregate.to_user_info().__json__()


def test_missing_local_binding_never_falls_back_to_an_existing_contact_account(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = f"contact_{uuid.uuid4().hex[:12]}"
    with app.app_context(), unit_of_work():
        # Old imported canonical identifiers do not establish a local binding.
        entity = create_user_entity(
            user_bid=uuid.uuid4().hex, identify=identifier, nickname=identifier
        )
        entity.is_operator = 1
    hashes: list[str] = []

    def record_hash(_password: str, password_hash: str) -> bool:
        hashes.append(password_hash)
        return False

    monkeypatch.setattr(local_password, "verify_password", record_hash)
    with app.app_context(), pytest.raises(AppError) as error:
        _verify(app, identifier)
    assert error.value.code == ERROR_CODE["server.user.invalidCredentials"]
    assert hashes == [local_password._DUMMY_PASSWORD_HASH]


@pytest.mark.parametrize(
    "mutation",
    ["operator", "user_deleted", "binding_deleted", "credential_deleted", "unverified"],
)
def test_local_login_rejects_disabled_or_changed_authority(
    app: Flask, local_admin: tuple[str, str], mutation: str
) -> None:
    user_bid, identifier = local_admin
    with app.app_context(), unit_of_work():
        user = UserEntity.query.filter_by(user_bid=user_bid).one()
        binding = LocalAdminAccount.query.filter_by(user_bid=user_bid).one()
        credential = AuthCredential.query.filter_by(user_bid=user_bid).one()
        if mutation == "operator":
            user.is_operator = 0
        elif mutation == "user_deleted":
            user.deleted = 1
        elif mutation == "binding_deleted":
            binding.deleted = 1
        elif mutation == "credential_deleted":
            credential.deleted = 1
        else:
            credential.state = CREDENTIAL_STATE_UNVERIFIED
    with app.app_context(), pytest.raises(AppError) as error:
        _verify(app, identifier)
    assert error.value.code == ERROR_CODE["server.user.invalidCredentials"]


def test_local_login_uses_account_rate_limit_and_console_reset_clears_cooldown(
    app: Flask, local_admin: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _user_bid, identifier = local_admin
    monkeypatch.setitem(app.config, "PASSWORD_LOGIN_MAX_FAILURES", 2)
    with app.app_context():
        with pytest.raises(AppError) as first:
            _verify(app, identifier, "Incorrect123")
        assert first.value.code == ERROR_CODE["server.user.invalidCredentials"]
        with pytest.raises(AppError) as second:
            _verify(app, identifier, "Incorrect123")
        assert (
            second.value.code == ERROR_CODE["server.user.passwordLoginTooManyAttempts"]
        )
        with pytest.raises(AppError) as blocked:
            _verify(app, identifier)
        assert (
            blocked.value.code == ERROR_CODE["server.user.passwordLoginTooManyAttempts"]
        )
        local_accounts.reset_local_admin_password(
            app, identifier=identifier, new_password="Recovered123"
        )
        assert _verify(app, identifier, "Recovered123").user.user_id


def test_waiting_for_local_password_guards_holds_no_database_transaction(
    app: Flask, local_admin: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _user_bid, identifier = local_admin
    real_attempt = local_password.PasswordLoginAttempt
    transaction_states: list[bool] = []

    class CheckedAttempt:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.delegate = real_attempt(*args, **kwargs)

        def __enter__(self) -> object:
            transaction_states.append(db.session().in_transaction())
            return self.delegate.__enter__()

        def __exit__(self, *args: object) -> None:
            self.delegate.__exit__(*args)

    monkeypatch.setattr(local_password, "PasswordLoginAttempt", CheckedAttempt)
    with app.app_context():
        _verify(app, identifier)
    assert transaction_states
    assert not any(transaction_states)


@pytest.mark.parametrize("mutation", ["operator", "binding", "credential"])
def test_token_confirmation_rechecks_authority_after_password_verification(
    app: Flask, local_admin: tuple[str, str], mutation: str
) -> None:
    user_bid, identifier = local_admin
    with app.app_context():
        result = _verify(app, identifier)
        with unit_of_work():
            if mutation == "operator":
                UserEntity.query.filter_by(user_bid=user_bid).one().is_operator = 0
            elif mutation == "binding":
                LocalAdminAccount.query.filter_by(user_bid=user_bid).one().deleted = 1
            else:
                AuthCredential.query.filter_by(
                    user_bid=user_bid
                ).one().state = CREDENTIAL_STATE_UNVERIFIED
        with pytest.raises(AppError), unit_of_work():
            _confirm(result)
        assert UserToken.query.filter_by(user_id=user_bid).count() == 0


def test_console_reset_revokes_sessions_and_rejects_inflight_old_password_evidence(
    app: Flask, local_admin: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    user_bid, identifier = local_admin
    cache = FakeRedis()
    monkeypatch.setattr(token_store, "_cache", cache)
    with app.app_context():
        result = _verify(app, identifier)
        with unit_of_work():
            token_store.save(
                app, user_id=user_bid, token="old-local-token", ttl_seconds=300
            )
        cache.set(token_store._refresh_marker_key(app, "old-local-token"), "1")
        assert cache.get(token_store._cache_key(app, "old-local-token"))

        local_accounts.reset_local_admin_password(
            app, identifier=identifier, new_password="Recovered123"
        )
        assert UserToken.query.filter_by(user_id=user_bid).count() == 0
        assert cache.get(token_store._cache_key(app, "old-local-token")) is None
        assert (
            cache.get(token_store._refresh_marker_key(app, "old-local-token")) is None
        )
        with pytest.raises(AppError), unit_of_work():
            _confirm(result)
        with pytest.raises(AppError):
            _verify(app, identifier)
        assert _verify(app, identifier, "Recovered123").user.user_id == user_bid


def test_console_reset_rolls_back_password_when_durable_session_revoke_fails(
    app: Flask, local_admin: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    user_bid, identifier = local_admin
    failure = Mock(side_effect=RuntimeError("durable deletion failed"))
    monkeypatch.setattr(token_store, "revoke_all", failure)
    with app.app_context():
        credential = AuthCredential.query.filter_by(user_bid=user_bid).one()
        original_hash = get_password_hash(credential)
        with pytest.raises(RuntimeError, match="durable deletion failed"):
            local_accounts.reset_local_admin_password(
                app, identifier=identifier, new_password="Recovered123"
            )
        db.session.expire_all()
        assert get_password_hash(credential) == original_hash


def test_token_revocation_joins_rollback_and_defers_cache_effects(
    app: Flask, local_admin: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    user_bid, _username = local_admin
    cache = FakeRedis()
    monkeypatch.setattr(token_store, "_cache", cache)
    with app.app_context():
        with unit_of_work():
            token_store.save(
                app, user_id=user_bid, token="retained-local-token", ttl_seconds=300
            )
        key = token_store._cache_key(app, "retained-local-token")

        def fail_after_revocation() -> None:
            with unit_of_work():
                assert token_store.revoke_all(app, user_id=user_bid) == 1
                assert cache.get(key)
                message = "later failure"
                raise RuntimeError(message)

        with pytest.raises(RuntimeError, match="later failure"):
            fail_after_revocation()
        assert UserToken.query.filter_by(user_id=user_bid).count() == 1
        assert cache.get(key)


def test_console_reset_remains_durable_when_cache_eviction_is_unavailable(
    app: Flask, local_admin: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    user_bid, identifier = local_admin

    class UnavailableCache:
        def delete(self, *_keys: str) -> None:
            raise ConnectionError

        def getex(self, *_args: object, **_kwargs: object) -> None:
            raise ConnectionError

    monkeypatch.setattr(token_store, "_cache", UnavailableCache())
    with app.app_context(), unit_of_work():
        db.session.add(
            UserToken(
                user_id=user_bid,
                token="stale-local-token",
                token_type=0,
                token_expired_at=now_utc() + timedelta(seconds=300),
            )
        )
    local_accounts.reset_local_admin_password(
        app, identifier=identifier, new_password="Recovered123"
    )
    with app.app_context():
        assert (
            token_store.get_and_refresh(
                app,
                token="stale-local-token",
                expected_user_id=user_bid,
                ttl_seconds=300,
            )
            is None
        )


def test_local_password_change_preserves_contact_code_requirements(
    app: Flask, local_admin: tuple[str, str]
) -> None:
    user_bid, identifier = local_admin
    with app.app_context():
        result = _verify(app, identifier)
        password_flow.change_password(
            app, user_bid=user_bid, old_password="Initial123", new_password="Changed123"
        )
        with pytest.raises(AppError), unit_of_work():
            _confirm(result)
        assert _verify(app, identifier, "Changed123").user.user_id == user_bid
        with pytest.raises(AppError) as error:
            password_flow.set_password(
                app,
                user_bid=user_bid,
                identifier=identifier,
                code="anything",
                new_password="Another123",
            )
        assert error.value.code == ERROR_CODE["server.user.invalidCredentials"]


def test_stale_password_change_cannot_overwrite_completed_console_recovery(
    app: Flask, local_admin: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    user_bid, identifier = local_admin
    original_verify = password_flow.verify_password
    recovery_completed = False
    with ThreadPoolExecutor(max_workers=1) as executor:

        def recover_after_old_password_check(plain: str, password_hash: str) -> bool:
            nonlocal recovery_completed
            matches = original_verify(plain, password_hash)
            if matches and not recovery_completed:
                executor.submit(
                    local_accounts.reset_local_admin_password,
                    app,
                    identifier=identifier,
                    new_password="Recovered123",
                ).result(timeout=5)
                recovery_completed = True
            return matches

        monkeypatch.setattr(
            password_flow, "verify_password", recover_after_old_password_check
        )
        with app.app_context(), pytest.raises(AppError) as error:
            password_flow.change_password(
                app,
                user_bid=user_bid,
                old_password="Initial123",
                new_password="StaleChange123",
            )
        assert error.value.code == ERROR_CODE["server.user.invalidCredentials"]
    assert recovery_completed
    with app.app_context():
        assert _verify(app, identifier, "Recovered123").user.user_id == user_bid
        with pytest.raises(AppError):
            _verify(app, identifier, "StaleChange123")


def test_console_recovery_serializes_with_confirmed_login_and_revokes_its_token(
    app: Flask, local_admin: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.route import installation as installation_routes

    user_bid, identifier = local_admin
    original_persist = installation_routes.persist_token
    write_attempted = threading.Event()
    worker_ids: set[int] = set()
    future = None
    with app.app_context():
        engine = db.engine
        original_updated_at = (
            UserEntity.query.filter_by(user_bid=user_bid).one().updated_at
        )

    def observe_recovery_write(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        if (
            threading.get_ident() in worker_ids
            and statement.lstrip().upper().startswith("UPDATE")
        ):
            write_attempted.set()

    def recover() -> None:
        worker_ids.add(threading.get_ident())
        local_accounts.reset_local_admin_password(
            app, identifier=identifier, new_password="Recovered123"
        )

    event.listen(engine, "before_cursor_execute", observe_recovery_write)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:

            def persist_after_recovery_attempt(*args: object, **kwargs: object) -> None:
                nonlocal future
                future = executor.submit(recover)
                assert write_attempted.wait(timeout=5)
                # SQLite ignores SELECT FOR UPDATE. The conditional user-row
                # write must hold recovery here until this login commits.
                with pytest.raises(TimeoutError):
                    future.result(timeout=0.5)
                original_persist(*args, **kwargs)

            monkeypatch.setattr(
                installation_routes, "persist_token", persist_after_recovery_attempt
            )
            with app.test_client() as client:
                response = client.post(
                    "/api/installation/login",
                    json={"identifier": identifier, "password": "Initial123"},
                    headers={"Origin": "http://localhost:8080"},
                ).get_json()
            assert response["code"] == 0
            assert future is not None
            future.result(timeout=5)
    finally:
        event.remove(engine, "before_cursor_execute", observe_recovery_write)

    with app.app_context():
        assert UserToken.query.filter_by(user_id=user_bid).count() == 0
        assert (
            UserEntity.query.filter_by(user_bid=user_bid).one().updated_at
            == original_updated_at
        )
        assert (
            token_store.get_and_refresh(
                app,
                token=response["data"]["token"],
                expected_user_id=user_bid,
                ttl_seconds=300,
            )
            is None
        )
        assert _verify(app, identifier, "Recovered123").user.user_id == user_bid


def test_legacy_binding_keeps_login_and_console_recovery_without_new_name_creation(
    app: Flask, local_admin: tuple[str, str]
) -> None:
    user_bid, identifier = local_admin
    legacy = f"old_{uuid.uuid4().hex[:12]}"
    with app.app_context(), unit_of_work():
        binding = LocalAdminAccount.query.filter_by(user_bid=user_bid).one()
        binding.identifier = legacy
        binding.identifier_kind = "legacy_username"
        credential = AuthCredential.query.filter_by(user_bid=user_bid).one()
        credential.identifier = credential.subject_id = legacy
        credential.subject_format = "local_username"
    with app.app_context():
        assert _verify(app, legacy.upper()).user.user_id == user_bid
    local_accounts.reset_local_admin_password(
        app, identifier=legacy, new_password="Recovered123"
    )
    with app.app_context():
        assert _verify(app, legacy, "Recovered123").user.user_id == user_bid
        with pytest.raises(AppError):
            _verify(app, identifier, "Recovered123")
        with pytest.raises(AppError), unit_of_work():
            local_accounts.provision_local_admin_account(
                app, identifier=legacy + "new", password="Initial123"
            )


def test_unverified_login_contact_never_joins_or_replaces_ordinary_contact_identity(
    app: Flask, local_admin: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    user_bid, identifier = local_admin
    ordinary_bid = uuid.uuid4().hex
    with app.app_context(), unit_of_work():
        create_user_entity(user_bid=ordinary_bid, identify=identifier)
        kind = "email" if "@" in identifier else "phone"
        ordinary_credential = AuthCredential(
            credential_bid=uuid.uuid4().hex,
            user_bid=ordinary_bid,
            provider_name=kind,
            subject_id=identifier,
            subject_format=kind,
            identifier=identifier,
            state=CREDENTIAL_STATE_UNVERIFIED,
            deleted=0,
        )
        db.session.add(ordinary_credential)
    try:
        consumed = Mock()
        monkeypatch.setattr(password_flow, "consume_verification_code", consumed)
        with app.app_context():
            assert _verify(app, identifier).user.user_id == user_bid
            assert (
                load_user_aggregate_by_identifier(identifier, providers=[kind]).user_bid
                == ordinary_bid
            )
            password_flow.reset_password(
                app,
                identifier=identifier,
                code="synthetic-code",
                new_password="Ordinary123",
            )
            consumed.assert_called_once()
            assert _verify(app, identifier).user.user_id == user_bid
            with pytest.raises(AppError):
                _verify(app, identifier, "Ordinary123")
            assert load_user_aggregate(ordinary_bid).is_operator is False
            assert (
                load_user_aggregate(user_bid).mobile
                == load_user_aggregate(user_bid).email
                == ""
            )
    finally:
        with app.app_context(), unit_of_work():
            AuthCredential.query.filter_by(user_bid=ordinary_bid).delete()
            UserEntity.query.filter_by(user_bid=ordinary_bid).delete()


def test_contact_without_a_verified_ordinary_account_cannot_reset_local_password(
    app: Flask, local_admin: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    user_bid, identifier = local_admin
    consumed = Mock()
    monkeypatch.setattr(password_flow, "consume_verification_code", consumed)
    with app.app_context():
        with pytest.raises(AppError):
            password_flow.reset_password(
                app,
                identifier=identifier,
                code="synthetic-code",
                new_password="Other123",
            )
        consumed.assert_not_called()
        assert _verify(app, identifier).user.user_id == user_bid
