from __future__ import annotations

from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_schema_hardening_migration_adds_unique_constraints_without_seed_rows() -> (
    None
):
    source = (
        _API_ROOT / "migrations/versions/b114d7f5e2c1_add_billing_core_phase.py"
    ).read_text(encoding="utf-8")

    assert "uq_bill_products_product_bid" in source
    assert "uq_bill_subscriptions_subscription_bid" in source
    assert "uq_bill_orders_bill_order_bid" in source
    assert "uq_credit_wallets_wallet_bid" in source
    assert "uq_credit_wallet_buckets_wallet_bucket_bid" in source
    assert "uq_credit_ledger_entries_ledger_bid" in source
    assert "uq_credit_usage_rates_rate_bid" in source
    assert "uq_credit_usage_rates_lookup" in source
    assert "uq_bill_renewal_events_renewal_event_bid" in source
    assert "uq_bill_renewal_events_subscription_event_scheduled" in source
    assert "op.bulk_insert(" not in source
