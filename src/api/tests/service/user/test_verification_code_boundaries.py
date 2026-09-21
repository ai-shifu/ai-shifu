"""Verify challenge cache/database disagreement and retry safety."""

import uuid
from datetime import UTC, timedelta
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import verification_codes as codes
from flaskr.service.user.models import UserVerifyCode
from flaskr.util.datetime import now_utc

from tests.common.fixtures.fake_redis import FakeRedis


@pytest.mark.parametrize("kind", ["email", "sms"])
@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("database_status", ["expired", "invalid"])
def test_cached_challenge_requires_a_current_durable_code(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    cached: bool,
    database_status: str,
) -> None:
    cache = FakeRedis()
    identifier = "person@example.com" if kind == "email" else "13800138000"
    prefix, _ttl = codes._verification_code_settings(app, kind)
    if cached:
        cache.set(prefix + identifier, "2468")
    database = Mock(return_value=database_status)
    monkeypatch.setattr(codes, "_consume_latest_code_from_db", database)
    with app.app_context(), pytest.raises(AppError) as error:
        codes.consume_verification_code(
            app, identifier=identifier, code="2468", kind=kind, cache_provider=cache
        )
    error_prefix = "mail" if kind == "email" else "sms"
    error_suffix = (
        "CheckError" if not cached and database_status == "invalid" else "SendExpired"
    )
    assert error.value.code == ERROR_CODE[f"server.user.{error_prefix}{error_suffix}"]
    database.assert_called_once_with(app, kind=kind, identifier=identifier, code="2468")
    attempts = cache.get(codes._verification_attempt_key(app, kind, identifier))
    assert attempts == (b"1" if error_suffix == "CheckError" else None)


@pytest.mark.parametrize("cached", [False, True])
def test_mixed_case_email_retries_canonical_database_identifier(
    app: object, monkeypatch: pytest.MonkeyPatch, cached: bool
) -> None:
    cache = FakeRedis()
    prefix, _ttl = codes._verification_code_settings(app, "email")
    if cached:
        cache.set(prefix + "person@example.com", "2468")
    database = Mock(side_effect=["expired", "ok"])
    monkeypatch.setattr(codes, "_consume_latest_code_from_db", database)
    with app.app_context():
        codes.consume_verification_code(
            app, identifier="Person@Example.com", code="2468", cache_provider=cache
        )
    assert [call.kwargs["identifier"] for call in database.call_args_list] == [
        "Person@Example.com",
        "person@example.com",
    ]
    assert cache.get(prefix + "person@example.com") is None
    assert (
        int(
            cache.get(
                codes._verification_attempt_key(app, "email", "person@example.com")
            )
        )
        == codes.VERIFICATION_CODE_CONSUMED_MARKER
    )


def test_prefixed_sms_cache_key_can_fall_back_to_canonical_database_record(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = FakeRedis()
    prefix, _ttl = codes._verification_code_settings(app, "sms")
    cache.set(prefix + "+8613800138000", "2468")
    database = Mock(side_effect=["expired", "ok"])
    monkeypatch.setattr(codes, "_consume_latest_code_from_db", database)
    with app.app_context():
        codes.consume_verification_code(
            app, identifier="+8613800138000", code="2468", cache_provider=cache
        )
    assert [call.kwargs["identifier"] for call in database.call_args_list] == [
        "+8613800138000",
        "13800138000",
    ]
    assert cache.get(prefix + "+8613800138000") is None


def test_sms_wrong_codes_exhaust_shared_budget_and_never_claim_database_record(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = FakeRedis()
    prefix, _ttl = codes._verification_code_settings(app, "sms")
    cache.set(prefix + "13800138000", "2468")
    database = Mock()
    monkeypatch.setattr(codes, "_consume_latest_code_from_db", database)
    with app.app_context():
        for _ in range(codes.MAX_VERIFICATION_ATTEMPTS):
            with pytest.raises(AppError) as error:
                codes.consume_verification_code(
                    app, identifier="+8613800138000", code="wrong", cache_provider=cache
                )
            assert error.value.code == ERROR_CODE["server.user.smsCheckError"]
        assert cache.get(prefix + "13800138000") is None
        with pytest.raises(AppError) as expired:
            codes.consume_verification_code(
                app, identifier="13800138000", code="2468", cache_provider=cache
            )
    assert expired.value.code == ERROR_CODE["server.user.smsSendExpired"]
    database.assert_not_called()


@pytest.mark.parametrize("kind", ["email", "sms"])
def test_lock_contention_fails_closed_before_entering_critical_section(
    app: object, kind: str
) -> None:
    cache = FakeRedis()
    identifier = "person@example.com" if kind == "email" else "13800138000"
    lock = cache.lock(f"{codes._verification_attempt_key(app, kind, identifier)}:lock")
    assert lock.acquire()
    entered = False
    with (
        app.app_context(),
        pytest.raises(AppError) as error,
        codes.verification_code_lock(
            app, kind=kind, identifier=identifier, cache_provider=cache
        ),
    ):
        entered = True
    assert entered is False
    error_key = "mailSendExpired" if kind == "email" else "smsSendExpired"
    assert error.value.code == ERROR_CODE[f"server.user.{error_key}"]
    lock.release()


def test_unstopped_lease_renewal_fails_closed_and_releases_lock(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    thread = Mock()
    thread.is_alive.return_value = True
    monkeypatch.setattr(codes.threading, "Thread", Mock(return_value=thread))
    cache = FakeRedis()
    with (
        app.app_context(),
        pytest.raises(AppError),
        codes.verification_code_lock(
            app, kind="sms", identifier="13800138000", cache_provider=cache
        ),
    ):
        pass
    assert cache._locks == {}
    thread.start.assert_called_once()
    thread.join.assert_called_once_with(timeout=1)


@pytest.mark.parametrize(
    ("age_seconds", "code", "expected"),
    [(301, "2468", "expired"), (10, "wrong", "invalid"), (10, "2468", "ok")],
)
@pytest.mark.parametrize("kind", ["email", "sms"])
def test_database_challenge_checks_expiry_and_code_before_consumption(
    app: object, kind: str, age_seconds: int, code: str, expected: str
) -> None:
    identifier = (
        f"{uuid.uuid4().hex}@example.com" if kind == "email" else uuid.uuid4().hex
    )
    with app.app_context():
        record = UserVerifyCode(
            mail=identifier if kind == "email" else "",
            phone=identifier if kind == "sms" else "",
            verify_code="2468",
            verify_code_type=2 if kind == "email" else 1,
            verify_code_send=1,
            verify_code_used=0,
            created=now_utc() - timedelta(seconds=age_seconds),
        )
        db.session.add(record)
        db.session.flush()
        assert (
            codes._consume_latest_code_from_db(
                app, kind=kind, identifier=identifier, code=code
            )
            == expected
        )
        assert record.verify_code_used == (1 if expected == "ok" else 0)
        db.session.rollback()


def test_database_challenge_cannot_be_claimed_after_another_transaction_wins(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        identifier = f"{uuid.uuid4().hex}@example.com"
        record = UserVerifyCode(
            mail=identifier,
            verify_code="2468",
            verify_code_type=2,
            verify_code_send=1,
            verify_code_used=0,
            created=now_utc(),
        )
        db.session.add(record)
        db.session.flush()
        monkeypatch.setattr(type(UserVerifyCode.query), "update", Mock(return_value=0))
        assert (
            codes._consume_latest_code_from_db(
                app, kind="email", identifier=identifier, code="2468"
            )
            == "expired"
        )
        assert record.verify_code_used == 0
        db.session.rollback()


def test_challenge_age_accepts_utc_aware_timestamps_and_rejects_missing_time() -> None:
    assert codes._is_within_seconds(None, seconds=300) is False
    assert codes._is_within_seconds(now_utc().replace(tzinfo=UTC), seconds=300) is True
