from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.daily_aggregates import (
    aggregate_daily_ledger_summary,
    finalize_daily_ledger_summary,
)
from flaskr.service.billing.models import BillingDailyLedgerSummary, CreditLedgerEntry


@pytest.fixture
def billing_daily_ledger_app(tmp_path):
    db_path = tmp_path / "billing-daily-ledger.sqlite"
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


def test_aggregate_daily_ledger_summary_respects_incremental_window_and_creator_scope(
    billing_daily_ledger_app: Flask,
) -> None:
    with billing_daily_ledger_app.app_context():
        _add_ledger_entry(
            creator_bid="creator-ledger-1",
            ledger_bid="ledger-morning-consume",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            amount=Decimal("-1.2500000000"),
            created_at=datetime(2026, 4, 8, 9, 0, 0),
        )
        _add_ledger_entry(
            creator_bid="creator-ledger-1",
            ledger_bid="ledger-afternoon-grant",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            amount=Decimal("10.0000000000"),
            created_at=datetime(2026, 4, 8, 18, 0, 0),
        )
        _add_ledger_entry(
            creator_bid="creator-ledger-1",
            ledger_bid="ledger-next-day",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            amount=Decimal("8.0000000000"),
            created_at=datetime(2026, 4, 9, 8, 0, 0),
        )
        dao.db.session.add(
            BillingDailyLedgerSummary(
                daily_ledger_summary_bid="existing-other-ledger-row",
                stat_date="2026-04-08",
                creator_bid="creator-ledger-2",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_TOPUP,
                amount=Decimal("9.0000000000"),
                entry_count=9,
                window_started_at=datetime(2026, 4, 8, 0, 0, 0),
                window_ended_at=datetime(2026, 4, 8, 23, 59, 59),
            )
        )
        dao.db.session.commit()

        payload = aggregate_daily_ledger_summary(
            billing_daily_ledger_app,
            stat_date="2026-04-08",
            creator_bid="creator-ledger-1",
            now=datetime(2026, 4, 8, 12, 0, 0),
        )

        assert payload["status"] == "aggregated"
        assert payload["creator_bid"] == "creator-ledger-1"
        assert payload["entry_count"] == 1
        assert payload["row_count"] == 1
        assert payload["window_ended_at"] == "2026-04-08T12:00:00"

        creator_rows = BillingDailyLedgerSummary.query.filter(
            BillingDailyLedgerSummary.stat_date == "2026-04-08",
            BillingDailyLedgerSummary.creator_bid == "creator-ledger-1",
        ).all()
        assert len(creator_rows) == 1
        assert creator_rows[0].entry_type == CREDIT_LEDGER_ENTRY_TYPE_CONSUME
        assert creator_rows[0].source_type == CREDIT_SOURCE_TYPE_USAGE
        assert str(creator_rows[0].amount) == "-1.2500000000"
        assert int(creator_rows[0].entry_count or 0) == 1

        other_creator_rows = BillingDailyLedgerSummary.query.filter(
            BillingDailyLedgerSummary.stat_date == "2026-04-08",
            BillingDailyLedgerSummary.creator_bid == "creator-ledger-2",
        ).all()
        assert len(other_creator_rows) == 1
        assert (
            other_creator_rows[0].daily_ledger_summary_bid
            == "existing-other-ledger-row"
        )


def test_finalize_daily_ledger_summary_recomputes_full_day(
    billing_daily_ledger_app: Flask,
) -> None:
    with billing_daily_ledger_app.app_context():
        _add_ledger_entry(
            creator_bid="creator-ledger-1",
            ledger_bid="ledger-consume-a",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            amount=Decimal("-1.2500000000"),
            created_at=datetime(2026, 4, 8, 6, 0, 0),
        )
        _add_ledger_entry(
            creator_bid="creator-ledger-1",
            ledger_bid="ledger-consume-b",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            source_type=CREDIT_SOURCE_TYPE_USAGE,
            amount=Decimal("-0.7500000000"),
            created_at=datetime(2026, 4, 8, 21, 0, 0),
        )
        _add_ledger_entry(
            creator_bid="creator-ledger-1",
            ledger_bid="ledger-grant-a",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            amount=Decimal("5.0000000000"),
            created_at=datetime(2026, 4, 8, 21, 30, 0),
        )
        dao.db.session.commit()

        payload = finalize_daily_ledger_summary(
            billing_daily_ledger_app,
            stat_date="2026-04-08",
            creator_bid="creator-ledger-1",
            now=datetime(2026, 4, 9, 1, 0, 0),
        )

        assert payload["status"] == "finalized"
        assert payload["finalize"] is True
        assert payload["entry_count"] == 3
        assert payload["row_count"] == 2
        assert payload["window_started_at"] == "2026-04-08T00:00:00"
        assert payload["window_ended_at"] == "2026-04-09T00:00:00"

        creator_rows = (
            BillingDailyLedgerSummary.query.filter(
                BillingDailyLedgerSummary.stat_date == "2026-04-08",
                BillingDailyLedgerSummary.creator_bid == "creator-ledger-1",
            )
            .order_by(
                BillingDailyLedgerSummary.entry_type.asc(),
                BillingDailyLedgerSummary.source_type.asc(),
            )
            .all()
        )
        assert len(creator_rows) == 2
        assert [
            (
                row.entry_type,
                row.source_type,
                str(row.amount),
                int(row.entry_count or 0),
                row.window_ended_at.isoformat(),
            )
            for row in creator_rows
        ] == [
            (
                CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                CREDIT_SOURCE_TYPE_TOPUP,
                "5.0000000000",
                1,
                "2026-04-09T00:00:00",
            ),
            (
                CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
                CREDIT_SOURCE_TYPE_USAGE,
                "-2.0000000000",
                2,
                "2026-04-09T00:00:00",
            ),
        ]


def _add_ledger_entry(
    *,
    creator_bid: str,
    ledger_bid: str,
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
            source_bid=f"source-{ledger_bid}",
            idempotency_key=f"idempotency-{ledger_bid}",
            amount=amount,
            balance_after=Decimal("0"),
            metadata_json={},
            created_at=created_at,
            updated_at=created_at,
        )
    )
    dao.db.session.flush()
