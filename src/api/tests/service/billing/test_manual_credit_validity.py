"""Verify manual durations and absolute compensation expiries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from functools import partial
from unittest.mock import Mock

import pytest
from flaskr.service.billing import manual_credit_grants as grants
from flaskr.service.billing import operation_credits, wallets
from flaskr.service.billing.models import (
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.common.models import AppError

pytest_plugins = ["tests.service.billing.wallet_lifecycle_app_fixture"]
START = datetime(2026, 1, 31, 12, 34, 56)


@pytest.fixture
def frozen_grants(monkeypatch: pytest.MonkeyPatch) -> Mock:
    monkeypatch.setattr(grants, "now_utc", lambda: START)
    monkeypatch.setattr(wallets, "now_utc", lambda: START)
    notification = Mock(return_value={})
    monkeypatch.setattr(grants, "stage_credit_granted_notification", notification)
    return notification


def _grant(
    app: object,
    *,
    creator: str = "custom-duration",
    request_id: str = "duration-request",
    **validity: object,
) -> object:
    return grants.grant_manual_credits_to_user(
        app,
        user_bid=creator,
        operator_user_bid="operator",
        request_id=request_id,
        amount="10",
        grant_source="reward",
        **validity,
    )


def _grant_with_expiry(app: object, expires_at: object) -> object:
    return grants.grant_manual_credits_with_expiry(
        app,
        user_bid="compensation",
        operator_user_bid="operator",
        request_id="compensation-request",
        amount="10",
        grant_source="compensation",
        expires_at=expires_at,
        grant_channel="cache_overcharge_compensation_script",
    )


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (1, "day", datetime(2026, 2, 1, 12, 34, 56)),
        (7, "day", datetime(2026, 2, 7, 12, 34, 56)),
        (1, "month", datetime(2026, 2, 28, 12, 34, 56)),
        (3, "month", datetime(2026, 4, 30, 12, 34, 56)),
        (1, "year", datetime(2027, 1, 31, 12, 34, 56)),
    ],
)
def test_duration_preserves_consumption_and_exact_expiry_boundary(
    billing_wallet_lifecycle_app: object,
    frozen_grants: Mock,
    monkeypatch: pytest.MonkeyPatch,
    value: int,
    unit: str,
    expected: datetime,
) -> None:
    app = billing_wallet_lifecycle_app
    result = _grant(app, validity_value=value, validity_unit=unit)
    assert result.expires_at == expected
    monkeypatch.setattr(
        operation_credits, "now_utc", lambda: expected - timedelta(seconds=1)
    )
    hold = operation_credits.reserve_operation_credits(
        app,
        creator_bid="custom-duration",
        amount=Decimal(3),
        operation_type="test",
        operation_bid="consume-custom",
    )
    operation_credits.capture_reserved_operation_credits(
        app, reservation_bid=hold.reservation_bid, usage_bid="usage-custom"
    )
    with app.app_context():
        bucket = CreditWalletBucket.query.one()
        assert bucket.available_credits == Decimal(7)
        assert bucket.consumed_credits == Decimal(3)
    # Spending stops exactly at expiry, before a sweep is necessary.
    for offset in (0, 1):
        monkeypatch.setattr(
            operation_credits,
            "now_utc",
            lambda offset=offset: expected + timedelta(seconds=offset),
        )
        with pytest.raises(AppError):
            operation_credits.reserve_operation_credits(
                app,
                creator_bid="custom-duration",
                amount=Decimal(1),
                operation_type="test",
                operation_bid=f"expired-custom-{offset}",
            )
    wallets.expire_credit_wallet_buckets(
        app, creator_bid="custom-duration", expire_before=expected
    )
    with app.app_context():
        bucket = CreditWalletBucket.query.one()
        assert bucket.available_credits == 0
        assert bucket.expired_credits == Decimal(7)
        assert CreditWallet.query.one().available_credits == 0
    frozen_grants.assert_called_once()


@pytest.mark.parametrize(
    ("start", "value", "unit", "expected"),
    [
        (START, 15, "day", datetime(2026, 2, 15, 12, 34, 56)),
        (START, 6, "month", datetime(2026, 7, 31, 12, 34, 56)),
        (START, 18, "month", datetime(2027, 7, 31, 12, 34, 56)),
        (datetime(2024, 2, 29), 1, "year", datetime(2025, 2, 28)),
        (datetime(2026, 8, 31), 6, "month", datetime(2027, 2, 28)),
    ],
)
def test_duration_persists_bucket_ledger_and_metadata(
    billing_wallet_lifecycle_app: object,
    frozen_grants: Mock,
    monkeypatch: pytest.MonkeyPatch,
    start: datetime,
    value: int,
    unit: str,
    expected: datetime,
) -> None:
    monkeypatch.setattr(grants, "now_utc", lambda: start)
    result = _grant(
        billing_wallet_lifecycle_app, validity_value=value, validity_unit=unit
    )
    assert result.expires_at == expected
    assert result.validity_value == value
    assert result.validity_unit == unit
    assert "validity_preset" not in result.to_payload()
    with billing_wallet_lifecycle_app.app_context():
        bucket = CreditWalletBucket.query.one()
        ledger = CreditLedgerEntry.query.one()
        assert bucket.effective_from == ledger.consumable_from == start
        assert bucket.effective_to == ledger.expires_at == expected
        for metadata in (bucket.metadata_json, ledger.metadata_json):
            assert metadata["validity_value"] == value
            assert metadata["validity_unit"] == unit
            assert "validity_preset" not in metadata
    frozen_grants.assert_called_once()


@pytest.mark.parametrize(
    ("value", "unit"),
    [
        (None, "day"),
        (0, "day"),
        (-1, "day"),
        (1.5, "day"),
        (True, "day"),
        ("15", "day"),
        (1, None),
        (1, "week"),
        (10**30, "day"),
        (10**30, "month"),
        (10**30, "year"),
    ],
)
def test_invalid_duration_does_not_write_or_notify(
    billing_wallet_lifecycle_app: object,
    frozen_grants: Mock,
    value: object,
    unit: object,
) -> None:
    with pytest.raises(AppError):
        _grant(billing_wallet_lifecycle_app, validity_value=value, validity_unit=unit)
    with billing_wallet_lifecycle_app.app_context():
        assert CreditWalletBucket.query.count() == CreditLedgerEntry.query.count() == 0
    frozen_grants.assert_not_called()


def test_retry_returns_persisted_duration_and_does_not_notify_twice(
    billing_wallet_lifecycle_app: object, frozen_grants: Mock
) -> None:
    first = _grant(
        billing_wallet_lifecycle_app, validity_value=6, validity_unit="month"
    )
    repeated = _grant(
        billing_wallet_lifecycle_app, validity_value=18, validity_unit="month"
    )
    assert repeated.ledger_bid == first.ledger_bid
    assert repeated.wallet_bucket_bid == first.wallet_bucket_bid
    assert repeated.expires_at == first.expires_at
    assert repeated.validity_value == 6
    assert repeated.validity_unit == "month"
    with billing_wallet_lifecycle_app.app_context():
        assert CreditWalletBucket.query.count() == CreditLedgerEntry.query.count() == 1
    frozen_grants.assert_called_once()


def test_retry_of_historical_grant_preserves_expiry_and_metadata(
    billing_wallet_lifecycle_app: object, frozen_grants: Mock
) -> None:
    first = wallets.grant_manual_credit_wallet_balance(
        billing_wallet_lifecycle_app,
        creator_bid="custom-duration",
        amount=Decimal(10),
        source_bid="historical",
        effective_from=START,
        effective_to=START + timedelta(days=1),
        idempotency_key="operator_manual_grant:duration-request",
        metadata={"grant_source": "reward", "validity_preset": "1d"},
    )
    repeated = _grant(
        billing_wallet_lifecycle_app, validity_value=6, validity_unit="month"
    )
    assert repeated.status == "noop_existing"
    assert repeated.validity_value is None
    assert repeated.validity_unit is None
    assert repeated.expires_at == first.expires_at
    assert repeated.metadata_json == first.metadata_json
    frozen_grants.assert_not_called()


@pytest.mark.parametrize(
    "expires_at",
    [
        datetime(2026, 2, 3, 17, 18, 19, 123456),
        datetime(2026, 2, 3, 17, 18, 19, 123456, tzinfo=UTC),
        datetime(2026, 2, 4, 1, 18, 19, 123456, tzinfo=timezone(timedelta(hours=8))),
    ],
)
def test_absolute_expiry_is_exact_utc_and_idempotent(
    billing_wallet_lifecycle_app: object, frozen_grants: Mock, expires_at: datetime
) -> None:
    expected = datetime(2026, 2, 3, 17, 18, 19, 123456)
    first = _grant_with_expiry(billing_wallet_lifecycle_app, expires_at)
    repeated = _grant_with_expiry(
        billing_wallet_lifecycle_app, expires_at + timedelta(days=10)
    )
    assert first.expires_at == repeated.expires_at == expected
    assert first.ledger_bid == repeated.ledger_bid
    assert first.validity_value is None
    assert first.validity_unit is None
    with billing_wallet_lifecycle_app.app_context():
        bucket = CreditWalletBucket.query.one()
        ledger = CreditLedgerEntry.query.one()
        assert bucket.effective_to == ledger.expires_at == expected
        assert bucket.effective_from == ledger.consumable_from == START
        for metadata in (bucket.metadata_json, ledger.metadata_json):
            assert "validity_preset" not in metadata
            assert "validity_value" not in metadata
            assert "validity_unit" not in metadata
    frozen_grants.assert_called_once()


@pytest.mark.parametrize(
    "expires_at", [None, "2026-03-01T00:00:00Z", START, START - timedelta(seconds=1)]
)
def test_invalid_absolute_expiry_does_not_write_or_notify(
    billing_wallet_lifecycle_app: object, frozen_grants: Mock, expires_at: object
) -> None:
    with pytest.raises(AppError):
        _grant_with_expiry(billing_wallet_lifecycle_app, expires_at)
    with billing_wallet_lifecycle_app.app_context():
        assert CreditWalletBucket.query.count() == CreditLedgerEntry.query.count() == 0
    frozen_grants.assert_not_called()


@pytest.mark.parametrize("absolute", [False, True])
def test_grant_reuses_context_and_notifies_only_after_committed_wallet(
    billing_wallet_lifecycle_app: object,
    frozen_grants: Mock,
    absolute: bool,
) -> None:
    from flaskr import dao

    app = billing_wallet_lifecycle_app
    with app.app_context():
        caller_session = dao.db.session()

        def assert_committed(_app: object, *, ledger_bid: str, **_: object) -> None:
            assert dao.db.session() is caller_session
            with dao.db.engine.connect() as connection:
                rows = connection.execute(
                    CreditLedgerEntry.__table__.select().where(
                        CreditLedgerEntry.ledger_bid == ledger_bid
                    )
                ).fetchall()
            assert len(rows) == 1

        frozen_grants.side_effect = assert_committed
        if absolute:
            _grant_with_expiry(app, START + timedelta(days=1))
        else:
            _grant(app, validity_value=1, validity_unit="day")
    frozen_grants.assert_called_once()


@pytest.mark.parametrize("absolute", [False, True])
def test_grant_wallet_failure_rolls_back_without_notification(
    billing_wallet_lifecycle_app: object,
    frozen_grants: Mock,
    monkeypatch: pytest.MonkeyPatch,
    absolute: bool,
) -> None:
    def fail_snapshot(*_: object, **__: object) -> None:
        message = "snapshot failure"
        raise RuntimeError(message)

    monkeypatch.setattr(wallets, "persist_credit_wallet_snapshot", fail_snapshot)
    app = billing_wallet_lifecycle_app
    grant = (
        partial(_grant_with_expiry, app, START + timedelta(days=1))
        if absolute
        else partial(_grant, app, validity_value=1, validity_unit="day")
    )
    with app.app_context(), pytest.raises(RuntimeError, match="snapshot failure"):
        grant()
    with app.app_context():
        assert CreditWalletBucket.query.count() == CreditLedgerEntry.query.count() == 0
    frozen_grants.assert_not_called()
