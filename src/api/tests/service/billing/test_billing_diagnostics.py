from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    BILLING_METRIC_LABELS,
    BILLING_METRIC_TTS_OUTPUT_CHARS,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.diagnostics import diagnose_tts_consumption
from flaskr.service.billing.models import BillingDailyUsageMetric, CreditLedgerEntry
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.service.metering.models import BillUsageRecord


@pytest.fixture
def billing_diagnostics_app(tmp_path):
    db_path = tmp_path / "billing-diagnostics.sqlite"
    db_uri = f"sqlite:///{db_path}"

    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI=db_uri,
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": db_uri,
            "ai_shifu_admin": db_uri,
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="Asia/Shanghai",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def test_diagnose_tts_consumption_flags_display_layer_issue(
    billing_diagnostics_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.diagnostics.resolve_usage_creator_bid",
        lambda app, usage: "creator-diagnose-1",
    )

    with billing_diagnostics_app.app_context():
        dao.db.session.add_all(
            [
                _create_usage(
                    usage_bid="usage-llm-1",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-4o-mini",
                    created_at=datetime(2026, 4, 20, 13, 3, 0),
                    input_value=120,
                    output_value=24,
                ),
                _create_usage(
                    usage_bid="usage-tts-1",
                    usage_type=BILL_USAGE_TYPE_TTS,
                    provider="minimax",
                    model="speech-2",
                    created_at=datetime(2026, 4, 20, 13, 4, 0),
                    input_value=20,
                    output_value=220,
                ),
                _create_ledger(
                    ledger_bid="ledger-llm-1",
                    usage_bid="usage-llm-1",
                    amount="-0.24",
                    created_at=datetime(2026, 4, 20, 13, 3, 30),
                    billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    provider="openai",
                    model="gpt-4o-mini",
                    raw_amount=24,
                    usage_type=BILL_USAGE_TYPE_LLM,
                ),
                _create_ledger(
                    ledger_bid="ledger-tts-1",
                    usage_bid="usage-tts-1",
                    amount="-0.80",
                    created_at=datetime(2026, 4, 20, 13, 4, 20),
                    billing_metric=BILLING_METRIC_TTS_OUTPUT_CHARS,
                    provider="minimax",
                    model="speech-2",
                    raw_amount=220,
                    usage_type=BILL_USAGE_TYPE_TTS,
                ),
                _create_daily_metric(
                    daily_usage_metric_bid="daily-tts-1",
                    usage_type=BILL_USAGE_TYPE_TTS,
                    provider="minimax",
                    model="speech-2",
                    billing_metric=BILLING_METRIC_TTS_OUTPUT_CHARS,
                    raw_amount=220,
                    consumed_credits="0.8000000000",
                ),
            ]
        )
        dao.db.session.commit()

    payload = diagnose_tts_consumption(
        billing_diagnostics_app,
        creator_bid="creator-diagnose-1",
        started_at="2026-04-20 13:00",
        ended_at="2026-04-20 13:10",
        timezone_name="Asia/Shanghai",
    )

    assert payload["summary"]["root_cause"] == "display_layer_missing_tts_distinction"
    assert {
        item["ledger_bid"]: item["resolved_usage_type"]
        for item in payload["ledger_entries"]
    } == {
        "ledger-llm-1": "llm",
        "ledger-tts-1": "tts",
    }
    assert payload["summary"]["ledger_tts_metric_count"] == 1
    assert payload["summary"]["daily_tts_metric_count"] == 1
    assert payload["sample_chains"][0] == {
        "ledger_bid": "ledger-tts-1",
        "usage_bid": "usage-tts-1",
        "root_usage_bid": "usage-tts-1",
        "root_usage_type": "tts",
        "daily_usage_metric_bid": "daily-tts-1",
        "daily_stat_date": "2026-04-20",
        "daily_billing_metric": "tts_output_chars",
    }


def test_diagnose_tts_consumption_flags_settlement_gap(
    billing_diagnostics_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.diagnostics.resolve_usage_creator_bid",
        lambda app, usage: "creator-diagnose-1",
    )

    with billing_diagnostics_app.app_context():
        dao.db.session.add(
            _create_usage(
                usage_bid="usage-tts-gap-1",
                usage_type=BILL_USAGE_TYPE_TTS,
                provider="minimax",
                model="speech-2",
                created_at=datetime(2026, 4, 20, 13, 5, 0),
                input_value=18,
                output_value=180,
            )
        )
        dao.db.session.commit()

    payload = diagnose_tts_consumption(
        billing_diagnostics_app,
        creator_bid="creator-diagnose-1",
        started_at="2026-04-20 13:00",
        ended_at="2026-04-20 13:10",
        timezone_name="Asia/Shanghai",
    )

    assert payload["summary"]["root_cause"] == "settlement_gap"
    assert payload["summary"]["tts_root_usage_count"] == 1
    assert payload["summary"]["ledger_tts_metric_count"] == 0
    assert payload["sample_chains"][0]["ledger_bid"] is None
    assert payload["sample_chains"][0]["usage_bid"] == "usage-tts-gap-1"
    assert payload["sample_chains"][0]["root_usage_bid"] == "usage-tts-gap-1"


def test_diagnose_tts_consumption_flags_missing_tts_root_usage(
    billing_diagnostics_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.diagnostics.resolve_usage_creator_bid",
        lambda app, usage: "creator-diagnose-1",
    )

    with billing_diagnostics_app.app_context():
        dao.db.session.add(
            _create_usage(
                usage_bid="usage-tts-segment-1",
                usage_type=BILL_USAGE_TYPE_TTS,
                provider="minimax",
                model="speech-2",
                created_at=datetime(2026, 4, 20, 13, 6, 0),
                input_value=6,
                output_value=60,
                record_level=1,
                parent_usage_bid="usage-tts-root-missing",
                segment_index=1,
                segment_count=2,
            )
        )
        dao.db.session.commit()

    payload = diagnose_tts_consumption(
        billing_diagnostics_app,
        creator_bid="creator-diagnose-1",
        started_at="2026-04-20 13:00",
        ended_at="2026-04-20 13:10",
        timezone_name="Asia/Shanghai",
    )

    assert payload["summary"]["root_cause"] == "tts_root_usage_missing"
    assert payload["summary"]["tts_root_usage_count"] == 0
    assert payload["summary"]["tts_segment_usage_count"] == 1
    assert payload["sample_chains"][0]["usage_bid"] == "usage-tts-segment-1"
    assert payload["sample_chains"][0]["root_usage_bid"] == "usage-tts-root-missing"


def test_diagnose_tts_consumption_flags_runtime_tts_missing(
    billing_diagnostics_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.diagnostics.resolve_usage_creator_bid",
        lambda app, usage: "creator-diagnose-1",
    )

    with billing_diagnostics_app.app_context():
        dao.db.session.add_all(
            [
                _create_usage(
                    usage_bid="usage-llm-only-1",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-4o-mini",
                    created_at=datetime(2026, 4, 20, 13, 7, 0),
                    input_value=200,
                    output_value=50,
                ),
                _create_ledger(
                    ledger_bid="ledger-llm-only-1",
                    usage_bid="usage-llm-only-1",
                    amount="-0.50",
                    created_at=datetime(2026, 4, 20, 13, 7, 20),
                    billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    provider="openai",
                    model="gpt-4o-mini",
                    raw_amount=50,
                    usage_type=BILL_USAGE_TYPE_LLM,
                ),
            ]
        )
        dao.db.session.commit()

    payload = diagnose_tts_consumption(
        billing_diagnostics_app,
        creator_bid="creator-diagnose-1",
        started_at="2026-04-20 13:00",
        ended_at="2026-04-20 13:10",
        timezone_name="Asia/Shanghai",
    )

    assert payload["summary"]["root_cause"] == "runtime_tts_usage_missing"
    assert payload["summary"]["tts_root_usage_count"] == 0
    assert payload["summary"]["tts_segment_usage_count"] == 0
    assert payload["summary"]["ledger_tts_metric_count"] == 0
    assert payload["daily_tts_metrics"] == []
    assert payload["sample_chains"] == []


def _create_usage(
    *,
    usage_bid: str,
    usage_type: int,
    provider: str,
    model: str,
    created_at: datetime,
    input_value: int,
    output_value: int,
    record_level: int = 0,
    parent_usage_bid: str = "",
    segment_index: int = 0,
    segment_count: int = 0,
) -> BillUsageRecord:
    return BillUsageRecord(
        usage_bid=usage_bid,
        parent_usage_bid=parent_usage_bid,
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
        usage_scene=BILL_USAGE_SCENE_PROD,
        provider=provider,
        model=model,
        is_stream=0,
        input=input_value,
        input_cache=0,
        output=output_value,
        total=input_value + output_value,
        word_count=output_value,
        duration_ms=1000,
        latency_ms=100,
        segment_index=segment_index,
        segment_count=segment_count,
        billable=1,
        status=0,
        error_message="",
        extra={},
        created_at=created_at,
        updated_at=created_at,
    )


def _create_ledger(
    *,
    ledger_bid: str,
    usage_bid: str,
    amount: str,
    created_at: datetime,
    billing_metric: int,
    provider: str,
    model: str,
    raw_amount: int,
    usage_type: int,
) -> CreditLedgerEntry:
    return CreditLedgerEntry(
        ledger_bid=ledger_bid,
        creator_bid="creator-diagnose-1",
        wallet_bid="wallet-diagnose-1",
        wallet_bucket_bid="bucket-diagnose-1",
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
        source_type=CREDIT_SOURCE_TYPE_USAGE,
        source_bid=usage_bid,
        idempotency_key=f"usage:{usage_bid}:consume",
        amount=Decimal(amount),
        balance_after=Decimal("9.0000000000"),
        expires_at=None,
        consumable_from=None,
        metadata_json={
            "usage_bid": usage_bid,
            "usage_scene": BILL_USAGE_SCENE_PROD,
            "usage_type": usage_type,
            "provider": provider,
            "model": model,
            "metric_breakdown": [
                {
                    "billing_metric": BILLING_METRIC_LABELS[billing_metric],
                    "billing_metric_code": billing_metric,
                    "raw_amount": raw_amount,
                    "unit_size": 1000,
                    "rounded_units": 1,
                    "credits_per_unit": 1,
                    "rounding_mode": "ceil",
                    "consumed_credits": str(abs(Decimal(amount))),
                }
            ],
        },
        created_at=created_at,
        updated_at=created_at,
    )


def _create_daily_metric(
    *,
    daily_usage_metric_bid: str,
    usage_type: int,
    provider: str,
    model: str,
    billing_metric: int,
    raw_amount: int,
    consumed_credits: str,
) -> BillingDailyUsageMetric:
    return BillingDailyUsageMetric(
        daily_usage_metric_bid=daily_usage_metric_bid,
        stat_date="2026-04-20",
        creator_bid="creator-diagnose-1",
        shifu_bid="shifu-1",
        usage_scene=BILL_USAGE_SCENE_PROD,
        usage_type=usage_type,
        provider=provider,
        model=model,
        billing_metric=billing_metric,
        raw_amount=raw_amount,
        record_count=1,
        consumed_credits=Decimal(consumed_credits),
        window_started_at=datetime(2026, 4, 20, 13, 0, 0),
        window_ended_at=datetime(2026, 4, 20, 13, 10, 0),
    )
