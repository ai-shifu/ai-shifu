"""Compatibility of custom manual durations with the existing wallet lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
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
from flaskr.service.shifu.admin_dtos_users import (
    AdminOperationUserCreditGrantRequestDTO,
)
from pydantic import ValidationError

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


@pytest.mark.parametrize(
    ("preset", "value", "unit"),
    [
        ("1d", 1, "day"),
        ("7d", 7, "day"),
        ("1m", 1, "month"),
        ("3m", 3, "month"),
        ("1y", 1, "year"),
    ],
)
def test_custom_grant_is_equivalent_to_legacy_through_consumption_and_expiry(
    billing_wallet_lifecycle_app: object,
    frozen_grants: Mock,
    monkeypatch: pytest.MonkeyPatch,
    preset: str,
    value: object,
    unit: str,
) -> None:
    app = billing_wallet_lifecycle_app
    legacy = _grant(app, creator="legacy", request_id="legacy", validity_preset=preset)
    custom = _grant(
        app,
        creator="custom",
        request_id="custom",
        validity_preset="custom",
        validity_value=value,
        validity_unit=unit,
    )
    assert frozen_grants.call_count == 2
    assert custom.expires_at == legacy.expires_at
    assert legacy.validity_value is None
    assert legacy.validity_unit is None
    with app.app_context():
        old = CreditWalletBucket.query.filter_by(creator_bid="legacy").one()
        new = CreditWalletBucket.query.filter_by(creator_bid="custom").one()
        for field in (
            "bucket_category",
            "source_type",
            "priority",
            "original_credits",
            "available_credits",
            "effective_from",
            "effective_to",
            "status",
        ):
            assert getattr(old, field) == getattr(new, field)
    monkeypatch.setattr(
        operation_credits, "now_utc", lambda: custom.expires_at - timedelta(seconds=1)
    )
    for creator in ("legacy", "custom"):
        hold = operation_credits.reserve_operation_credits(
            app,
            creator_bid=creator,
            amount=Decimal(3),
            operation_type="test",
            operation_bid=f"consume-{creator}",
        )
        operation_credits.capture_reserved_operation_credits(
            app,
            reservation_bid=hold.reservation_bid,
            usage_bid=f"usage-{creator}",
        )
        with app.app_context():
            bucket = CreditWalletBucket.query.filter_by(creator_bid=creator).one()
            assert bucket.available_credits == Decimal(7)
            assert bucket.consumed_credits == Decimal(3)
    # Exact end boundary is excluded even before the expiry sweep runs.
    for offset in (0, 1):
        monkeypatch.setattr(
            operation_credits,
            "now_utc",
            lambda offset=offset: custom.expires_at + timedelta(seconds=offset),
        )
        for creator in ("legacy", "custom"):
            with pytest.raises(AppError):
                operation_credits.reserve_operation_credits(
                    app,
                    creator_bid=creator,
                    amount=Decimal(1),
                    operation_type="test",
                    operation_bid=f"expired-{creator}-{offset}",
                )
    for creator in ("legacy", "custom"):
        wallets.expire_credit_wallet_buckets(
            app, creator_bid=creator, expire_before=custom.expires_at
        )
        with app.app_context():
            bucket = CreditWalletBucket.query.filter_by(creator_bid=creator).one()
            assert bucket.available_credits == 0
            assert bucket.expired_credits == Decimal(7)
            assert (
                CreditWallet.query.filter_by(creator_bid=creator)
                .one()
                .available_credits
                == 0
            )


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
def test_custom_duration_persists_bucket_ledger_and_metadata(
    billing_wallet_lifecycle_app: object,
    frozen_grants: Mock,
    monkeypatch: pytest.MonkeyPatch,
    start: datetime,
    value: object,
    unit: str,
    expected: datetime,
) -> None:
    monkeypatch.setattr(grants, "now_utc", lambda: start)
    result = _grant(
        billing_wallet_lifecycle_app,
        validity_preset="custom",
        validity_value=value,
        validity_unit=unit,
    )
    assert result.expires_at == expected
    assert result.validity_value == value
    assert result.validity_unit == unit
    with billing_wallet_lifecycle_app.app_context():
        bucket = CreditWalletBucket.query.one()
        ledger = CreditLedgerEntry.query.one()
        assert bucket.effective_from == ledger.consumable_from == start
        assert bucket.effective_to == ledger.expires_at == expected
        assert (
            bucket.metadata_json["validity_value"]
            == ledger.metadata_json["validity_value"]
            == value
        )
        assert ledger.metadata_json["validity_unit"] == unit
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
def test_invalid_custom_duration_does_not_write_or_notify(
    billing_wallet_lifecycle_app: object, frozen_grants: Mock, value: object, unit: str
) -> None:
    with pytest.raises(AppError):
        _grant(
            billing_wallet_lifecycle_app,
            validity_preset="custom",
            validity_value=value,
            validity_unit=unit,
        )
    with billing_wallet_lifecycle_app.app_context():
        assert CreditWalletBucket.query.count() == CreditLedgerEntry.query.count() == 0
    frozen_grants.assert_not_called()


def test_legacy_preset_rejects_custom_fields(
    billing_wallet_lifecycle_app: object, frozen_grants: Mock
) -> None:
    with pytest.raises(AppError):
        _grant(
            billing_wallet_lifecycle_app,
            validity_preset="7d",
            validity_value=15,
            validity_unit="day",
        )
    with billing_wallet_lifecycle_app.app_context():
        assert CreditWalletBucket.query.count() == CreditLedgerEntry.query.count() == 0

    frozen_grants.assert_not_called()


@pytest.mark.parametrize(
    "second",
    [
        {"validity_preset": "custom", "validity_value": 18, "validity_unit": "month"},
        {"validity_preset": "1d"},
    ],
)
def test_retry_returns_persisted_duration_and_does_not_notify_twice(
    billing_wallet_lifecycle_app: object, frozen_grants: Mock, second: object
) -> None:
    first = _grant(
        billing_wallet_lifecycle_app,
        validity_preset="custom",
        validity_value=6,
        validity_unit="month",
    )
    repeated = _grant(billing_wallet_lifecycle_app, **second)
    assert repeated.ledger_bid == first.ledger_bid
    assert repeated.wallet_bucket_bid == first.wallet_bucket_bid
    assert repeated.expires_at == first.expires_at
    assert repeated.validity_preset == "custom"
    assert repeated.validity_value == 6
    assert repeated.validity_unit == "month"
    with billing_wallet_lifecycle_app.app_context():
        assert CreditWalletBucket.query.count() == CreditLedgerEntry.query.count() == 1
    frozen_grants.assert_called_once()


def test_custom_retry_of_legacy_grant_does_not_invent_metadata(
    billing_wallet_lifecycle_app: object, frozen_grants: Mock
) -> None:
    first = _grant(billing_wallet_lifecycle_app, validity_preset="1d")
    repeated = _grant(
        billing_wallet_lifecycle_app,
        validity_preset="custom",
        validity_value=6,
        validity_unit="month",
    )
    assert repeated.validity_value is None
    assert repeated.validity_unit is None
    assert repeated.expires_at == first.expires_at
    assert repeated.validity_preset == "1d"
    frozen_grants.assert_called_once()


@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "6"])
def test_request_dto_does_not_coerce_duration(value: object) -> None:
    with pytest.raises(ValidationError):
        AdminOperationUserCreditGrantRequestDTO(
            request_id="test",
            amount="10",
            grant_source="reward",
            validity_preset="custom",
            validity_value=value,
            validity_unit="month",
        )


@pytest.mark.parametrize("active", [True, False])
def test_align_subscription_retains_existing_rules(
    monkeypatch: pytest.MonkeyPatch, active: bool
) -> None:
    from types import SimpleNamespace

    subscription = (
        SimpleNamespace(current_period_end_at=START + timedelta(days=40))
        if active
        else None
    )
    monkeypatch.setattr(
        grants,
        "load_primary_active_subscription",
        lambda *_args, **_kwargs: subscription,
    )
    if active:
        assert (
            grants._resolve_manual_credit_grant_expiry(
                creator_bid="test",
                validity_preset="align_subscription",
                granted_at=START,
            )
            == subscription.current_period_end_at
        )
    else:
        with pytest.raises(AppError):
            grants._resolve_manual_credit_grant_expiry(
                creator_bid="test",
                validity_preset="align_subscription",
                granted_at=START,
            )
