from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    BillingSubscription,
    CreditLedgerEntry,
    CreditUsageRate,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.settlement import settle_bill_usage
from flaskr.service.billing.wallets import (
    expire_credit_wallet_buckets,
)
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD, BILL_USAGE_TYPE_LLM
from flaskr.service.metering.models import BillUsageRecord

pytest_plugins = ["tests.service.billing.wallet_lifecycle_app_fixture"]


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
        expire_entries = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid="bucket-consistency-topup",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        ).all()

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

        assert expire_payload["status"] == "noop"
        assert expire_payload["bucket_count"] == 0
        assert expire_payload["expired_credits"] == 0
        assert expire_entries == []

        assert wallet.available_credits == Decimal("2.0000000000")
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
        assert buckets["bucket-consistency-topup"].available_credits == Decimal(
            "2.0000000000"
        )
        assert buckets["bucket-consistency-topup"].expired_credits == Decimal("0")
        assert buckets["bucket-consistency-topup"].status == CREDIT_BUCKET_STATUS_ACTIVE

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
        assert bucket_expired_total == Decimal("0")
        assert ledger_reduction_total == Decimal("2.5000000000")
        for bucket in buckets.values():
            assert bucket.original_credits == (
                bucket.available_credits
                + bucket.consumed_credits
                + bucket.expired_credits
            )
