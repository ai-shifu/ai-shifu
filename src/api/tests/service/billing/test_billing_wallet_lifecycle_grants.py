from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import flaskr.dao as dao
import pytest
from flask import Flask
from flaskr.service.billing.consts import (
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.wallets import (
    grant_manual_credit_wallet_balance,
    grant_refund_return_credits,
)
from sqlalchemy.exc import IntegrityError

pytest_plugins = ["tests.service.billing.wallet_lifecycle_app_fixture"]


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


def test_grant_manual_credit_wallet_balance_returns_noop_existing_after_integrity_error(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
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
            "validity_preset": "1d",
        },
    )

    original_commit = dao.db.session.commit
    state = {"raised": False}

    def _commit_once_with_duplicate():
        if not state["raised"]:
            state["raised"] = True
            dao.db.session.rollback()
            dao.db.session.add(existing)
            original_commit()
            raise IntegrityError("duplicate", {}, Exception("duplicate"))
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
