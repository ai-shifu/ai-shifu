from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_INPUT_TOKENS,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    CreditLedgerEntry,
    CreditUsageRate,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.settlement import settle_bill_usage
from flaskr.service.billing.wallets import (
    expire_credit_wallet_buckets,
    grant_refund_return_credits,
    rebuild_credit_wallet_snapshots,
)
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD, BILL_USAGE_TYPE_LLM
from flaskr.service.metering.models import BillUsageRecord


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


def test_usage_split_and_bucket_expiry_keep_wallet_bucket_and_ledger_consistent(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-consistency-1",
    )

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-consistency-1",
            creator_bid="creator-consistency-1",
            available_credits=Decimal("4.5000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("4.5000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        dao.db.session.add_all(
            [
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-consistency-free",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-consistency-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
                    source_type=CREDIT_SOURCE_TYPE_REFUND,
                    source_bid="grant-consistency-free",
                    priority=10,
                    original_credits=Decimal("1.0000000000"),
                    available_credits=Decimal("1.0000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 8, 0, 0, 0),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-consistency-sub",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-consistency-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    source_type=0,
                    source_bid="grant-consistency-sub",
                    priority=20,
                    original_credits=Decimal("1.5000000000"),
                    available_credits=Decimal("1.5000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 8, 0, 0, 0),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-consistency-topup",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-consistency-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
                    source_type=CREDIT_SOURCE_TYPE_TOPUP,
                    source_bid="grant-consistency-topup",
                    priority=30,
                    original_credits=Decimal("2.0000000000"),
                    available_credits=Decimal("2.0000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 8, 0, 0, 0),
                    effective_to=datetime(2026, 4, 9, 0, 0, 0),
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
                CreditUsageRate(
                    rate_bid="rate-consistency-1",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-consistency",
                    usage_scene=BILL_USAGE_SCENE_PROD,
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                    unit_size=1000,
                    credits_per_unit=Decimal("0.5000000000"),
                    rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
                    effective_from=datetime(2026, 4, 8, 0, 0, 0),
                    effective_to=None,
                    status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
                ),
                BillUsageRecord(
                    usage_bid="usage-consistency-1",
                    parent_usage_bid="",
                    user_bid="learner-consistency-1",
                    shifu_bid="shifu-consistency-1",
                    outline_item_bid="",
                    progress_record_bid="",
                    generated_block_bid="",
                    audio_bid="",
                    request_id="req-consistency-1",
                    trace_id="trace-consistency-1",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    record_level=0,
                    usage_scene=BILL_USAGE_SCENE_PROD,
                    provider="openai",
                    model="gpt-consistency",
                    is_stream=0,
                    input=5000,
                    input_cache=0,
                    output=0,
                    total=5000,
                    word_count=0,
                    duration_ms=1000,
                    latency_ms=100,
                    segment_index=0,
                    segment_count=0,
                    billable=1,
                    status=0,
                    error_message="",
                    extra={},
                    created_at=datetime(2026, 4, 8, 12, 0, 0),
                    updated_at=datetime(2026, 4, 8, 12, 0, 0),
                ),
            ]
        )
        dao.db.session.commit()

        settle_payload = settle_bill_usage(
            billing_wallet_lifecycle_app,
            usage_bid="usage-consistency-1",
        )
        expire_payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid="creator-consistency-1",
            expire_before=datetime(2026, 4, 10, 0, 0, 0),
        )

        wallet = CreditWallet.query.filter_by(creator_bid="creator-consistency-1").one()
        buckets = {
            bucket.wallet_bucket_bid: bucket
            for bucket in CreditWalletBucket.query.filter_by(
                creator_bid="creator-consistency-1"
            ).all()
        }
        usage_entries = (
            CreditLedgerEntry.query.filter_by(
                creator_bid="creator-consistency-1",
                source_type=CREDIT_SOURCE_TYPE_USAGE,
                source_bid="usage-consistency-1",
            )
            .order_by(CreditLedgerEntry.id.asc())
            .all()
        )
        expire_entry = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid="bucket-consistency-topup",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        ).one()

        assert settle_payload["status"] == "settled"
        assert settle_payload["entry_count"] == 2
        assert settle_payload["consumed_credits"] == 2.5
        assert [entry.wallet_bucket_bid for entry in usage_entries] == [
            "bucket-consistency-free",
            "bucket-consistency-sub",
        ]
        assert [entry.amount for entry in usage_entries] == [
            Decimal("-1.0000000000"),
            Decimal("-1.5000000000"),
        ]
        assert [entry.balance_after for entry in usage_entries] == [
            Decimal("3.5000000000"),
            Decimal("2.0000000000"),
        ]

        assert expire_payload["status"] == "expired"
        assert expire_payload["bucket_count"] == 1
        assert expire_payload["expired_credits"] == 2
        assert expire_entry.amount == Decimal("-2.0000000000")
        assert expire_entry.balance_after == Decimal("0E-10")

        assert wallet.available_credits == Decimal("0E-10")
        assert wallet.reserved_credits == Decimal("0E-10")
        assert wallet.lifetime_consumed_credits == Decimal("2.5000000000")

        assert buckets["bucket-consistency-free"].available_credits == Decimal("0E-10")
        assert buckets["bucket-consistency-free"].consumed_credits == Decimal(
            "1.0000000000"
        )
        assert buckets["bucket-consistency-sub"].available_credits == Decimal("0E-10")
        assert buckets["bucket-consistency-sub"].consumed_credits == Decimal(
            "1.5000000000"
        )
        assert buckets["bucket-consistency-topup"].available_credits == Decimal("0")
        assert buckets["bucket-consistency-topup"].expired_credits == Decimal(
            "2.0000000000"
        )
        assert (
            buckets["bucket-consistency-topup"].status == CREDIT_BUCKET_STATUS_EXPIRED
        )

        bucket_available_total = sum(
            (bucket.available_credits for bucket in buckets.values()),
            start=Decimal("0"),
        )
        bucket_consumed_total = sum(
            (bucket.consumed_credits for bucket in buckets.values()),
            start=Decimal("0"),
        )
        bucket_expired_total = sum(
            (bucket.expired_credits for bucket in buckets.values()),
            start=Decimal("0"),
        )
        ledger_reduction_total = sum(
            (
                -entry.amount
                for entry in CreditLedgerEntry.query.filter_by(
                    creator_bid="creator-consistency-1"
                ).all()
            ),
            start=Decimal("0"),
        )

        assert bucket_available_total == wallet.available_credits
        assert bucket_consumed_total == Decimal("2.5000000000")
        assert bucket_expired_total == Decimal("2.0000000000")
        assert ledger_reduction_total == Decimal("4.5000000000")
        for bucket in buckets.values():
            assert bucket.original_credits == (
                bucket.available_credits
                + bucket.consumed_credits
                + bucket.expired_credits
            )
