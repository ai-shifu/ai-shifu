"""Verify account-scoped password login protection."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


def _post_password(client: object, identifier: str, password: str) -> dict:
    response = client.post(
        "/api/user/login_password",
        data=json.dumps({"identifier": identifier, "password": password}),
        content_type="application/json",
    )
    assert response.status_code == 200
    return json.loads(response.data)


def _create_phone_password_account(
    app: Flask, client: object, *, phone: str, password: str
) -> str:
    from flaskr.service.user import phone_flow

    with app.app_context():
        token, _created, _context = phone_flow.verify_phone_code(
            app, user_id=None, phone=phone, code="9999"
        )
    response = client.post(
        "/api/user/set_password",
        data=json.dumps(
            {"identifier": phone, "code": "9999", "new_password": password}
        ),
        content_type="application/json",
        headers={"Token": token.token},
    )
    assert json.loads(response.data)["code"] == 0
    return token.userInfo.user_id


def test_tenth_failure_starts_cooldown_and_blocks_correct_password(
    app: Flask, test_client: object, mock_redis_client: object
) -> None:
    phone = "15500007101"
    password = "Correct123"
    _create_phone_password_account(app, test_client, phone=phone, password=password)

    for _attempt in range(9):
        assert _post_password(test_client, phone, "Wrong123")["code"] == 1016

    assert _post_password(test_client, phone, "Wrong123")["code"] == 1039
    assert _post_password(test_client, phone, password)["code"] == 1039

    cooldown_key = next(
        key for key in mock_redis_client._store if key.endswith(":cooldown")
    )
    mock_redis_client._expires[cooldown_key] = time.time() - 1
    assert _post_password(test_client, phone, password)["code"] == 0


def test_success_clears_only_the_account_failure_budget(
    app: Flask, test_client: object
) -> None:
    app.config["PASSWORD_LOGIN_MAX_FAILURES"] = 3
    phone = "15500007102"
    password = "Correct123"
    _create_phone_password_account(app, test_client, phone=phone, password=password)

    assert _post_password(test_client, phone, "Wrong123")["code"] == 1016
    assert _post_password(test_client, phone, password)["code"] == 0
    assert _post_password(test_client, phone, "Wrong123")["code"] == 1016
    assert _post_password(test_client, phone, "Wrong123")["code"] == 1016
    assert _post_password(test_client, phone, "Wrong123")["code"] == 1039


def test_phone_and_email_aliases_share_one_failure_budget(
    app: Flask, test_client: object
) -> None:
    from flaskr.dao.uow import unit_of_work
    from flaskr.service.user.repository import upsert_credential

    app.config["PASSWORD_LOGIN_MAX_FAILURES"] = 3
    phone = "15500007103"
    email = "same-account@example.com"
    password = "Correct123"
    user_bid = _create_phone_password_account(
        app, test_client, phone=phone, password=password
    )
    with app.app_context(), unit_of_work():
        upsert_credential(
            app,
            user_bid=user_bid,
            provider_name="email",
            subject_id=email,
            subject_format="email",
            identifier=email,
            metadata={},
            verified=True,
        )

    assert _post_password(test_client, phone, "Wrong123")["code"] == 1016
    assert _post_password(test_client, email, "Wrong123")["code"] == 1016
    assert _post_password(test_client, phone, "Wrong123")["code"] == 1039
    assert _post_password(test_client, email, password)["code"] == 1039


def test_unknown_and_passwordless_accounts_execute_dummy_bcrypt(
    app: Flask, test_client: object, monkeypatch: object
) -> None:
    from flaskr.service.user import phone_flow
    from flaskr.service.user.auth.providers import password as password_provider

    passwordless_phone = "15500007104"
    with app.app_context():
        phone_flow.verify_phone_code(
            app, user_id=None, phone=passwordless_phone, code="9999"
        )

    hashes: list[str] = []

    def record_hash(_plain_text: str, hashed: str) -> bool:
        hashes.append(hashed)
        return False

    monkeypatch.setattr(password_provider, "verify_password", record_hash)

    unknown = _post_password(test_client, "missing@example.com", "Wrong123")
    passwordless = _post_password(test_client, passwordless_phone, "Wrong123")

    assert unknown["code"] == passwordless["code"] == 1016
    assert hashes == [
        password_provider._DUMMY_PASSWORD_HASH,
        password_provider._DUMMY_PASSWORD_HASH,
    ]


def test_unknown_account_enters_the_same_cooldown_contract(
    app: Flask, test_client: object
) -> None:
    app.config["PASSWORD_LOGIN_MAX_FAILURES"] = 2
    identifier = "still-missing@example.com"

    assert _post_password(test_client, identifier, "Wrong123")["code"] == 1016
    assert _post_password(test_client, identifier, "Wrong123")["code"] == 1039
    assert _post_password(test_client, identifier, "Wrong123")["code"] == 1039


def test_redis_failure_does_not_skip_password_verification(
    app: Flask, test_client: object, monkeypatch: object
) -> None:
    from flaskr.service.user import password_rate_limit

    phone = "15500007105"
    password = "Correct123"
    _create_phone_password_account(app, test_client, phone=phone, password=password)

    class BrokenRedis:
        def lock(self, *_args: object, **_kwargs: object) -> object:
            raise ConnectionError

    monkeypatch.setattr(password_rate_limit, "get_redis_client", BrokenRedis)

    assert _post_password(test_client, phone, "Wrong123")["code"] == 1016
    assert _post_password(test_client, phone, password)["code"] == 0


def test_waiting_for_account_guard_holds_no_database_transaction(
    test_client: object, monkeypatch: object
) -> None:
    from flaskr.dao import db
    from flaskr.service.user.auth.providers import password as password_provider

    real_attempt = password_provider.PasswordLoginAttempt
    transaction_states: list[bool] = []

    class CheckedAttempt:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._delegate = real_attempt(*args, **kwargs)

        def __enter__(self) -> object:
            transaction_states.append(db.session().in_transaction())
            return self._delegate.__enter__()

        def __exit__(self, *args: object) -> None:
            self._delegate.__exit__(*args)

    monkeypatch.setattr(password_provider, "PasswordLoginAttempt", CheckedAttempt)

    assert (
        _post_password(test_client, "missing@example.com", "Wrong123")["code"] == 1016
    )
    assert transaction_states == [False]


def test_lost_account_guard_rejects_an_otherwise_valid_login(
    app: Flask,
    test_client: object,
    monkeypatch: object,
    mock_redis_client: object,
) -> None:
    from flaskr.service.user.auth.providers import password as password_provider

    phone = "15500007106"
    password = "Correct123"
    _create_phone_password_account(app, test_client, phone=phone, password=password)
    app.config["PASSWORD_LOGIN_LOCK_TIMEOUT_SECONDS"] = 1

    original_verify = password_provider.verify_password

    def slow_verify(plain_text: str, password_hash: str) -> bool:
        time.sleep(1.1)
        return original_verify(plain_text, password_hash)

    monkeypatch.setattr(password_provider, "verify_password", slow_verify)

    original_lock = mock_redis_client.lock

    def losing_lock(*args: object, **kwargs: object) -> object:
        acquired_lock = original_lock(*args, **kwargs)
        acquired_lock.extend = lambda *_args, **_kwargs: False
        return acquired_lock

    monkeypatch.setattr(mock_redis_client, "lock", losing_lock)

    assert _post_password(test_client, phone, password)["code"] == 1039


def test_password_limit_keys_do_not_contain_plaintext_identifier(
    test_client: object, mock_redis_client: object, caplog: object
) -> None:
    identifier = "private-person@example.com"

    assert _post_password(test_client, identifier, "Wrong123")["code"] == 1016

    keys = list(mock_redis_client._store) + list(mock_redis_client._locks)
    assert keys
    assert all(identifier not in key for key in keys)
    assert all("Wrong123" not in key for key in keys)
    assert identifier not in caplog.text
    assert "Wrong123" not in caplog.text
