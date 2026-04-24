from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_METRIC_LLM_CACHE_TOKENS,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    BILLING_METRIC_TTS_OUTPUT_CHARS,
    BILLING_METRIC_TTS_REQUEST_COUNT,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXHAUSTED,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_SOURCE_TYPE_MANUAL,
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
from flaskr.service.billing.charges import build_usage_metric_charges
from flaskr.service.billing.settlement import (
    backfill_bill_usage_settlement,
    replay_bill_usage_settlement,
    settle_bill_usage,
)
from flaskr.service.billing.wallets import persist_credit_wallet_snapshot
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.service.metering.models import BillUsageRecord


@pytest.fixture
def billing_settlement_app():
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


def _create_wallet(creator_bid: str, available_credits: str) -> CreditWallet:
    return CreditWallet(
        wallet_bid=f"wallet-{creator_bid}",
        creator_bid=creator_bid,
        available_credits=Decimal(available_credits),
        reserved_credits=Decimal("0"),
        lifetime_granted_credits=Decimal("100.0000000000"),
        lifetime_consumed_credits=Decimal("0"),
        last_settled_usage_id=0,
        version=0,
    )


def _create_bucket(
    *,
    creator_bid: str,
    wallet_bid: str,
    bucket_bid: str,
    category: int,
    priority: int,
    available_credits: str,
    effective_to: datetime | None = None,
    created_at: datetime | None = None,
) -> CreditWalletBucket:
    bucket_created_at = created_at or datetime(2026, 1, 1, 0, 0, 0)
    return CreditWalletBucket(
        wallet_bucket_bid=bucket_bid,
        wallet_bid=wallet_bid,
        creator_bid=creator_bid,
        bucket_category=category,
        source_type=0,
        source_bid=f"source-{bucket_bid}",
        priority=priority,
        original_credits=Decimal(available_credits),
        available_credits=Decimal(available_credits),
        reserved_credits=Decimal("0"),
        consumed_credits=Decimal("0"),
        expired_credits=Decimal("0"),
        effective_from=datetime(2026, 1, 1, 0, 0, 0),
        effective_to=effective_to,
        status=CREDIT_BUCKET_STATUS_ACTIVE,
        metadata_json={},
        created_at=bucket_created_at,
        updated_at=bucket_created_at,
    )


def _create_active_subscription(creator_bid: str) -> BillingSubscription:
    return BillingSubscription(
        subscription_bid=f"subscription-{creator_bid}",
        creator_bid=creator_bid,
        product_bid="bill-product-plan-monthly",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        billing_provider="manual",
        provider_subscription_id="",
        provider_customer_id="",
        current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
        current_period_end_at=datetime(2026, 5, 1, 0, 0, 0),
        cancel_at_period_end=0,
        next_product_bid="",
        metadata_json={},
    )


def _create_rate(
    *,
    rate_bid: str,
    usage_type: int,
    billing_metric: int,
    credits_per_unit: str,
    provider: str = "*",
    model: str = "*",
    usage_scene: int = BILL_USAGE_SCENE_PROD,
    unit_size: int = 1000,
) -> CreditUsageRate:
    return CreditUsageRate(
        rate_bid=rate_bid,
        usage_type=usage_type,
        provider=provider,
        model=model,
        usage_scene=usage_scene,
        billing_metric=billing_metric,
        unit_size=unit_size,
        credits_per_unit=Decimal(credits_per_unit),
        rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
        effective_from=datetime(2026, 1, 1, 0, 0, 0),
        effective_to=None,
        status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
    )


def _create_usage(
    *,
    usage_bid: str,
    usage_type: int,
    provider: str,
    model: str,
    input_value: int,
    input_cache: int,
    output: int,
    total: int,
    usage_scene: int = BILL_USAGE_SCENE_PROD,
    record_level: int = 0,
    billable: int = 1,
) -> BillUsageRecord:
    return BillUsageRecord(
        usage_bid=usage_bid,
        parent_usage_bid="",
        user_bid="learner-1",
        shifu_bid="shifu-1",
        outline_item_bid="",
        progress_record_bid="",
        generated_block_bid="",
        audio_bid="",
        request_id=f"req-{usage_bid}",
        trace_id=f"trace-{usage_bid}",
        usage_type=usage_type,
        record_level=record_level,
        usage_scene=usage_scene,
        provider=provider,
        model=model,
        is_stream=0,
        input=input_value,
        input_cache=input_cache,
        output=output,
        total=total,
        word_count=output,
        duration_ms=1000,
        latency_ms=100,
        segment_index=0,
        segment_count=0,
        billable=billable,
        status=0,
        error_message="",
        extra={},
        created_at=datetime(2026, 4, 8, 12, 0, 0),
        updated_at=datetime(2026, 4, 8, 12, 0, 0),
    )


def test_settle_llm_usage_consumes_multi_metric_in_bucket_priority_order(
    billing_settlement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-1",
    )

    with billing_settlement_app.app_context():
        wallet = _create_wallet("creator-1", "4.0000000000")
        dao.db.session.add(wallet)
        dao.db.session.add(_create_active_subscription("creator-1"))
        dao.db.session.add_all(
            [
                _create_bucket(
                    creator_bid="creator-1",
                    wallet_bid=wallet.wallet_bid,
                    bucket_bid="bucket-free",
                    category=CREDIT_BUCKET_CATEGORY_FREE,
                    priority=10,
                    available_credits="2.0000000000",
                ),
                _create_bucket(
                    creator_bid="creator-1",
                    wallet_bid=wallet.wallet_bid,
                    bucket_bid="bucket-sub",
                    category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    priority=20,
                    available_credits="1.0000000000",
                ),
                _create_bucket(
                    creator_bid="creator-1",
                    wallet_bid=wallet.wallet_bid,
                    bucket_bid="bucket-topup",
                    category=CREDIT_BUCKET_CATEGORY_TOPUP,
                    priority=30,
                    available_credits="1.0000000000",
                ),
                _create_rate(
                    rate_bid="rate-llm-input",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                    credits_per_unit="1.0000000000",
                ),
                _create_rate(
                    rate_bid="rate-llm-cache",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    billing_metric=BILLING_METRIC_LLM_CACHE_TOKENS,
                    credits_per_unit="1.0000000000",
                ),
                _create_rate(
                    rate_bid="rate-llm-output",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    credits_per_unit="1.0000000000",
                ),
                _create_usage(
                    usage_bid="usage-llm-1",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-test",
                    input_value=1200,
                    input_cache=1000,
                    output=1000,
                    total=3200,
                ),
            ]
        )
        dao.db.session.commit()

        payload = settle_bill_usage(billing_settlement_app, usage_bid="usage-llm-1")

        wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
        entries = (
            CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_type=CREDIT_SOURCE_TYPE_USAGE,
                source_bid="usage-llm-1",
            )
            .order_by(CreditLedgerEntry.id.asc())
            .all()
        )
        buckets = {
            row.wallet_bucket_bid: row
            for row in CreditWalletBucket.query.filter_by(creator_bid="creator-1").all()
        }

        assert payload["status"] == "settled"
        assert payload["entry_count"] == 1
        assert payload["consumed_credits"] == 4
        assert wallet.available_credits == Decimal("0E-10")
        assert wallet.lifetime_consumed_credits == Decimal("4.0000000000")
        assert len(entries) == 1
        assert entries[0].wallet_bucket_bid == ""
        assert entries[0].amount == Decimal("-4.0000000000")
        assert entries[0].balance_after == Decimal("0E-10")
        assert [
            row["billing_metric"]
            for row in entries[0].metadata_json["metric_breakdown"]
        ] == [
            "llm_input_tokens",
            "llm_cache_tokens",
            "llm_output_tokens",
        ]
        assert [
            row["wallet_bucket_bid"]
            for row in entries[0].metadata_json["bucket_breakdown"]
        ] == [
            "bucket-free",
            "bucket-sub",
            "bucket-topup",
        ]
        assert buckets["bucket-free"].status == CREDIT_BUCKET_STATUS_EXHAUSTED
        assert buckets["bucket-sub"].status == CREDIT_BUCKET_STATUS_EXHAUSTED
        assert buckets["bucket-topup"].status == CREDIT_BUCKET_STATUS_EXHAUSTED


def test_settle_usage_rounds_consumption_before_persisting(
    billing_settlement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-rounding",
    )
    monkeypatch.setattr(
        "flaskr.service.billing.primitives.get_config",
        lambda key, default=None: 2 if key == "BILL_CREDIT_PRECISION" else default,
    )

    with billing_settlement_app.app_context():
        wallet = _create_wallet("creator-rounding", "1.0000000000")
        dao.db.session.add(wallet)
        dao.db.session.add(_create_active_subscription("creator-rounding"))
        dao.db.session.add(
            _create_bucket(
                creator_bid="creator-rounding",
                wallet_bid=wallet.wallet_bid,
                bucket_bid="bucket-rounding",
                category=CREDIT_BUCKET_CATEGORY_TOPUP,
                priority=30,
                available_credits="1.0000000000",
            )
        )
        dao.db.session.add(
            _create_rate(
                rate_bid="rate-rounding",
                usage_type=BILL_USAGE_TYPE_LLM,
                billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                credits_per_unit="0.1250000000",
                unit_size=1,
            )
        )
        dao.db.session.add(
            _create_usage(
                usage_bid="usage-rounding",
                usage_type=BILL_USAGE_TYPE_LLM,
                provider="openai",
                model="gpt-test",
                input_value=1,
                input_cache=0,
                output=0,
                total=1,
            )
        )
        dao.db.session.commit()

        payload = settle_bill_usage(
            billing_settlement_app,
            usage_bid="usage-rounding",
        )

        wallet = CreditWallet.query.filter_by(creator_bid="creator-rounding").one()
        entry = CreditLedgerEntry.query.filter_by(source_bid="usage-rounding").one()

        assert payload["status"] == "settled"
        assert payload["consumed_credits"] == 0.13
        assert wallet.available_credits == Decimal("0.8700000000")
        assert entry.amount == Decimal("-0.1300000000")
        assert entry.metadata_json["metric_breakdown"][0]["consumed_credits"] == 0.13
        assert entry.metadata_json["bucket_breakdown"][0]["consumed_credits"] == 0.13


def test_settle_usage_writes_zero_amount_bill_when_consumption_quantizes_to_zero(
    billing_settlement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-zero-bill",
    )
    monkeypatch.setattr(
        "flaskr.service.billing.primitives.get_config",
        lambda key, default=None: 2 if key == "BILL_CREDIT_PRECISION" else default,
    )

    with billing_settlement_app.app_context():
        wallet = _create_wallet("creator-zero-bill", "1.0000000000")
        dao.db.session.add(wallet)
        dao.db.session.add(
            _create_bucket(
                creator_bid="creator-zero-bill",
                wallet_bid=wallet.wallet_bid,
                bucket_bid="bucket-zero-bill",
                category=CREDIT_BUCKET_CATEGORY_TOPUP,
                priority=30,
                available_credits="1.0000000000",
            )
        )
        dao.db.session.add(
            _create_rate(
                rate_bid="rate-zero-bill",
                usage_type=BILL_USAGE_TYPE_LLM,
                billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                credits_per_unit="0.0000001000",
                unit_size=1,
            )
        )
        dao.db.session.add(
            _create_usage(
                usage_bid="usage-zero-bill",
                usage_type=BILL_USAGE_TYPE_LLM,
                provider="openai",
                model="gpt-test",
                input_value=1,
                input_cache=0,
                output=0,
                total=1,
            )
        )
        dao.db.session.commit()

        usage = BillUsageRecord.query.filter_by(usage_bid="usage-zero-bill").one()

        first = settle_bill_usage(billing_settlement_app, usage_bid="usage-zero-bill")
        second = settle_bill_usage(billing_settlement_app, usage_bid="usage-zero-bill")

        wallet = CreditWallet.query.filter_by(creator_bid="creator-zero-bill").one()
        entries = CreditLedgerEntry.query.filter_by(source_bid="usage-zero-bill").all()

        assert first["status"] == "settled"
        assert first["entry_count"] == 1
        assert first["consumed_credits"] == 0
        assert second["status"] == "already_settled"
        assert len(entries) == 1
        assert entries[0].amount == Decimal("0")
        assert entries[0].balance_after == Decimal("1.0000000000")
        assert entries[0].metadata_json["metric_breakdown"][0]["consumed_credits"] == 0
        assert entries[0].metadata_json["bucket_breakdown"] == []
        assert wallet.available_credits == Decimal("1.0000000000")
        assert wallet.lifetime_consumed_credits == Decimal("0")
        assert wallet.last_settled_usage_id == int(usage.id or 0)


def test_settle_tts_usage_is_idempotent(
    billing_settlement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-2",
    )

    with billing_settlement_app.app_context():
        wallet = _create_wallet("creator-2", "5.0000000000")
        dao.db.session.add(wallet)
        dao.db.session.add(_create_active_subscription("creator-2"))
        dao.db.session.add(
            _create_bucket(
                creator_bid="creator-2",
                wallet_bid=wallet.wallet_bid,
                bucket_bid="bucket-tts-topup",
                category=CREDIT_BUCKET_CATEGORY_TOPUP,
                priority=30,
                available_credits="5.0000000000",
            )
        )
        dao.db.session.add(
            _create_rate(
                rate_bid="rate-tts-request",
                usage_type=BILL_USAGE_TYPE_TTS,
                billing_metric=BILLING_METRIC_TTS_REQUEST_COUNT,
                credits_per_unit="2.0000000000",
                unit_size=1,
            )
        )
        dao.db.session.add(
            _create_usage(
                usage_bid="usage-tts-1",
                usage_type=BILL_USAGE_TYPE_TTS,
                provider="minimax",
                model="speech-01",
                input_value=20,
                input_cache=0,
                output=20,
                total=20,
            )
        )
        dao.db.session.commit()

        first = settle_bill_usage(billing_settlement_app, usage_bid="usage-tts-1")
        second = settle_bill_usage(billing_settlement_app, usage_bid="usage-tts-1")

        wallet = CreditWallet.query.filter_by(creator_bid="creator-2").one()
        entries = CreditLedgerEntry.query.filter_by(
            creator_bid="creator-2",
            source_bid="usage-tts-1",
        ).all()

        assert first["status"] == "settled"
        assert first["entry_count"] == 1
        assert first["consumed_credits"] == 2
        assert second["status"] == "already_settled"
        assert len(entries) == 1
        assert wallet.available_credits == Decimal("3.0000000000")


def test_settle_tts_usage_supports_char_mode_when_request_rate_missing(
    billing_settlement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-tts-char",
    )

    with billing_settlement_app.app_context():
        wallet = _create_wallet("creator-tts-char", "5.0000000000")
        dao.db.session.add(wallet)
        dao.db.session.add(_create_active_subscription("creator-tts-char"))
        dao.db.session.add(
            _create_bucket(
                creator_bid="creator-tts-char",
                wallet_bid=wallet.wallet_bid,
                bucket_bid="bucket-tts-char",
                category=CREDIT_BUCKET_CATEGORY_TOPUP,
                priority=30,
                available_credits="5.0000000000",
            )
        )
        dao.db.session.add(
            _create_rate(
                rate_bid="rate-tts-output-char",
                usage_type=BILL_USAGE_TYPE_TTS,
                billing_metric=BILLING_METRIC_TTS_OUTPUT_CHARS,
                credits_per_unit="0.5000000000",
                unit_size=100,
            )
        )
        dao.db.session.add(
            _create_usage(
                usage_bid="usage-tts-char",
                usage_type=BILL_USAGE_TYPE_TTS,
                provider="minimax",
                model="speech-01",
                input_value=250,
                input_cache=0,
                output=250,
                total=250,
            )
        )
        dao.db.session.commit()

        payload = settle_bill_usage(billing_settlement_app, usage_bid="usage-tts-char")

        wallet = CreditWallet.query.filter_by(creator_bid="creator-tts-char").one()
        entry = CreditLedgerEntry.query.filter_by(source_bid="usage-tts-char").one()

        assert payload["status"] == "settled"
        assert payload["entry_count"] == 1
        assert payload["consumed_credits"] == 1.5
        assert entry.amount == Decimal("-1.5000000000")
        assert entry.metadata_json["metric_breakdown"][0]["billing_metric"] == (
            "tts_output_chars"
        )
        assert wallet.available_credits == Decimal("3.5000000000")


def test_settle_usage_consumes_manual_grant_without_subscription_and_skips_topup(
    billing_settlement_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-manual-settlement",
    )

    with billing_settlement_app.app_context():
        wallet = _create_wallet("creator-manual-settlement", "5.0000000000")
        dao.db.session.add(wallet)
        dao.db.session.add_all(
            [
                _create_bucket(
                    creator_bid="creator-manual-settlement",
                    wallet_bid=wallet.wallet_bid,
                    bucket_bid="bucket-manual-settlement",
                    category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    priority=20,
                    available_credits="2.0000000000",
                ),
                _create_bucket(
                    creator_bid="creator-manual-settlement",
                    wallet_bid=wallet.wallet_bid,
                    bucket_bid="bucket-topup-settlement",
                    category=CREDIT_BUCKET_CATEGORY_TOPUP,
                    priority=30,
                    available_credits="3.0000000000",
                ),
                _create_rate(
                    rate_bid="rate-manual-settlement",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                    credits_per_unit="2.0000000000",
                ),
                _create_usage(
                    usage_bid="usage-manual-settlement",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-test",
                    input_value=1000,
                    input_cache=0,
                    output=0,
                    total=1000,
                ),
            ]
        )
        manual_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-manual-settlement"
        ).one()
        manual_bucket.source_type = CREDIT_SOURCE_TYPE_MANUAL
        manual_bucket.metadata_json = {"grant_type": "manual_grant"}
        dao.db.session.add(manual_bucket)
        dao.db.session.commit()

        payload = settle_bill_usage(
            billing_settlement_app,
            usage_bid="usage-manual-settlement",
        )

        manual_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-manual-settlement"
        ).one()
        topup_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-topup-settlement"
        ).one()

        assert payload["status"] == "settled"
        assert manual_bucket.available_credits == Decimal("0E-10")
        assert topup_bucket.available_credits == Decimal("3.0000000000")


def test_settle_usage_prefers_exact_rate_over_wildcard(
    billing_settlement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-3",
    )

    with billing_settlement_app.app_context():
        wallet = _create_wallet("creator-3", "3.0000000000")
        dao.db.session.add(wallet)
        dao.db.session.add(
            _create_bucket(
                creator_bid="creator-3",
                wallet_bid=wallet.wallet_bid,
                bucket_bid="bucket-exact",
                category=CREDIT_BUCKET_CATEGORY_FREE,
                priority=10,
                available_credits="3.0000000000",
            )
        )
        dao.db.session.add_all(
            [
                _create_rate(
                    rate_bid="rate-llm-input-wildcard",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                    credits_per_unit="1.0000000000",
                ),
                _create_rate(
                    rate_bid="rate-llm-input-exact",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                    credits_per_unit="2.0000000000",
                    provider="openai",
                    model="gpt-exact",
                ),
                _create_usage(
                    usage_bid="usage-llm-exact",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-exact",
                    input_value=1000,
                    input_cache=0,
                    output=0,
                    total=1000,
                ),
            ]
        )
        dao.db.session.commit()

        payload = settle_bill_usage(billing_settlement_app, usage_bid="usage-llm-exact")

        entry = CreditLedgerEntry.query.filter_by(source_bid="usage-llm-exact").one()
        assert payload["status"] == "settled"
        assert payload["consumed_credits"] == 2
        assert entry.amount == Decimal("-2.0000000000")


@pytest.mark.parametrize(
    ("usage_scene", "expected_credits", "usage_bid"),
    [
        (BILL_USAGE_SCENE_PROD, Decimal("1.0000000000"), "usage-scene-prod"),
        (BILL_USAGE_SCENE_PREVIEW, Decimal("2.0000000000"), "usage-scene-preview"),
        (BILL_USAGE_SCENE_DEBUG, Decimal("3.0000000000"), "usage-scene-debug"),
    ],
)
def test_settle_usage_applies_scene_specific_rate_and_records_scene_metadata(
    billing_settlement_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    usage_scene: int,
    expected_credits: Decimal,
    usage_bid: str,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-scene-settlement",
    )

    with billing_settlement_app.app_context():
        wallet = _create_wallet("creator-scene-settlement", "10.0000000000")
        dao.db.session.add(wallet)
        dao.db.session.add(
            _create_bucket(
                creator_bid="creator-scene-settlement",
                wallet_bid=wallet.wallet_bid,
                bucket_bid=f"bucket-scene-{usage_scene}",
                category=CREDIT_BUCKET_CATEGORY_FREE,
                priority=10,
                available_credits="10.0000000000",
            )
        )
        dao.db.session.add_all(
            [
                _create_rate(
                    rate_bid="rate-scene-prod",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                    usage_scene=BILL_USAGE_SCENE_PROD,
                    credits_per_unit="1.0000000000",
                ),
                _create_rate(
                    rate_bid="rate-scene-preview",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                    usage_scene=BILL_USAGE_SCENE_PREVIEW,
                    credits_per_unit="2.0000000000",
                ),
                _create_rate(
                    rate_bid="rate-scene-debug",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                    usage_scene=BILL_USAGE_SCENE_DEBUG,
                    credits_per_unit="3.0000000000",
                ),
                _create_usage(
                    usage_bid=usage_bid,
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-scene-test",
                    input_value=1000,
                    input_cache=0,
                    output=0,
                    total=1000,
                    usage_scene=usage_scene,
                ),
            ]
        )
        dao.db.session.commit()

        payload = settle_bill_usage(billing_settlement_app, usage_bid=usage_bid)

        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-scene-settlement"
        ).one()
        entry = CreditLedgerEntry.query.filter_by(source_bid=usage_bid).one()

        assert payload["status"] == "settled"
        assert payload["entry_count"] == 1
        assert payload["consumed_credits"] == int(expected_credits)
        assert entry.amount == -expected_credits
        assert entry.balance_after == Decimal("10.0000000000") - expected_credits
        assert entry.metadata_json["usage_scene"] == usage_scene
        assert entry.metadata_json["metric_breakdown"][0]["billing_metric"] == (
            "llm_input_tokens"
        )
        assert wallet.available_credits == Decimal("10.0000000000") - expected_credits


def test_settle_usage_rebuilds_wallet_snapshot_from_bucket_balances(
    billing_settlement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-5",
    )

    with billing_settlement_app.app_context():
        wallet = _create_wallet("creator-5", "999.0000000000")
        dao.db.session.add(wallet)
        dao.db.session.add_all(
            [
                _create_bucket(
                    creator_bid="creator-5",
                    wallet_bid=wallet.wallet_bid,
                    bucket_bid="bucket-free-5",
                    category=CREDIT_BUCKET_CATEGORY_FREE,
                    priority=10,
                    available_credits="1.0000000000",
                ),
                _create_bucket(
                    creator_bid="creator-5",
                    wallet_bid=wallet.wallet_bid,
                    bucket_bid="bucket-topup-5",
                    category=CREDIT_BUCKET_CATEGORY_TOPUP,
                    priority=30,
                    available_credits="2.0000000000",
                ),
                _create_rate(
                    rate_bid="rate-creator-5-input",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                    credits_per_unit="1.0000000000",
                ),
                _create_usage(
                    usage_bid="usage-creator-5",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-test",
                    input_value=1000,
                    input_cache=0,
                    output=0,
                    total=1000,
                ),
            ]
        )
        dao.db.session.commit()

        payload = settle_bill_usage(billing_settlement_app, usage_bid="usage-creator-5")

        wallet = CreditWallet.query.filter_by(creator_bid="creator-5").one()
        entry = CreditLedgerEntry.query.filter_by(source_bid="usage-creator-5").one()
        free_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-free-5"
        ).one()
        topup_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-topup-5"
        ).one()

        assert payload["status"] == "settled"
        assert wallet.available_credits == Decimal("2.0000000000")
        assert entry.balance_after == Decimal("2.0000000000")
        assert free_bucket.status == CREDIT_BUCKET_STATUS_EXHAUSTED
        assert topup_bucket.status == CREDIT_BUCKET_STATUS_ACTIVE


def test_settle_usage_prefers_earliest_expiry_then_oldest_created_in_same_priority(
    billing_settlement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-6",
    )

    with billing_settlement_app.app_context():
        wallet = _create_wallet("creator-6", "4.0000000000")
        dao.db.session.add(wallet)
        dao.db.session.add_all(
            [
                _create_bucket(
                    creator_bid="creator-6",
                    wallet_bid=wallet.wallet_bid,
                    bucket_bid="bucket-free-early",
                    category=CREDIT_BUCKET_CATEGORY_FREE,
                    priority=10,
                    available_credits="1.0000000000",
                    effective_to=datetime(2026, 4, 9, 0, 0, 0),
                    created_at=datetime(2026, 1, 3, 0, 0, 0),
                ),
                _create_bucket(
                    creator_bid="creator-6",
                    wallet_bid=wallet.wallet_bid,
                    bucket_bid="bucket-free-same-old",
                    category=CREDIT_BUCKET_CATEGORY_FREE,
                    priority=10,
                    available_credits="1.0000000000",
                    effective_to=datetime(2026, 4, 10, 0, 0, 0),
                    created_at=datetime(2026, 1, 1, 0, 0, 0),
                ),
                _create_bucket(
                    creator_bid="creator-6",
                    wallet_bid=wallet.wallet_bid,
                    bucket_bid="bucket-free-same-new",
                    category=CREDIT_BUCKET_CATEGORY_FREE,
                    priority=10,
                    available_credits="1.0000000000",
                    effective_to=datetime(2026, 4, 10, 0, 0, 0),
                    created_at=datetime(2026, 1, 2, 0, 0, 0),
                ),
                _create_bucket(
                    creator_bid="creator-6",
                    wallet_bid=wallet.wallet_bid,
                    bucket_bid="bucket-free-never",
                    category=CREDIT_BUCKET_CATEGORY_FREE,
                    priority=10,
                    available_credits="1.0000000000",
                    effective_to=None,
                    created_at=datetime(2026, 1, 4, 0, 0, 0),
                ),
                _create_rate(
                    rate_bid="rate-creator-6-input",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                    credits_per_unit="1.0000000000",
                ),
                _create_usage(
                    usage_bid="usage-creator-6",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-test",
                    input_value=4000,
                    input_cache=0,
                    output=0,
                    total=4000,
                ),
            ]
        )
        dao.db.session.commit()

        payload = settle_bill_usage(billing_settlement_app, usage_bid="usage-creator-6")

        entry = CreditLedgerEntry.query.filter_by(source_bid="usage-creator-6").one()

        assert payload["status"] == "settled"
        assert payload["entry_count"] == 1
        assert entry.wallet_bucket_bid == ""
        assert [
            row["wallet_bucket_bid"] for row in entry.metadata_json["bucket_breakdown"]
        ] == [
            "bucket-free-early",
            "bucket-free-same-old",
            "bucket-free-same-new",
            "bucket-free-never",
        ]


def test_settle_usage_skips_segment_and_non_billable_records(
    billing_settlement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-4",
    )

    with billing_settlement_app.app_context():
        dao.db.session.add_all(
            [
                _create_usage(
                    usage_bid="usage-segment",
                    usage_type=BILL_USAGE_TYPE_TTS,
                    provider="minimax",
                    model="speech-01",
                    input_value=10,
                    input_cache=0,
                    output=10,
                    total=10,
                    record_level=1,
                ),
                _create_usage(
                    usage_bid="usage-non-billable",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-test",
                    input_value=1000,
                    input_cache=0,
                    output=1000,
                    total=2000,
                    billable=0,
                ),
            ]
        )
        dao.db.session.commit()

        segment_payload = settle_bill_usage(
            billing_settlement_app,
            usage_bid="usage-segment",
        )
        non_billable_payload = settle_bill_usage(
            billing_settlement_app,
            usage_bid="usage-non-billable",
        )

        assert segment_payload["status"] == "skipped"
        assert segment_payload["reason"] == "segment_record"
        assert non_billable_payload["status"] == "skipped"
        assert non_billable_payload["reason"] == "non_billable"
        assert CreditLedgerEntry.query.count() == 0


def test_settle_usage_acquires_creator_scoped_lock(
    billing_settlement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _DummyLock:
        def __init__(self) -> None:
            self.acquire_calls: list[bool] = []
            self.release_calls = 0

        def acquire(self, blocking: bool = True, blocking_timeout=None):
            self.acquire_calls.append(bool(blocking))
            return True

        def release(self) -> None:
            self.release_calls += 1

    class _DummyCacheProvider:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []
            self.lock_instance = _DummyLock()

        def lock(self, key: str, timeout=None, blocking_timeout=None):
            self.calls.append(
                {
                    "key": key,
                    "timeout": timeout,
                    "blocking_timeout": blocking_timeout,
                }
            )
            return self.lock_instance

    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-lock-1",
    )
    dummy_cache = _DummyCacheProvider()
    monkeypatch.setattr("flaskr.service.billing.settlement.cache_provider", dummy_cache)
    billing_settlement_app.config["REDIS_KEY_PREFIX"] = "billing-test"

    with billing_settlement_app.app_context():
        wallet = _create_wallet("creator-lock-1", "2.0000000000")
        dao.db.session.add(wallet)
        dao.db.session.add(
            _create_bucket(
                creator_bid="creator-lock-1",
                wallet_bid=wallet.wallet_bid,
                bucket_bid="bucket-lock-1",
                category=CREDIT_BUCKET_CATEGORY_FREE,
                priority=10,
                available_credits="2.0000000000",
            )
        )
        dao.db.session.add(
            _create_rate(
                rate_bid="rate-lock-1",
                usage_type=BILL_USAGE_TYPE_LLM,
                billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                credits_per_unit="1.0000000000",
            )
        )
        dao.db.session.add(
            _create_usage(
                usage_bid="usage-lock-1",
                usage_type=BILL_USAGE_TYPE_LLM,
                provider="openai",
                model="gpt-test",
                input_value=1000,
                input_cache=0,
                output=0,
                total=1000,
            )
        )
        dao.db.session.commit()

        payload = settle_bill_usage(billing_settlement_app, usage_bid="usage-lock-1")

        assert payload["status"] == "settled"
        assert dummy_cache.calls == [
            {
                "key": "billing-test:billing:settle_usage:creator-lock-1",
                "timeout": 60,
                "blocking_timeout": 60,
            }
        ]
        assert dummy_cache.lock_instance.acquire_calls == [True]
        assert dummy_cache.lock_instance.release_calls == 1


def test_settle_usage_releases_creator_lock_on_error(
    billing_settlement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _DummyLock:
        def __init__(self) -> None:
            self.release_calls = 0

        def acquire(self, blocking: bool = True, blocking_timeout=None):
            return True

        def release(self) -> None:
            self.release_calls += 1

    lock = _DummyLock()
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.cache_provider",
        SimpleNamespace(lock=lambda *args, **kwargs: lock),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-lock-err",
    )
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.build_usage_metric_charges",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("lock-test-error")),
    )

    with billing_settlement_app.app_context():
        dao.db.session.add(
            _create_usage(
                usage_bid="usage-lock-error",
                usage_type=BILL_USAGE_TYPE_LLM,
                provider="openai",
                model="gpt-test",
                input_value=1000,
                input_cache=0,
                output=0,
                total=1000,
            )
        )
        dao.db.session.commit()

        with pytest.raises(RuntimeError, match="lock-test-error"):
            settle_bill_usage(billing_settlement_app, usage_bid="usage-lock-error")

        assert lock.release_calls == 1


def test_persist_credit_wallet_snapshot_rejects_stale_version(
    billing_settlement_app: Flask,
) -> None:
    with billing_settlement_app.app_context():
        wallet = _create_wallet("creator-wallet-version", "5.0000000000")
        dao.db.session.add(wallet)
        dao.db.session.commit()

        stale_wallet = CreditWallet.query.filter_by(
            creator_bid="creator-wallet-version"
        ).one()
        CreditWallet.query.filter_by(id=stale_wallet.id).update(
            {
                "version": 1,
                "updated_at": datetime(2026, 4, 8, 12, 30, 0),
            },
            synchronize_session=False,
        )

        with pytest.raises(RuntimeError, match="credit_wallet_version_conflict"):
            persist_credit_wallet_snapshot(
                stale_wallet,
                available_credits=Decimal("4.0000000000"),
                reserved_credits=Decimal("0"),
                updated_at=datetime(2026, 4, 8, 13, 0, 0),
            )

        dao.db.session.rollback()


def test_replay_bill_usage_settlement_keeps_existing_consumption_idempotent(
    billing_settlement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-replay-1",
    )

    with billing_settlement_app.app_context():
        wallet = _create_wallet("creator-replay-1", "3.0000000000")
        dao.db.session.add(wallet)
        dao.db.session.add(
            _create_bucket(
                creator_bid="creator-replay-1",
                wallet_bid=wallet.wallet_bid,
                bucket_bid="bucket-replay-1",
                category=CREDIT_BUCKET_CATEGORY_FREE,
                priority=10,
                available_credits="3.0000000000",
            )
        )
        dao.db.session.add(
            _create_rate(
                rate_bid="rate-replay-1",
                usage_type=BILL_USAGE_TYPE_LLM,
                billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                credits_per_unit="1.0000000000",
            )
        )
        dao.db.session.add(
            _create_usage(
                usage_bid="usage-replay-1",
                usage_type=BILL_USAGE_TYPE_LLM,
                provider="openai",
                model="gpt-test",
                input_value=1000,
                input_cache=0,
                output=0,
                total=1000,
            )
        )
        dao.db.session.commit()

        first = settle_bill_usage(billing_settlement_app, usage_bid="usage-replay-1")
        second = replay_bill_usage_settlement(
            billing_settlement_app,
            creator_bid="creator-replay-1",
            usage_bid="usage-replay-1",
        )

        entries = CreditLedgerEntry.query.filter_by(source_bid="usage-replay-1").all()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-replay-1").one()

        assert first["status"] == "settled"
        assert second["status"] == "already_settled"
        assert second["replay"] is True
        assert len(entries) == 1
        assert wallet.available_credits == Decimal("2.0000000000")


def test_replay_bill_usage_settlement_rejects_creator_mismatch(
    billing_settlement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-replay-real",
    )

    with billing_settlement_app.app_context():
        dao.db.session.add(
            _create_usage(
                usage_bid="usage-replay-mismatch",
                usage_type=BILL_USAGE_TYPE_LLM,
                provider="openai",
                model="gpt-test",
                input_value=1000,
                input_cache=0,
                output=0,
                total=1000,
            )
        )
        dao.db.session.commit()

        payload = replay_bill_usage_settlement(
            billing_settlement_app,
            creator_bid="creator-replay-wrong",
            usage_bid="usage-replay-mismatch",
        )

        assert payload["status"] == "creator_mismatch"
        assert payload["creator_bid"] == "creator-replay-real"
        assert payload["requested_creator_bid"] == "creator-replay-wrong"
        assert payload["replay"] is True


def test_backfill_bill_usage_settlement_replays_one_usage_range_safely(
    billing_settlement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-backfill-1",
    )

    with billing_settlement_app.app_context():
        wallet = _create_wallet("creator-backfill-1", "4.0000000000")
        dao.db.session.add(wallet)
        dao.db.session.add(
            _create_bucket(
                creator_bid="creator-backfill-1",
                wallet_bid=wallet.wallet_bid,
                bucket_bid="bucket-backfill-1",
                category=CREDIT_BUCKET_CATEGORY_FREE,
                priority=10,
                available_credits="4.0000000000",
            )
        )
        dao.db.session.add(
            _create_rate(
                rate_bid="rate-backfill-1",
                usage_type=BILL_USAGE_TYPE_LLM,
                billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                credits_per_unit="1.0000000000",
            )
        )
        dao.db.session.add_all(
            [
                _create_usage(
                    usage_bid="usage-backfill-1",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-test",
                    input_value=1000,
                    input_cache=0,
                    output=0,
                    total=1000,
                ),
                _create_usage(
                    usage_bid="usage-backfill-2",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-test",
                    input_value=1000,
                    input_cache=0,
                    output=0,
                    total=1000,
                ),
            ]
        )
        dao.db.session.commit()

        first = backfill_bill_usage_settlement(
            billing_settlement_app,
            creator_bid="creator-backfill-1",
            usage_id_start=1,
            usage_id_end=1,
        )
        second = backfill_bill_usage_settlement(
            billing_settlement_app,
            creator_bid="creator-backfill-1",
            usage_id_start=1,
            usage_id_end=1,
        )

        wallet = CreditWallet.query.filter_by(creator_bid="creator-backfill-1").one()

        assert first["status"] == "completed"
        assert first["processed_count"] == 1
        assert first["status_counts"] == {"settled": 1}
        assert first["backfill"] is True
        assert second["status_counts"] == {"already_settled": 1}
        assert wallet.available_credits == Decimal("3.0000000000")


def test_build_usage_metric_charges_uses_public_charge_module(
    billing_settlement_app: Flask,
) -> None:
    with billing_settlement_app.app_context():
        dao.db.session.add(
            _create_rate(
                rate_bid="rate-public-charge-1",
                usage_type=BILL_USAGE_TYPE_LLM,
                billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                credits_per_unit="1.0000000000",
            )
        )
        dao.db.session.add(
            _create_usage(
                usage_bid="usage-public-charge-1",
                usage_type=BILL_USAGE_TYPE_LLM,
                provider="openai",
                model="gpt-test",
                input_value=1200,
                input_cache=0,
                output=0,
                total=1200,
            )
        )
        dao.db.session.commit()

        usage = BillUsageRecord.query.filter_by(usage_bid="usage-public-charge-1").one()
        charges = build_usage_metric_charges(
            usage,
            settlement_at=datetime(2026, 4, 8, 12, 0, 0),
        )

        assert len(charges) == 1
        assert charges[0]["billing_metric"] == BILLING_METRIC_LLM_INPUT_TOKENS
        assert charges[0]["raw_amount"] == 1200
