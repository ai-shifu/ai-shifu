from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_SOURCE_TYPE_USAGE,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.daily_aggregates import (
    aggregate_daily_usage_metrics,
    finalize_daily_usage_metrics,
)
from flaskr.service.billing.models import (
    BillingDailyUsageMetric,
    CreditLedgerEntry,
    CreditUsageRate,
)
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD, BILL_USAGE_TYPE_LLM
from flaskr.service.metering.models import BillUsageRecord


@pytest.fixture
def billing_daily_usage_app(tmp_path):
    db_path = tmp_path / "billing-daily-usage.sqlite"
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
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def test_aggregate_daily_usage_metrics_respects_incremental_window_and_creator_scope(
    billing_daily_usage_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.daily_aggregates.resolve_usage_creator_bid",
        lambda app, usage: {
            "shifu-agg-1": "creator-agg-1",
            "shifu-agg-2": "creator-agg-2",
        }.get(usage.shifu_bid, ""),
    )

    with billing_daily_usage_app.app_context():
        _add_llm_rates()
        _add_usage(
            usage_bid="usage-morning",
            shifu_bid="shifu-agg-1",
            created_at=datetime(2026, 4, 8, 9, 0, 0),
            input_tokens=100,
            output_tokens=40,
        )
        _add_usage(
            usage_bid="usage-afternoon",
            shifu_bid="shifu-agg-1",
            created_at=datetime(2026, 4, 8, 18, 0, 0),
            input_tokens=70,
            output_tokens=20,
        )
        _add_usage(
            usage_bid="usage-other-creator",
            shifu_bid="shifu-agg-2",
            created_at=datetime(2026, 4, 8, 10, 0, 0),
            input_tokens=33,
            output_tokens=11,
        )
        _add_usage(
            usage_bid="usage-next-day",
            shifu_bid="shifu-agg-1",
            created_at=datetime(2026, 4, 9, 8, 0, 0),
            input_tokens=55,
            output_tokens=12,
        )
        _add_usage_ledger(
            creator_bid="creator-agg-1",
            usage_bid="usage-morning",
            metric_code=BILLING_METRIC_LLM_INPUT_TOKENS,
            amount=Decimal("-1.2500000000"),
            created_at=datetime(2026, 4, 8, 9, 1, 0),
        )
        _add_usage_ledger(
            creator_bid="creator-agg-1",
            usage_bid="usage-morning",
            metric_code=BILLING_METRIC_LLM_OUTPUT_TOKENS,
            amount=Decimal("-0.7500000000"),
            created_at=datetime(2026, 4, 8, 9, 1, 30),
        )
        _add_usage_ledger(
            creator_bid="creator-agg-1",
            usage_bid="usage-afternoon",
            metric_code=BILLING_METRIC_LLM_INPUT_TOKENS,
            amount=Decimal("-0.9000000000"),
            created_at=datetime(2026, 4, 8, 18, 1, 0),
        )
        _add_usage_ledger(
            creator_bid="creator-agg-1",
            usage_bid="usage-afternoon",
            metric_code=BILLING_METRIC_LLM_OUTPUT_TOKENS,
            amount=Decimal("-0.4500000000"),
            created_at=datetime(2026, 4, 8, 18, 1, 30),
        )
        dao.db.session.add(
            BillingDailyUsageMetric(
                daily_usage_metric_bid="existing-other-creator-row",
                stat_date="2026-04-08",
                creator_bid="creator-agg-2",
                shifu_bid="shifu-agg-2",
                usage_scene=BILL_USAGE_SCENE_PROD,
                usage_type=BILL_USAGE_TYPE_LLM,
                provider="openai",
                model="gpt-4o-mini",
                billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                raw_amount=99,
                record_count=9,
                consumed_credits=Decimal("9.0000000000"),
                window_started_at=datetime(2026, 4, 8, 0, 0, 0),
                window_ended_at=datetime(2026, 4, 8, 23, 59, 59),
            )
        )
        dao.db.session.commit()

        payload = aggregate_daily_usage_metrics(
            billing_daily_usage_app,
            stat_date="2026-04-08",
            creator_bid="creator-agg-1",
            now=datetime(2026, 4, 8, 12, 0, 0),
        )

        assert payload["status"] == "aggregated"
        assert payload["creator_bid"] == "creator-agg-1"
        assert payload["usage_count"] == 1
        assert payload["row_count"] == 2
        assert payload["window_ended_at"] == "2026-04-08T12:00:00"

        creator_rows = (
            BillingDailyUsageMetric.query.filter(
                BillingDailyUsageMetric.stat_date == "2026-04-08",
                BillingDailyUsageMetric.creator_bid == "creator-agg-1",
            )
            .order_by(BillingDailyUsageMetric.billing_metric.asc())
            .all()
        )
        assert len(creator_rows) == 2
        assert [
            (
                row.billing_metric,
                int(row.raw_amount or 0),
                int(row.record_count or 0),
                str(row.consumed_credits),
            )
            for row in creator_rows
        ] == [
            (
                BILLING_METRIC_LLM_INPUT_TOKENS,
                100,
                1,
                "1.2500000000",
            ),
            (
                BILLING_METRIC_LLM_OUTPUT_TOKENS,
                40,
                1,
                "0.7500000000",
            ),
        ]

        other_creator_rows = BillingDailyUsageMetric.query.filter(
            BillingDailyUsageMetric.stat_date == "2026-04-08",
            BillingDailyUsageMetric.creator_bid == "creator-agg-2",
        ).all()
        assert len(other_creator_rows) == 1
        assert (
            other_creator_rows[0].daily_usage_metric_bid == "existing-other-creator-row"
        )


def test_finalize_daily_usage_metrics_recomputes_full_day(
    billing_daily_usage_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.daily_aggregates.resolve_usage_creator_bid",
        lambda app, usage: "creator-agg-1",
    )

    with billing_daily_usage_app.app_context():
        _add_llm_rates()
        _add_usage(
            usage_bid="usage-finalize-a",
            shifu_bid="shifu-agg-1",
            created_at=datetime(2026, 4, 8, 6, 0, 0),
            input_tokens=25,
            output_tokens=5,
        )
        _add_usage(
            usage_bid="usage-finalize-b",
            shifu_bid="shifu-agg-1",
            created_at=datetime(2026, 4, 8, 21, 0, 0),
            input_tokens=75,
            output_tokens=15,
        )
        _add_usage_ledger(
            creator_bid="creator-agg-1",
            usage_bid="usage-finalize-a",
            metric_code=BILLING_METRIC_LLM_INPUT_TOKENS,
            amount=Decimal("-0.2500000000"),
            created_at=datetime(2026, 4, 8, 6, 1, 0),
        )
        _add_usage_ledger(
            creator_bid="creator-agg-1",
            usage_bid="usage-finalize-a",
            metric_code=BILLING_METRIC_LLM_OUTPUT_TOKENS,
            amount=Decimal("-0.0500000000"),
            created_at=datetime(2026, 4, 8, 6, 1, 30),
        )
        _add_usage_ledger(
            creator_bid="creator-agg-1",
            usage_bid="usage-finalize-b",
            metric_code=BILLING_METRIC_LLM_INPUT_TOKENS,
            amount=Decimal("-0.7500000000"),
            created_at=datetime(2026, 4, 8, 21, 1, 0),
        )
        _add_usage_ledger(
            creator_bid="creator-agg-1",
            usage_bid="usage-finalize-b",
            metric_code=BILLING_METRIC_LLM_OUTPUT_TOKENS,
            amount=Decimal("-0.1500000000"),
            created_at=datetime(2026, 4, 8, 21, 1, 30),
        )
        dao.db.session.commit()

        payload = finalize_daily_usage_metrics(
            billing_daily_usage_app,
            stat_date="2026-04-08",
            creator_bid="creator-agg-1",
            now=datetime(2026, 4, 9, 1, 0, 0),
        )

        assert payload["status"] == "finalized"
        assert payload["finalize"] is True
        assert payload["usage_count"] == 2
        assert payload["row_count"] == 2
        assert payload["window_started_at"] == "2026-04-08T00:00:00"
        assert payload["window_ended_at"] == "2026-04-09T00:00:00"

        creator_rows = (
            BillingDailyUsageMetric.query.filter(
                BillingDailyUsageMetric.stat_date == "2026-04-08",
                BillingDailyUsageMetric.creator_bid == "creator-agg-1",
            )
            .order_by(BillingDailyUsageMetric.billing_metric.asc())
            .all()
        )
        assert len(creator_rows) == 2
        assert [
            (
                row.billing_metric,
                int(row.raw_amount or 0),
                int(row.record_count or 0),
                str(row.consumed_credits),
                row.window_ended_at.isoformat(),
            )
            for row in creator_rows
        ] == [
            (
                BILLING_METRIC_LLM_INPUT_TOKENS,
                100,
                2,
                "1.0000000000",
                "2026-04-09T00:00:00",
            ),
            (
                BILLING_METRIC_LLM_OUTPUT_TOKENS,
                20,
                2,
                "0.2000000000",
                "2026-04-09T00:00:00",
            ),
        ]


def test_aggregate_daily_usage_metrics_supports_single_usage_ledger_with_multi_metric_metadata(
    billing_daily_usage_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.daily_aggregates.resolve_usage_creator_bid",
        lambda app, usage: "creator-agg-single-ledger",
    )

    with billing_daily_usage_app.app_context():
        _add_llm_rates()
        _add_usage(
            usage_bid="usage-single-ledger",
            shifu_bid="shifu-agg-1",
            created_at=datetime(2026, 4, 8, 9, 0, 0),
            input_tokens=100,
            output_tokens=40,
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-usage-single-ledger",
                creator_bid="creator-agg-single-ledger",
                wallet_bid="wallet-creator-agg-single-ledger",
                wallet_bucket_bid="",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
                source_type=CREDIT_SOURCE_TYPE_USAGE,
                source_bid="usage-single-ledger",
                idempotency_key="usage:usage-single-ledger:consume",
                amount=Decimal("-2.0000000000"),
                balance_after=Decimal("0"),
                metadata_json={
                    "metric_breakdown": [
                        {
                            "billing_metric_code": BILLING_METRIC_LLM_INPUT_TOKENS,
                            "consumed_credits": "1.2500000000",
                        },
                        {
                            "billing_metric_code": BILLING_METRIC_LLM_OUTPUT_TOKENS,
                            "consumed_credits": "0.7500000000",
                        },
                    ],
                    "bucket_breakdown": [
                        {
                            "wallet_bucket_bid": "bucket-free",
                            "consumed_credits": "2.0000000000",
                        }
                    ],
                },
                created_at=datetime(2026, 4, 8, 9, 1, 0),
                updated_at=datetime(2026, 4, 8, 9, 1, 0),
            )
        )
        dao.db.session.commit()

        payload = aggregate_daily_usage_metrics(
            billing_daily_usage_app,
            stat_date="2026-04-08",
            creator_bid="creator-agg-single-ledger",
            now=datetime(2026, 4, 8, 23, 0, 0),
        )

        creator_rows = (
            BillingDailyUsageMetric.query.filter(
                BillingDailyUsageMetric.stat_date == "2026-04-08",
                BillingDailyUsageMetric.creator_bid == "creator-agg-single-ledger",
            )
            .order_by(BillingDailyUsageMetric.billing_metric.asc())
            .all()
        )

        assert payload["status"] == "aggregated"
        assert payload["usage_count"] == 1
        assert payload["metric_count"] == 2
        assert len(creator_rows) == 2
        assert [
            (
                row.billing_metric,
                int(row.raw_amount or 0),
                int(row.record_count or 0),
                str(row.consumed_credits),
            )
            for row in creator_rows
        ] == [
            (
                BILLING_METRIC_LLM_INPUT_TOKENS,
                100,
                1,
                "1.2500000000",
            ),
            (
                BILLING_METRIC_LLM_OUTPUT_TOKENS,
                40,
                1,
                "0.7500000000",
            ),
        ]


def test_aggregate_daily_usage_metrics_quantizes_consumed_credits_with_configured_precision(
    billing_daily_usage_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.daily_aggregates.resolve_usage_creator_bid",
        lambda app, usage: "creator-agg-precision",
    )
    monkeypatch.setattr(
        "flaskr.service.billing.primitives.get_config",
        lambda key, default=None: 2 if key == "BILL_CREDIT_PRECISION" else default,
    )

    with billing_daily_usage_app.app_context():
        _add_llm_rates()
        _add_usage(
            usage_bid="usage-agg-precision",
            shifu_bid="shifu-agg-1",
            created_at=datetime(2026, 4, 8, 9, 0, 0),
            input_tokens=100,
            output_tokens=0,
        )
        _add_usage_ledger(
            creator_bid="creator-agg-precision",
            usage_bid="usage-agg-precision",
            metric_code=BILLING_METRIC_LLM_INPUT_TOKENS,
            amount=Decimal("-1.2350000000"),
            created_at=datetime(2026, 4, 8, 9, 1, 0),
        )
        dao.db.session.commit()

        payload = aggregate_daily_usage_metrics(
            billing_daily_usage_app,
            stat_date="2026-04-08",
            creator_bid="creator-agg-precision",
            now=datetime(2026, 4, 8, 23, 0, 0),
        )

        row = BillingDailyUsageMetric.query.filter(
            BillingDailyUsageMetric.stat_date == "2026-04-08",
            BillingDailyUsageMetric.creator_bid == "creator-agg-precision",
            BillingDailyUsageMetric.billing_metric == BILLING_METRIC_LLM_INPUT_TOKENS,
        ).one()

        assert payload["status"] == "aggregated"
        assert str(row.consumed_credits) == "1.2400000000"


def test_aggregate_daily_usage_metrics_keeps_zero_amount_usage_ledgers(
    billing_daily_usage_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.daily_aggregates.resolve_usage_creator_bid",
        lambda app, usage: "creator-agg-zero-ledger",
    )

    with billing_daily_usage_app.app_context():
        _add_llm_rates()
        _add_usage(
            usage_bid="usage-agg-zero-ledger",
            shifu_bid="shifu-agg-1",
            created_at=datetime(2026, 4, 8, 9, 0, 0),
            input_tokens=100,
            output_tokens=0,
        )
        _add_usage_ledger(
            creator_bid="creator-agg-zero-ledger",
            usage_bid="usage-agg-zero-ledger",
            metric_code=BILLING_METRIC_LLM_INPUT_TOKENS,
            amount=Decimal("0"),
            created_at=datetime(2026, 4, 8, 9, 1, 0),
        )
        dao.db.session.commit()

        payload = aggregate_daily_usage_metrics(
            billing_daily_usage_app,
            stat_date="2026-04-08",
            creator_bid="creator-agg-zero-ledger",
            now=datetime(2026, 4, 8, 23, 0, 0),
        )

        rows = BillingDailyUsageMetric.query.filter(
            BillingDailyUsageMetric.stat_date == "2026-04-08",
            BillingDailyUsageMetric.creator_bid == "creator-agg-zero-ledger",
        ).all()

        assert payload["status"] == "aggregated"
        assert payload["usage_count"] == 1
        assert payload["metric_count"] == 1
        assert len(rows) == 1
        assert rows[0].billing_metric == BILLING_METRIC_LLM_INPUT_TOKENS
        assert int(rows[0].raw_amount or 0) == 100
        assert int(rows[0].record_count or 0) == 1
        assert rows[0].consumed_credits == Decimal("0")


def _add_llm_rates() -> None:
    for metric_code in (
        BILLING_METRIC_LLM_INPUT_TOKENS,
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
    ):
        dao.db.session.add(
            CreditUsageRate(
                rate_bid=f"rate-{metric_code}",
                usage_type=BILL_USAGE_TYPE_LLM,
                provider="openai",
                model="gpt-4o-mini",
                usage_scene=BILL_USAGE_SCENE_PROD,
                billing_metric=metric_code,
                unit_size=100,
                credits_per_unit=Decimal("1.0000000000"),
                rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
                effective_from=datetime(2026, 1, 1, 0, 0, 0),
                status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
            )
        )
    dao.db.session.flush()


def _add_usage(
    *,
    usage_bid: str,
    shifu_bid: str,
    created_at: datetime,
    input_tokens: int,
    output_tokens: int,
) -> None:
    dao.db.session.add(
        BillUsageRecord(
            usage_bid=usage_bid,
            user_bid="user-agg-1",
            shifu_bid=shifu_bid,
            usage_type=BILL_USAGE_TYPE_LLM,
            usage_scene=BILL_USAGE_SCENE_PROD,
            provider="openai",
            model="gpt-4o-mini",
            input=input_tokens,
            output=output_tokens,
            total=input_tokens + output_tokens,
            billable=1,
            status=0,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    dao.db.session.flush()


def _add_usage_ledger(
    *,
    creator_bid: str,
    usage_bid: str,
    metric_code: int,
    amount: Decimal,
    created_at: datetime,
) -> None:
    dao.db.session.add(
        CreditLedgerEntry(
            ledger_bid=f"ledger-{usage_bid}-{metric_code}-{created_at.timestamp()}",
            creator_bid=creator_bid,
            wallet_bid=f"wallet-{creator_bid}",
            wallet_bucket_bid=f"bucket-{usage_bid}-{metric_code}",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            source_bid=usage_bid,
            idempotency_key=f"{usage_bid}:{metric_code}:{created_at.timestamp()}",
            amount=amount,
            balance_after=Decimal("0"),
            metadata_json={
                "metric_breakdown": [
                    {
                        "billing_metric_code": metric_code,
                        "consumed_credits": str(-amount),
                    }
                ]
            },
            created_at=created_at,
            updated_at=created_at,
        )
    )
    dao.db.session.flush()
