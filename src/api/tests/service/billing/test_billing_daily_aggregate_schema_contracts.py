"""Protect billing daily aggregate schema compatibility."""

from __future__ import annotations

from flaskr.service.billing.models import (
    BillingDailyLedgerSummary,
    BillingDailyUsageMetric,
)


def test_billing_v11_models_define_daily_aggregate_tables() -> None:
    usage_table = BillingDailyUsageMetric.__table__
    ledger_table = BillingDailyLedgerSummary.__table__

    assert BillingDailyUsageMetric.__tablename__ == "bill_daily_usage_metrics"
    assert "daily_usage_metric_bid" in usage_table.c
    assert "consumed_credits" in usage_table.c
    assert "window_started_at" in usage_table.c

    assert BillingDailyLedgerSummary.__tablename__ == "bill_daily_ledger_summary"
    assert "daily_ledger_summary_bid" in ledger_table.c
    assert "amount" in ledger_table.c
    assert "entry_count" in ledger_table.c
