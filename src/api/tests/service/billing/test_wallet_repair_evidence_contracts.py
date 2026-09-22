"""Verify wallet repairs require complete evidence and preserve balances on failure."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.billing import wallets
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
)
from flaskr.service.billing.models import (
    BillingOrder,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.common.models import AppError

from tests.service.billing import wallet_lifecycle_app_fixture as wallet_fixtures
from tests.service.billing.test_billing_wallet_lifecycle_repair import (
    _seed_wrongly_expired_credit_pack_bucket,
)

if TYPE_CHECKING:
    from flask import Flask

billing_wallet_lifecycle_app = wallet_fixtures.billing_wallet_lifecycle_app


def _expired_bucket() -> tuple:
    return _seed_wrongly_expired_credit_pack_bucket(
        creator_bid=uuid4().hex,
        wallet_bid=uuid4().hex,
        bucket_bid=uuid4().hex,
        order_bid=uuid4().hex,
        original=Decimal(10),
        consumed=Decimal(2),
        expired=Decimal(8),
    )


@pytest.mark.parametrize(
    ("missing", "reason"),
    [
        ("order", "billing_order_not_found"),
        ("paid", "billing_order_is_not_paid_topup"),
        ("paid-time", "billing_order_is_not_paid_topup"),
        ("topup", "billing_order_is_not_paid_topup"),
        ("bucket", "credit_pack_bucket_not_found"),
        ("status", "bucket_is_not_expired"),
        ("expired", "bucket_has_no_expired_credits"),
        ("reserved", "bucket_has_reserved_credits"),
        ("available", "bucket_has_available_credits"),
        ("balance", "bucket_balance_shape_mismatch"),
        ("ledger", "matching_expire_ledger_not_found"),
    ],
)
def test_credit_pack_restore_reports_missing_evidence_without_writing(
    missing: str,
    reason: str,
    billing_wallet_lifecycle_app: Flask,
) -> None:
    wallet, bucket = _expired_bucket()
    order = BillingOrder.query.filter_by(bill_order_bid=bucket.source_bid).one()
    if missing == "order":
        order.deleted = 1
    elif missing == "paid":
        order.status = BILLING_ORDER_STATUS_PENDING
    elif missing == "paid-time":
        order.paid_at = None
    elif missing == "topup":
        order.order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_START
    elif missing == "bucket":
        bucket.deleted = 1
    elif missing == "status":
        bucket.status = CREDIT_BUCKET_STATUS_ACTIVE
    elif missing == "expired":
        bucket.expired_credits = 0
    elif missing == "reserved":
        bucket.reserved_credits = 1
    elif missing == "available":
        bucket.available_credits = 1
    elif missing == "balance":
        bucket.original_credits = 99
    else:
        CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid=bucket.wallet_bucket_bid
        ).one().deleted = 1
    db.session.commit()
    before = (
        bucket.available_credits,
        bucket.expired_credits,
        bucket.status,
        wallet.version,
    )
    result = wallets.restore_wrongly_expired_credit_pack_buckets(
        billing_wallet_lifecycle_app,
        bill_order_bids=[order.bill_order_bid, order.bill_order_bid],
        dry_run=False,
    )
    assert result["order_count"] == 1
    assert result["status"] == "manual_review"
    assert result["buckets"][0]["repair_reason"] == reason
    db.session.expire_all()
    assert (
        bucket.available_credits,
        bucket.expired_credits,
        bucket.status,
        wallet.version,
    ) == before
    assert (
        CreditLedgerEntry.query.filter_by(
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT
        ).count()
        == 0
    )


def test_credit_pack_restore_rolls_back_bucket_write_if_wallet_was_deleted(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    wallet, bucket = _expired_bucket()
    wallet.deleted = 1
    db.session.commit()
    with pytest.raises(RuntimeError, match="credit_pack_restore_wallet_missing"):
        wallets.restore_wrongly_expired_credit_pack_buckets(
            billing_wallet_lifecycle_app,
            bill_order_bids=[bucket.source_bid],
            dry_run=False,
        )
    db.session.expire_all()
    assert bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
    assert bucket.available_credits == 0
    assert bucket.expired_credits == 8
    assert (
        CreditLedgerEntry.query.filter_by(
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT
        ).count()
        == 0
    )


@pytest.mark.parametrize("orders", [[], ["", " "]])
def test_credit_pack_restore_never_treats_empty_scope_as_all_orders(
    orders: list, billing_wallet_lifecycle_app: Flask
) -> None:
    result = wallets.restore_wrongly_expired_credit_pack_buckets(
        billing_wallet_lifecycle_app, bill_order_bids=orders, dry_run=False
    )
    assert result["status"] == "noop"
    assert result["order_count"] == 0


@pytest.mark.parametrize(
    ("operation", "creator", "amount", "reference", "status"),
    [
        ("refund", "", 1, "refund-test", "noop"),
        ("refund", "teacher", 1, "", "noop"),
        ("refund", "teacher", 0, "refund-test", "noop"),
        ("manual", "", 1, "grant-test", "noop"),
        ("manual", "teacher", -1, "grant-test", "noop"),
        ("manual", "teacher", 1, "", "error_missing_idempotency"),
        ("adjust", "", 1, "", "noop"),
        ("adjust", "teacher", 0, "", "noop"),
    ],
)
def test_wallet_mutations_require_amount_identity_and_idempotency_before_writes(
    operation: str,
    creator: str,
    amount: int,
    reference: str,
    status: str,
    billing_wallet_lifecycle_app: Flask,
) -> None:
    if operation == "refund":
        result = wallets.grant_refund_return_credits(
            billing_wallet_lifecycle_app,
            creator_bid=creator,
            amount=amount,
            refund_bid=reference,
        )
    elif operation == "manual":
        result = wallets.grant_manual_credit_wallet_balance(
            billing_wallet_lifecycle_app,
            creator_bid=creator,
            amount=amount,
            source_bid=reference,
        )
    else:
        result = wallets.adjust_credit_wallet_balance(
            billing_wallet_lifecycle_app, creator_bid=creator, amount=amount
        )
    assert result.status == status
    assert CreditWallet.query.count() == 0
    assert CreditWalletBucket.query.count() == 0
    assert CreditLedgerEntry.query.count() == 0


def test_debit_exceeding_available_balance_rolls_back_without_partial_consumption(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    creator = uuid4().hex
    wallets.grant_manual_credit_wallet_balance(
        billing_wallet_lifecycle_app,
        creator_bid=creator,
        amount=Decimal(5),
        source_bid=uuid4().hex,
    )
    with pytest.raises(AppError):
        wallets.adjust_credit_wallet_balance(
            billing_wallet_lifecycle_app,
            creator_bid=creator,
            amount=Decimal(-6),
            note="test debit",
        )
    db.session.expire_all()
    assert CreditWallet.query.one().available_credits == Decimal(5)
    assert CreditWalletBucket.query.one().available_credits == Decimal(5)
    assert CreditLedgerEntry.query.count() == 1
