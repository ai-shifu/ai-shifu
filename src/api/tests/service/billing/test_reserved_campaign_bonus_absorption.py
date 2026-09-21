"""Verify reserved campaign bonuses are absorbed once and atomically on upgrade."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import subscriptions
from flaskr.service.billing.consts import (
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_GIFT,
)
from flaskr.service.billing.models import (
    BillingOrder,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.util.datetime import now_utc

if TYPE_CHECKING:
    from flask import Flask


def _seed_reserved_bonus(
    *, reserved: int = 10, original: int = 10, grant_amount: int = 10
) -> tuple[BillingOrder, CreditWallet, CreditWalletBucket, CreditLedgerEntry]:
    creator = uuid4().hex
    wallet = CreditWallet(
        wallet_bid=uuid4().hex,
        creator_bid=creator,
        available_credits=0,
        reserved_credits=reserved,
    )
    order = BillingOrder(bill_order_bid=uuid4().hex, creator_bid=creator)
    bucket = CreditWalletBucket(
        wallet_bucket_bid=uuid4().hex,
        creator_bid=creator,
        wallet_bid=wallet.wallet_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_GIFT,
        priority=20,
        effective_from=now_utc(),
        source_bid=order.bill_order_bid,
        original_credits=original,
        available_credits=0,
        reserved_credits=reserved,
        status=CREDIT_BUCKET_STATUS_ACTIVE,
    )
    entry = CreditLedgerEntry(
        ledger_bid=uuid4().hex,
        creator_bid=creator,
        wallet_bid=wallet.wallet_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        source_type=CREDIT_SOURCE_TYPE_GIFT,
        source_bid=order.bill_order_bid,
        idempotency_key=f"grant:campaign_bonus:{order.bill_order_bid}",
        amount=grant_amount,
        balance_after=0,
        metadata_json={
            "bucket_credit_state": "reserved",
            "campaign_bid": "campaign-test",
        },
    )
    db.session.add_all([order, wallet, bucket, entry])
    db.session.commit()
    return order, wallet, bucket, entry


@pytest.mark.parametrize(
    ("reserved", "original", "grant", "remaining"),
    [(10, 10, 10, 0), (6, 6, 10, 0), (20, 20, 10, 10), (0, 0, 10, 0)],
)
def test_absorption_releases_at_most_reserved_balance_and_is_idempotent(
    reserved: int, original: int, grant: int, remaining: int, app: Flask
) -> None:
    with app.app_context():
        order, wallet, bucket, entry = _seed_reserved_bonus(
            reserved=reserved, original=original, grant_amount=grant
        )
        with unit_of_work():
            assert (
                subscriptions._void_reserved_campaign_bonus_grant_for_order(
                    app, order, absorbed_by_bill_order_bid="upgrade-test"
                )
                is True
            )
        db.session.expire_all()
        assert bucket.reserved_credits == Decimal(remaining)
        assert bucket.original_credits == Decimal(remaining)
        assert wallet.reserved_credits == Decimal(remaining)
        assert wallet.available_credits == 0
        assert entry.metadata_json["bucket_credit_state"] == "absorbed"
        assert entry.metadata_json["absorbed_by_bill_order_bid"] == "upgrade-test"
        assert entry.metadata_json["campaign_bid"] == "campaign-test"
        assert entry.metadata_json["absorbed_at"]
        assert entry.amount == Decimal(grant)
        assert entry.balance_after == 0
        first_version = wallet.version
        with unit_of_work():
            assert (
                subscriptions._void_reserved_campaign_bonus_grant_for_order(
                    app, order, absorbed_by_bill_order_bid="upgrade-test"
                )
                is False
            )
        db.session.expire_all()
        assert wallet.version == first_version
        assert bucket.reserved_credits == Decimal(remaining)


@pytest.mark.parametrize("missing", ["entry", "bucket-id", "bucket"])
def test_incomplete_bonus_evidence_does_not_mutate_wallet(
    missing: str, app: Flask
) -> None:
    with app.app_context():
        order, wallet, bucket, entry = _seed_reserved_bonus()
        if missing == "entry":
            entry.deleted = 1
        elif missing == "bucket-id":
            entry.wallet_bucket_bid = ""
        else:
            bucket.deleted = 1
        db.session.commit()
        with unit_of_work():
            assert (
                subscriptions._void_reserved_campaign_bonus_grant_for_order(
                    app, order, absorbed_by_bill_order_bid="upgrade-test"
                )
                is False
            )
        db.session.expire_all()
        assert wallet.reserved_credits == 10
        assert entry.metadata_json["bucket_credit_state"] == "reserved"


def test_wallet_write_failure_rolls_back_bonus_and_ledger_absorption(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject_wallet_write(*_args: object, **_kwargs: object) -> None:
        message = "wallet write failed"
        raise RuntimeError(message)

    monkeypatch.setattr(
        subscriptions, "persist_credit_wallet_snapshot", reject_wallet_write
    )
    with app.app_context():
        order, wallet, bucket, entry = _seed_reserved_bonus()
        with pytest.raises(RuntimeError, match="wallet write failed"), unit_of_work():
            subscriptions._void_reserved_campaign_bonus_grant_for_order(
                app, order, absorbed_by_bill_order_bid="upgrade-test"
            )
        db.session.expire_all()
        assert bucket.reserved_credits == 10
        assert bucket.original_credits == 10
        assert wallet.reserved_credits == 10
        assert entry.metadata_json == {
            "bucket_credit_state": "reserved",
            "campaign_bid": "campaign-test",
        }
