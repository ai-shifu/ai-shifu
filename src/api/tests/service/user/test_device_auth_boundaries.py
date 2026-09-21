"""Exercise device authorization expiry, cache corruption, and lock races."""

import json
from unittest.mock import Mock

import pytest
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import device_auth

from tests.common.fixtures.fake_redis import FakeRedis


@pytest.fixture(autouse=True)
def device_cache(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    cache = FakeRedis()
    monkeypatch.setattr(device_auth, "redis", cache)
    return cache


def _start(app: object) -> dict:
    return device_auth.create_device_authorization(app, device_name="Test machine")


@pytest.mark.parametrize("raw", ["not json", "[]", "null", '"scalar"'])
def test_corrupt_session_is_deleted_and_never_issues_a_token(
    app: object, device_cache: FakeRedis, raw: str
) -> None:
    with app.test_request_context():
        started = _start(app)
        session_key = device_auth._session_key(app, started["device_code"])
        device_cache.set(session_key, raw)
        with pytest.raises(AppError) as error:
            device_auth.poll_device_authorization(
                app, device_code=started["device_code"]
            )
        assert error.value.code == ERROR_CODE["server.user.deviceCodeInvalid"]
        assert device_cache.get(session_key) is None


def test_lookup_removes_pairing_code_when_session_has_expired(
    app: object, device_cache: FakeRedis
) -> None:
    with app.test_request_context():
        started = _start(app)
        device_cache.delete(device_auth._session_key(app, started["device_code"]))
        with pytest.raises(AppError):
            device_auth.get_device_authorization(app, user_code=started["user_code"])
        assert (
            device_cache.get(
                device_auth._user_code_key(
                    app, device_auth.normalize_user_code(started["user_code"])
                )
            )
            is None
        )


@pytest.mark.parametrize("code", ["", "  ", "---"])
def test_empty_pairing_code_is_rejected(app: object, code: str) -> None:
    with app.test_request_context(), pytest.raises(AppError) as error:
        device_auth.get_device_authorization(app, user_code=code)
    assert error.value.code == ERROR_CODE["server.user.deviceCodeInvalid"]


@pytest.mark.parametrize("code", ["", "  ", "unknown-secret"])
def test_poll_rejects_missing_or_unknown_device_code(app: object, code: str) -> None:
    with app.test_request_context(), pytest.raises(AppError) as error:
        device_auth.poll_device_authorization(app, device_code=code)
    assert error.value.code == ERROR_CODE["server.user.deviceCodeInvalid"]


def test_creation_caps_untrusted_metadata_and_honors_expiry_configuration(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(app.config, "DEVICE_AUTH_EXPIRE_TIME", 120)
    monkeypatch.setitem(app.config, "DEVICE_AUTH_POLL_INTERVAL", 7)
    with app.test_request_context():
        started = device_auth.create_device_authorization(
            app,
            device_name="  " + "n" * 100,
            device_os="  Linux  ",
            client_version=None,
        )
        details = device_auth.get_device_authorization(
            app, user_code=started["user_code"]
        )
    assert started["expires_in"] == 120
    assert started["interval"] == 7
    assert details["device_name"] == "n" * 64
    assert details["device_os"] == "Linux"
    assert details["client_version"] == ""
    assert 118 <= details["expires_in"] <= 120
    assert "device_code" not in details
    assert "token" not in details


def test_exhausted_pairing_code_collisions_do_not_overwrite_existing_request(
    app: object, device_cache: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(device_auth.secrets, "choice", lambda _alphabet: "A")
    with app.test_request_context():
        first = _start(app)
        with pytest.raises(AppError):
            _start(app)
        assert (
            device_cache.get(device_auth._user_code_key(app, "AAAAAA"))
            == first["device_code"].encode()
        )
        assert (
            device_auth.get_device_authorization(app, user_code="AAA-AAA")[
                "device_name"
            ]
            == "Test machine"
        )


def test_poll_waits_without_minting_when_another_collector_holds_the_lock(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = Mock()
    lock.acquire.return_value = False
    monkeypatch.setattr(device_auth, "_session_lock", Mock(return_value=lock))
    mint = Mock()
    monkeypatch.setattr(device_auth, "generate_token", mint)
    with app.test_request_context():
        started = _start(app)
        result = device_auth.poll_device_authorization(
            app, device_code=started["device_code"]
        )
    assert result["status"] == device_auth.STATUS_PENDING
    assert result["token"] == ""
    mint.assert_not_called()
    lock.release.assert_not_called()


def test_decision_fails_without_mutation_when_lock_cannot_be_acquired(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = Mock()
    lock.acquire.return_value = False
    monkeypatch.setattr(device_auth, "_session_lock", Mock(return_value=lock))
    with app.test_request_context():
        started = _start(app)
        with pytest.raises(AppError):
            device_auth.deny_device_authorization(app, user_code=started["user_code"])
        payload = device_auth._load_session(app, started["device_code"])
    assert payload["status"] == device_auth.STATUS_PENDING
    lock.release.assert_not_called()


@pytest.mark.parametrize("competing_change", ["delete", "deny", "expire"])
def test_decision_rechecks_state_after_acquiring_lock_and_always_releases_it(
    app: object,
    device_cache: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
    competing_change: str,
) -> None:
    with app.test_request_context():
        started = _start(app)
        key = device_auth._session_key(app, started["device_code"])
        lock = Mock()

        def acquire(**_kwargs: object) -> bool:
            if competing_change == "delete":
                device_cache.delete(key)
            elif competing_change == "deny":
                payload = json.loads(device_cache.get(key))
                payload["status"] = device_auth.STATUS_DENIED
                device_cache.set(key, json.dumps(payload), ex=60)
            else:
                monkeypatch.setattr(device_cache, "ttl", lambda _key: 0)
            return True

        lock.acquire.side_effect = acquire
        monkeypatch.setattr(device_auth, "_session_lock", Mock(return_value=lock))
        with pytest.raises(AppError) as error:
            device_auth.approve_device_authorization(
                app, user_code=started["user_code"], user_id="account"
            )
    expected = (
        "deviceAuthAlreadyHandled"
        if competing_change == "deny"
        else "deviceCodeInvalid"
    )
    assert error.value.code == ERROR_CODE[f"server.user.{expected}"]
    lock.release.assert_called_once()


def test_poll_rechecks_session_after_waiting_for_lock(
    app: object, device_cache: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.test_request_context():
        started = _start(app)
        lock = Mock()

        def acquire(**_kwargs: object) -> bool:
            device_cache.delete(device_auth._session_key(app, started["device_code"]))
            return True

        lock.acquire.side_effect = acquire
        monkeypatch.setattr(device_auth, "_session_lock", Mock(return_value=lock))
        with pytest.raises(AppError):
            device_auth.poll_device_authorization(
                app, device_code=started["device_code"]
            )
    lock.release.assert_called_once()


def test_approved_session_without_an_account_is_consumed_without_a_token(
    app: object, device_cache: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    mint = Mock()
    monkeypatch.setattr(device_auth, "generate_token", mint)
    with app.test_request_context():
        started = _start(app)
        payload = device_auth._load_session(app, started["device_code"])
        payload["status"] = device_auth.STATUS_APPROVED
        device_auth._store_session(app, started["device_code"], payload, 60)
        with pytest.raises(AppError):
            device_auth.poll_device_authorization(
                app, device_code=started["device_code"]
            )
    assert (
        device_cache.get(device_auth._session_key(app, started["device_code"])) is None
    )
    assert (
        device_cache.get(device_auth._user_code_key(app, payload["user_code"])) is None
    )
    mint.assert_not_called()


def test_failed_token_issuance_keeps_approved_request_retryable(
    app: object, device_cache: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    mint = Mock(side_effect=[RuntimeError("issuer unavailable"), "issued-token"])
    monkeypatch.setattr(device_auth, "generate_token", mint)
    with app.test_request_context():
        started = _start(app)
        device_auth.approve_device_authorization(
            app, user_code=started["user_code"], user_id="account"
        )
        with pytest.raises(RuntimeError, match="issuer unavailable"):
            device_auth.poll_device_authorization(
                app, device_code=started["device_code"]
            )
        result = device_auth.poll_device_authorization(
            app, device_code=started["device_code"]
        )
    assert result == {"status": device_auth.STATUS_APPROVED, "token": "issued-token"}
    assert (
        device_cache.get(device_auth._session_key(app, started["device_code"])) is None
    )
