from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_INPUT_TOKENS,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.daily_aggregates import rebuild_daily_aggregates
from flaskr.service.billing.models import (
    BillingDailyLedgerSummary,
    BillingDailyUsageMetric,
    CreditLedgerEntry,
    CreditUsageRate,
)
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD, BILL_USAGE_TYPE_LLM
from flaskr.service.metering.models import BillUsageRecord


@pytest.fixture
def billing_daily_rebuild_app(tmp_path):
    db_path = tmp_path / "billing-daily-rebuild.sqlite"
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


def test_rebuild_daily_aggregates_rebuilds_creator_date_window(
    billing_daily_rebuild_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.daily_aggregates.resolve_usage_creator_bid",
        lambda app, usage: "creator-rebuild-1",
    )

    with billing_daily_rebuild_app.app_context():
        _add_rate()
        _add_usage(
            usage_bid="usage-rebuild-day-1",
            shifu_bid="shifu-rebuild-1",
            created_at=datetime(2026, 4, 8, 9, 0, 0),
            input_tokens=100,
        )
        _add_usage(
            usage_bid="usage-rebuild-day-2",
            shifu_bid="shifu-rebuild-1",
            created_at=datetime(2026, 4, 9, 9, 0, 0),
            input_tokens=60,
        )
        _add_ledger(
            creator_bid="creator-rebuild-1",
            ledger_bid="ledger-rebuild-day-1",
            source_bid="usage-rebuild-day-1",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            amount=Decimal("-1.0000000000"),
            created_at=datetime(2026, 4, 8, 9, 1, 0),
        )
        _add_ledger(
            creator_bid="creator-rebuild-1",
            ledger_bid="ledger-rebuild-day-2",
            source_bid="topup-rebuild-day-2",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            amount=Decimal("5.0000000000"),
            created_at=datetime(2026, 4, 9, 9, 1, 0),
        )
        dao.db.session.commit()

        payload = rebuild_daily_aggregates(
            billing_daily_rebuild_app,
            creator_bid="creator-rebuild-1",
            date_from="2026-04-08",
            date_to="2026-04-09",
        )

        assert payload["status"] == "rebuilt"
        assert payload["day_count"] == 2
        assert payload["usage"]["processed_days"] == 2
        assert payload["ledger"]["processed_days"] == 2
        assert payload["ledger"]["skipped_days"] == 0

        usage_rows = (
            BillingDailyUsageMetric.query.filter(
                BillingDailyUsageMetric.creator_bid == "creator-rebuild-1"
            )
            .order_by(BillingDailyUsageMetric.stat_date.asc())
            .all()
        )
        assert [
            (
                row.stat_date,
                row.shifu_bid,
                int(row.raw_amount or 0),
                str(row.consumed_credits),
            )
            for row in usage_rows
        ] == [
            ("2026-04-08", "shifu-rebuild-1", 100, "1.0000000000"),
            ("2026-04-09", "shifu-rebuild-1", 60, "0E-10"),
        ]

        ledger_rows = (
            BillingDailyLedgerSummary.query.filter(
                BillingDailyLedgerSummary.creator_bid == "creator-rebuild-1"
            )
            .order_by(BillingDailyLedgerSummary.stat_date.asc())
            .all()
        )
        assert [
            (row.stat_date, row.entry_type, row.source_type, str(row.amount))
            for row in ledger_rows
        ] == [
            (
                "2026-04-08",
                CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
                CREDIT_SOURCE_TYPE_USAGE,
                "-1.0000000000",
            ),
            (
                "2026-04-09",
                CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                CREDIT_SOURCE_TYPE_TOPUP,
                "5.0000000000",
            ),
        ]


def test_rebuild_daily_aggregates_scopes_usage_by_shifu_and_skips_ledger(
    billing_daily_rebuild_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.daily_aggregates.resolve_usage_creator_bid",
        lambda app, usage: "creator-rebuild-1",
    )

    with billing_daily_rebuild_app.app_context():
        _add_rate()
        _add_usage(
            usage_bid="usage-shifu-a",
            shifu_bid="shifu-a",
            created_at=datetime(2026, 4, 8, 8, 0, 0),
            input_tokens=50,
        )
        _add_usage(
            usage_bid="usage-shifu-b",
            shifu_bid="shifu-b",
            created_at=datetime(2026, 4, 8, 10, 0, 0),
            input_tokens=80,
        )
        dao.db.session.add(
            BillingDailyUsageMetric(
                daily_usage_metric_bid="existing-shifu-b-row",
                stat_date="2026-04-08",
                creator_bid="creator-rebuild-1",
                shifu_bid="shifu-b",
                usage_scene=BILL_USAGE_SCENE_PROD,
                usage_type=BILL_USAGE_TYPE_LLM,
                provider="openai",
                model="gpt-4o-mini",
                billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                raw_amount=999,
                record_count=9,
                consumed_credits=Decimal("9.0000000000"),
                window_started_at=datetime(2026, 4, 8, 0, 0, 0),
                window_ended_at=datetime(2026, 4, 9, 0, 0, 0),
            )
        )
        dao.db.session.commit()

        payload = rebuild_daily_aggregates(
            billing_daily_rebuild_app,
            creator_bid="creator-rebuild-1",
            shifu_bid="shifu-a",
            date_from="2026-04-08",
            date_to="2026-04-08",
        )

        assert payload["status"] == "rebuilt"
        assert payload["ledger"]["processed_days"] == 0
        assert payload["ledger"]["skipped_days"] == 1
        assert payload["ledger"]["days"][0]["reason"] == "shifu_scope_not_supported"

        usage_rows = (
            BillingDailyUsageMetric.query.filter(
                BillingDailyUsageMetric.creator_bid == "creator-rebuild-1",
                BillingDailyUsageMetric.stat_date == "2026-04-08",
            )
            .order_by(BillingDailyUsageMetric.shifu_bid.asc())
            .all()
        )
        assert [(row.shifu_bid, int(row.raw_amount or 0)) for row in usage_rows] == [
            ("shifu-a", 50),
            ("shifu-b", 999),
        ]


def _add_rate() -> None:
    dao.db.session.add(
        CreditUsageRate(
            rate_bid="rate-rebuild-input",
            usage_type=BILL_USAGE_TYPE_LLM,
            provider="openai",
            model="gpt-4o-mini",
            usage_scene=BILL_USAGE_SCENE_PROD,
            billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
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
) -> None:
    dao.db.session.add(
        BillUsageRecord(
            usage_bid=usage_bid,
            user_bid="user-rebuild-1",
            shifu_bid=shifu_bid,
            usage_type=BILL_USAGE_TYPE_LLM,
            usage_scene=BILL_USAGE_SCENE_PROD,
            provider="openai",
            model="gpt-4o-mini",
            input=input_tokens,
            output=0,
            total=input_tokens,
            billable=1,
            status=0,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    dao.db.session.flush()


def _add_ledger(
    *,
    creator_bid: str,
    ledger_bid: str,
    source_bid: str,
    entry_type: int,
    source_type: int,
    amount: Decimal,
    created_at: datetime,
) -> None:
    dao.db.session.add(
        CreditLedgerEntry(
            ledger_bid=ledger_bid,
            creator_bid=creator_bid,
            wallet_bid=f"wallet-{creator_bid}",
            wallet_bucket_bid=f"bucket-{ledger_bid}",
            entry_type=entry_type,
            source_type=source_type,
            source_bid=source_bid,
            idempotency_key=f"idempotency-{ledger_bid}",
            amount=amount,
            balance_after=Decimal("0"),
            metadata_json=(
                {
                    "metric_breakdown": [
                        {
                            "billing_metric_code": BILLING_METRIC_LLM_INPUT_TOKENS,
                            "consumed_credits": str(-amount),
                        }
                    ]
                }
                if source_type == CREDIT_SOURCE_TYPE_USAGE
                else {}
            ),
            created_at=created_at,
            updated_at=created_at,
        )
    )
    dao.db.session.flush()
