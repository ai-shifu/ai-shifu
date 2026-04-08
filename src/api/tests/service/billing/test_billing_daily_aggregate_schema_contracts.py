from __future__ import annotations

from pathlib import Path

from flaskr.service.billing.models import (
    BillingDailyLedgerSummary,
    BillingDailyUsageMetric,
)

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_v11_models_define_daily_aggregate_tables() -> None:
    usage_table = BillingDailyUsageMetric.__table__
    ledger_table = BillingDailyLedgerSummary.__table__

    assert BillingDailyUsageMetric.__tablename__ == "billing_daily_usage_metrics"
    assert "daily_usage_metric_bid" in usage_table.c
    assert "consumed_credits" in usage_table.c
    assert "window_started_at" in usage_table.c

    assert BillingDailyLedgerSummary.__tablename__ == "billing_daily_ledger_summary"
    assert "daily_ledger_summary_bid" in ledger_table.c
    assert "amount" in ledger_table.c
    assert "entry_count" in ledger_table.c


def test_billing_v11_migration_creates_daily_aggregate_tables() -> None:
    source = (
        _API_ROOT
        / "migrations/versions/d4e5f6a7b8c9_add_billing_daily_aggregate_tables.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "c1d2e3f4a5b6"' in source
    assert 'op.create_table(\n        "billing_daily_usage_metrics",' in source
    assert 'op.create_table(\n        "billing_daily_ledger_summary",' in source
    assert "uq_billing_daily_usage_metrics_lookup" in source
    assert "ix_billing_daily_usage_metrics_stat_creator" in source
    assert "uq_billing_daily_ledger_summary_lookup" in source
    assert "ix_billing_daily_ledger_summary_stat_creator" in source
