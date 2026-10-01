"""Verify billing wallet lifecycle grants behavior."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from flaskr import dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.wallets import (
    deduct_operator_credit_wallet_balance,
    grant_manual_credit_wallet_balance,
    grant_refund_return_credits,
)
from flaskr.service.common.models import AppError
from flaskr.util.datetime import now_utc
from flaskr.util.uuid import generate_id
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from flask import Flask

pytest_plugins = ["tests.service.billing.wallet_lifecycle_app_fixture"]


def test_operator_deduction_uses_paid_credits_before_manual_credits(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        wallet = CreditWallet(
            wallet_bid="wallet-deduction-paid-first",
            creator_bid="creator-deduction-paid-first",
            available_credits=Decimal("1000.75"),
            reserved_credits=0,
            lifetime_granted_credits=Decimal("1000.75"),
            lifetime_consumed_credits=0,
            version=0,
        )
        paid_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-deduction-paid",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-deduction-paid",
            priority=20,
            original_credits=Decimal("600.25"),
            available_credits=Decimal("600.25"),
            reserved_credits=0,
            consumed_credits=0,
            expired_credits=0,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=30),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"payment_provider": "stripe"},
        )
        manual_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-deduction-manual",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_MANUAL,
            source_bid="grant-deduction-manual",
            priority=20,
            original_credits=Decimal("400.50"),
            available_credits=Decimal("400.50"),
            reserved_credits=0,
            consumed_credits=0,
            expired_credits=0,
            effective_from=now - timedelta(days=2),
            effective_to=now + timedelta(days=2),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        dao.db.session.add_all(
            [
                BillingSubscription(
                    subscription_bid="subscription-deduction-paid-first",
                    creator_bid=wallet.creator_bid,
                    product_bid="product-deduction-paid-first",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    current_period_start_at=now - timedelta(days=1),
                    current_period_end_at=now + timedelta(days=30),
                ),
                wallet,
                paid_bucket,
                manual_bucket,
            ]
        )
        dao.db.session.commit()

        result = deduct_operator_credit_wallet_balance(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            amount=Decimal("800.40"),
            request_id="deduction-request-1",
            reason="incorrect_grant",
            operator_user_bid="operator-1",
        )

        assert result.status == "deducted"
        assert paid_bucket.available_credits == 0
        assert manual_bucket.available_credits == Decimal("200.35")
        assert wallet.available_credits == Decimal("200.35")
        entries = (
            CreditLedgerEntry.query.filter_by(
                creator_bid=wallet.creator_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
                source_bid="deduction-request-1",
            )
            .order_by(CreditLedgerEntry.id.asc())
            .all()
        )
        assert [entry.wallet_bucket_bid for entry in entries] == [
            paid_bucket.wallet_bucket_bid,
            manual_bucket.wallet_bucket_bid,
        ]
        assert [entry.amount for entry in entries] == [
            Decimal("-600.25"),
            Decimal("-200.15"),
        ]

        replay = deduct_operator_credit_wallet_balance(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            amount=Decimal("800.40"),
            request_id="deduction-request-1",
            reason="incorrect_grant",
            operator_user_bid="operator-1",
        )
        assert replay.status == "noop_existing"
        assert (
            CreditLedgerEntry.query.filter_by(
                creator_bid=wallet.creator_bid,
                source_bid="deduction-request-1",
            ).count()
            == 2
        )


def test_operator_deduction_rejects_insufficient_paid_and_manual_credits(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        grant_manual_credit_wallet_balance(
            billing_wallet_lifecycle_app,
            creator_bid="creator-deduction-insufficient",
            amount=Decimal("2.50"),
            source_bid="grant-deduction-insufficient",
            effective_from=now_utc() - timedelta(minutes=1),
            effective_to=now_utc() + timedelta(days=1),
            idempotency_key="grant-deduction-insufficient",
        )
        with pytest.raises(AppError):
            deduct_operator_credit_wallet_balance(
                billing_wallet_lifecycle_app,
                creator_bid="creator-deduction-insufficient",
                amount=Decimal("2.51"),
                request_id="deduction-request-insufficient",
                reason="incorrect_grant",
            )
        bucket = CreditWalletBucket.query.filter_by(
            creator_bid="creator-deduction-insufficient"
        ).one()
        assert bucket.available_credits == Decimal("2.50")
        assert (
            CreditLedgerEntry.query.filter_by(
                source_bid="deduction-request-insufficient"
            ).count()
            == 0
        )


@pytest.mark.parametrize(
    ("source_type", "bucket_category", "metadata", "with_subscription"),
    [
        (
            CREDIT_SOURCE_TYPE_MANUAL,
            CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            {"grant_source": "reward", "grant_type": "manual_grant"},
            False,
        ),
        (
            CREDIT_SOURCE_TYPE_MANUAL,
            CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            {"grant_type": "referral_reward"},
            False,
        ),
        (
            CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            {"refund_return": True},
            True,
        ),
        (
            CREDIT_SOURCE_TYPE_TOPUP,
            CREDIT_BUCKET_CATEGORY_TOPUP,
            {"refund_return": True},
            True,
        ),
    ],
)
def test_operator_deduction_excludes_reward_and_refund_return_buckets(
    billing_wallet_lifecycle_app: Flask,
    source_type: int,
    bucket_category: int,
    metadata: dict[str, object],
    with_subscription: bool,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        creator_bid = f"creator-excluded-{source_type}-{bucket_category}-{metadata}"
        wallet = CreditWallet(
            wallet_bid=generate_id(billing_wallet_lifecycle_app),
            creator_bid=creator_bid,
            available_credits=Decimal(5),
            reserved_credits=0,
            lifetime_granted_credits=Decimal(5),
            lifetime_consumed_credits=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid=generate_id(billing_wallet_lifecycle_app),
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=bucket_category,
            source_type=source_type,
            source_bid=generate_id(billing_wallet_lifecycle_app),
            priority=20,
            original_credits=Decimal(5),
            available_credits=Decimal(5),
            reserved_credits=0,
            consumed_credits=0,
            expired_credits=0,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=30),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json=metadata,
        )
        rows: list[object] = [wallet, bucket]
        if with_subscription:
            rows.append(
                BillingSubscription(
                    subscription_bid=generate_id(billing_wallet_lifecycle_app),
                    creator_bid=creator_bid,
                    product_bid=generate_id(billing_wallet_lifecycle_app),
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    current_period_start_at=now - timedelta(days=1),
                    current_period_end_at=now + timedelta(days=30),
                )
            )
        dao.db.session.add_all(rows)
        dao.db.session.commit()

        with pytest.raises(AppError):
            deduct_operator_credit_wallet_balance(
                billing_wallet_lifecycle_app,
                creator_bid=creator_bid,
                amount=Decimal(1),
                request_id=generate_id(billing_wallet_lifecycle_app),
                reason="account_correction",
            )
        assert bucket.available_credits == Decimal(5)


def test_operator_deduction_excludes_paid_bucket_without_active_subscription(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        wallet = CreditWallet(
            wallet_bid="wallet-deduction-inactive-subscription",
            creator_bid="creator-deduction-inactive-subscription",
            available_credits=0,
            reserved_credits=0,
            lifetime_granted_credits=Decimal(5),
            lifetime_consumed_credits=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-deduction-inactive-subscription",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-deduction-inactive-subscription",
            priority=30,
            original_credits=Decimal(5),
            available_credits=Decimal(5),
            reserved_credits=0,
            consumed_credits=0,
            expired_credits=0,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=30),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        dao.db.session.add_all([wallet, bucket])
        dao.db.session.commit()

        with pytest.raises(AppError):
            deduct_operator_credit_wallet_balance(
                billing_wallet_lifecycle_app,
                creator_bid=wallet.creator_bid,
                amount=Decimal(1),
                request_id="deduction-inactive-subscription",
                reason="account_correction",
            )
        assert bucket.available_credits == Decimal(5)


def test_operator_deduction_rejects_mixed_origin_package_bucket(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        now = now_utc()
        wallet = CreditWallet(
            wallet_bid="wallet-deduction-mixed-origin",
            creator_bid="creator-deduction-mixed-origin",
            available_credits=Decimal(60),
            reserved_credits=0,
            lifetime_granted_credits=Decimal(60),
            lifetime_consumed_credits=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-deduction-mixed-origin",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-deduction-mixed-manual",
            priority=20,
            original_credits=Decimal(60),
            available_credits=Decimal(60),
            reserved_credits=0,
            consumed_credits=0,
            expired_credits=0,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=30),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"payment_provider": "manual"},
        )
        dao.db.session.add_all(
            [
                wallet,
                bucket,
                BillingSubscription(
                    subscription_bid="subscription-deduction-mixed-origin",
                    creator_bid=wallet.creator_bid,
                    product_bid="product-deduction-mixed-origin",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    current_period_start_at=now - timedelta(days=1),
                    current_period_end_at=now + timedelta(days=30),
                ),
                CreditLedgerEntry(
                    ledger_bid="ledger-deduction-mixed-paid",
                    creator_bid=wallet.creator_bid,
                    wallet_bid=wallet.wallet_bid,
                    wallet_bucket_bid=bucket.wallet_bucket_bid,
                    entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    source_bid="order-deduction-mixed-paid",
                    idempotency_key="grant-deduction-mixed-paid",
                    amount=Decimal(10),
                    balance_after=Decimal(10),
                    metadata_json={"payment_provider": "stripe"},
                ),
                CreditLedgerEntry(
                    ledger_bid="ledger-deduction-mixed-manual",
                    creator_bid=wallet.creator_bid,
                    wallet_bid=wallet.wallet_bid,
                    wallet_bucket_bid=bucket.wallet_bucket_bid,
                    entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    source_bid="order-deduction-mixed-manual",
                    idempotency_key="grant-deduction-mixed-manual",
                    amount=Decimal(50),
                    balance_after=Decimal(60),
                    metadata_json={"payment_provider": "manual"},
                ),
            ]
        )
        dao.db.session.commit()

        with pytest.raises(AppError):
            deduct_operator_credit_wallet_balance(
                billing_wallet_lifecycle_app,
                creator_bid=wallet.creator_bid,
                amount=Decimal(1),
                request_id="deduction-mixed-origin",
                reason="account_correction",
            )
        assert bucket.available_credits == Decimal(60)


def test_grant_refund_return_credits_creates_subscription_bucket_and_refund_ledger(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="subscription-refund-return-1",
                creator_bid="creator-refund-return-1",
                product_bid="bill-product-refund-return",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                current_period_start_at=datetime(2026, 4, 8, 0, 0, 0),
                current_period_end_at=datetime(2026, 5, 8, 0, 0, 0),
            )
        )
        dao.db.session.commit()

        payload = grant_refund_return_credits(
            billing_wallet_lifecycle_app,
            creator_bid="creator-refund-return-1",
            amount=Decimal("1.2500000000"),
            refund_bid="refund-return-1",
            metadata={"reason": "usage_reversal"},
            effective_from=datetime(2026, 4, 8, 12, 0, 0),
        )

        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-refund-return-1"
        ).one()
        bucket = CreditWalletBucket.query.filter_by(source_bid="refund-return-1").one()
        ledger = CreditLedgerEntry.query.filter_by(source_bid="refund-return-1").one()

        assert payload["status"] == "granted"
        assert bucket.bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
        assert bucket.source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION
        assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
        assert bucket.available_credits == Decimal("1.2500000000")
        assert bucket.metadata_json["refund_return"] is True
        assert ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_REFUND
        assert ledger.wallet_bucket_bid == bucket.wallet_bucket_bid
        assert ledger.amount == Decimal("1.2500000000")
        assert ledger.balance_after == Decimal("1.2500000000")
        assert wallet.available_credits == Decimal("1.2500000000")

        second = grant_refund_return_credits(
            billing_wallet_lifecycle_app,
            creator_bid="creator-refund-return-1",
            amount=Decimal("1.2500000000"),
            refund_bid="refund-return-1",
        )
        assert second["status"] == "already_granted"
        assert (
            CreditLedgerEntry.query.filter_by(source_bid="refund-return-1").count() == 1
        )


def test_grant_manual_credit_wallet_balance_returns_existing_ledger_payload(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        first = grant_manual_credit_wallet_balance(
            billing_wallet_lifecycle_app,
            creator_bid="creator-manual-idempotent-1",
            amount=Decimal("2.5000000000"),
            source_bid="grant-manual-idempotent-1",
            effective_from=datetime(2026, 4, 8, 12, 0, 0),
            effective_to=datetime(2026, 4, 9, 12, 0, 0),
            idempotency_key="manual-grant-idempotent-1",
            metadata={
                "grant_source": "reward",
                "validity_preset": "1d",
            },
        )
        second = grant_manual_credit_wallet_balance(
            billing_wallet_lifecycle_app,
            creator_bid="creator-manual-idempotent-1",
            amount=Decimal("9.9000000000"),
            source_bid="grant-manual-idempotent-2",
            effective_from=datetime(2026, 4, 8, 13, 0, 0),
            effective_to=datetime(2026, 4, 15, 12, 0, 0),
            idempotency_key="manual-grant-idempotent-1",
            metadata={
                "grant_source": "compensation",
                "validity_preset": "7d",
            },
        )

        ledger = CreditLedgerEntry.query.filter_by(
            creator_bid="creator-manual-idempotent-1",
            idempotency_key="manual-grant-idempotent-1",
        ).one()

        assert first["status"] == "granted"
        assert second["status"] == "noop_existing"
        assert second["ledger_bid"] == first["ledger_bid"]
        assert second["amount"] == 2.5
        assert second["expires_at"] == datetime(2026, 4, 9, 12, 0, 0)
        assert second["metadata_json"]["grant_source"] == "reward"
        assert second["metadata_json"]["validity_preset"] == "1d"
        assert ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT


@pytest.mark.parametrize(
    "validity",
    [
        {"validity_preset": "1d"},
        {"validity_preset": "custom", "validity_value": 6, "validity_unit": "month"},
    ],
)
def test_grant_manual_credit_wallet_balance_returns_noop_existing_after_integrity_error(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    validity: dict[str, object],
) -> None:
    existing = CreditLedgerEntry(
        ledger_bid="ledger-existing-manual-grant",
        creator_bid="creator-manual-race-1",
        wallet_bid="wallet-existing-manual-grant",
        wallet_bucket_bid="bucket-existing-manual-grant",
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        source_bid="grant-existing-manual-grant",
        idempotency_key="manual-grant-race-1",
        amount=Decimal("3.0000000000"),
        balance_after=Decimal("3.0000000000"),
        expires_at=datetime(2026, 4, 9, 12, 0, 0),
        consumable_from=datetime(2026, 4, 8, 12, 0, 0),
        metadata_json={
            "grant_source": "reward",
            **validity,
        },
    )

    original_commit = dao.db.session.commit
    state = {"raised": False}

    def _commit_once_with_duplicate() -> object:
        if not state["raised"]:
            state["raised"] = True
            dao.db.session.rollback()
            dao.db.session.add(existing)
            original_commit()
            message = "duplicate"
            raise IntegrityError(message, {}, Exception("duplicate"))
        return original_commit()

    monkeypatch.setattr(dao.db.session, "commit", _commit_once_with_duplicate)

    with billing_wallet_lifecycle_app.app_context():
        result = grant_manual_credit_wallet_balance(
            billing_wallet_lifecycle_app,
            creator_bid="creator-manual-race-1",
            amount=Decimal("4.0000000000"),
            source_bid="grant-manual-race-1",
            effective_from=datetime(2026, 4, 8, 12, 0, 0),
            effective_to=datetime(2026, 4, 9, 12, 0, 0),
            idempotency_key="manual-grant-race-1",
            metadata={
                "grant_source": "compensation",
                "validity_preset": "7d",
            },
        )

    assert result["status"] == "noop_existing"
    assert result["ledger_bid"] == "ledger-existing-manual-grant"
    assert result["amount"] == 3
    assert result["metadata_json"]["grant_source"] == "reward"

    for key, value in validity.items():
        assert result["metadata_json"][key] == value


def test_grant_refund_return_credits_maps_topup_orders_back_to_topup_bucket(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        dao.db.session.add(
            BillingOrder(
                bill_order_bid="order-topup-refund-1",
                creator_bid="creator-topup-refund-1",
                order_type=BILLING_ORDER_TYPE_TOPUP,
                product_bid="bill-product-topup-small",
            )
        )
        dao.db.session.commit()

        payload = grant_refund_return_credits(
            billing_wallet_lifecycle_app,
            creator_bid="creator-topup-refund-1",
            amount=Decimal("2.0000000000"),
            refund_bid="refund-topup-refund-1",
            metadata={"bill_order_bid": "order-topup-refund-1"},
        )

        bucket = CreditWalletBucket.query.filter_by(
            source_bid="refund-topup-refund-1"
        ).one()

        assert payload["status"] == "granted"
        assert bucket.bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP
