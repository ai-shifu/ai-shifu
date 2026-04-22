from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import Flask
import pytest
from sqlalchemy.exc import IntegrityError

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditUsageRate,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.settlement import settle_bill_usage
from flaskr.service.billing.wallets import (
    expire_credit_wallet_buckets,
    grant_manual_credit_wallet_balance,
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


def test_grant_refund_return_credits_creates_subscription_bucket_and_refund_ledger(
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
                BillingSubscription(
                    subscription_bid="subscription-consistency-1",
                    creator_bid="creator-consistency-1",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    current_period_start_at=datetime(2026, 4, 8, 0, 0, 0),
                    current_period_end_at=datetime(2026, 4, 30, 0, 0, 0),
                ),
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
        assert settle_payload["entry_count"] == 1
        assert settle_payload["consumed_credits"] == 2.5
        assert len(usage_entries) == 1
        assert usage_entries[0].wallet_bucket_bid == ""
        assert usage_entries[0].amount == Decimal("-2.5000000000")
        assert usage_entries[0].balance_after == Decimal("2.0000000000")
        assert [
            item["wallet_bucket_bid"]
            for item in usage_entries[0].metadata_json["bucket_breakdown"]
        ] == [
            "bucket-consistency-free",
            "bucket-consistency-sub",
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
