from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from flaskr.service.billing.models import (
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.wallets import (
    expire_credit_wallet_buckets,
    grant_refund_return_credits,
    rebuild_credit_wallet_snapshots,
)


@pytest.fixture
def billing_wallet_lifecycle_app():
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def test_expire_credit_wallet_buckets_marks_bucket_expired_and_writes_ledger(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-1",
            creator_bid="creator-expire-1",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        dao.db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid="bucket-expire-1",
                wallet_bid=wallet.wallet_bid,
                creator_bid="creator-expire-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
                source_type=CREDIT_SOURCE_TYPE_TOPUP,
                source_bid="order-topup-expire-1",
                priority=30,
                original_credits=Decimal("2.5000000000"),
                available_credits=Decimal("2.5000000000"),
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("0"),
                expired_credits=Decimal("0"),
                effective_from=datetime(2026, 4, 1, 0, 0, 0),
                effective_to=datetime(2026, 4, 7, 0, 0, 0),
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={},
                created_at=datetime(2026, 4, 1, 0, 0, 0),
                updated_at=datetime(2026, 4, 1, 0, 0, 0),
            )
        )
        dao.db.session.commit()

        payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid="creator-expire-1",
            expire_before=datetime(2026, 4, 8, 0, 0, 0),
        )

        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-1"
        ).one()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-expire-1").one()
        ledger = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid="bucket-expire-1"
        ).one()

        assert payload["status"] == "expired"
        assert payload["bucket_count"] == 1
        assert payload["expired_credits"] == 2.5
        assert bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
        assert bucket.available_credits == Decimal("0")
        assert bucket.expired_credits == Decimal("2.5000000000")
        assert wallet.available_credits == Decimal("0E-10")
        assert ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_EXPIRE
        assert ledger.amount == Decimal("-2.5000000000")
        assert ledger.balance_after == Decimal("0E-10")


def test_grant_refund_return_credits_creates_free_bucket_and_refund_ledger(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
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
        assert bucket.bucket_category == CREDIT_BUCKET_CATEGORY_FREE
        assert bucket.source_type == CREDIT_SOURCE_TYPE_REFUND
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


def test_rebuild_credit_wallet_snapshots_recomputes_from_bucket_rows(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-rebuild-1",
            creator_bid="creator-rebuild-1",
            available_credits=Decimal("999.0000000000"),
            reserved_credits=Decimal("999.0000000000"),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        dao.db.session.add_all(
            [
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-rebuild-1a",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-rebuild-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
                    source_type=CREDIT_SOURCE_TYPE_REFUND,
                    source_bid="refund-rebuild-1",
                    priority=10,
                    original_credits=Decimal("2.0000000000"),
                    available_credits=Decimal("1.5000000000"),
                    reserved_credits=Decimal("0.2500000000"),
                    consumed_credits=Decimal("0.5000000000"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 8, 0, 0, 0),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-rebuild-1b",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-rebuild-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
                    source_type=CREDIT_SOURCE_TYPE_TOPUP,
                    source_bid="topup-rebuild-1",
                    priority=30,
                    original_credits=Decimal("3.0000000000"),
                    available_credits=Decimal("2.0000000000"),
                    reserved_credits=Decimal("0.5000000000"),
                    consumed_credits=Decimal("1.0000000000"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 8, 0, 0, 0),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
            ]
        )
        dao.db.session.commit()

        payload = rebuild_credit_wallet_snapshots(
            billing_wallet_lifecycle_app,
            creator_bid="creator-rebuild-1",
        )

        wallet = CreditWallet.query.filter_by(creator_bid="creator-rebuild-1").one()

        assert payload["status"] == "rebuilt"
        assert payload["wallet_count"] == 1
        assert payload["wallets"][0]["available_credits"] == 3.5
        assert payload["wallets"][0]["reserved_credits"] == 0.75
        assert wallet.available_credits == Decimal("3.5000000000")
        assert wallet.reserved_credits == Decimal("0.7500000000")
        assert wallet.version == 1
