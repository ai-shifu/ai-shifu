from __future__ import annotations

from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_schema_hardening_migration_adds_unique_constraints_and_rate_seeds() -> (
    None
):
    source = (
        _API_ROOT
        / "migrations/versions/9c1d2e3f4a5b_harden_billing_schema_and_seed_rates.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "8f1d2c3b4a5e"' in source
    assert "uq_billing_products_product_bid" in source
    assert "uq_billing_subscriptions_subscription_bid" in source
    assert "uq_billing_orders_billing_order_bid" in source
    assert "uq_credit_wallets_wallet_bid" in source
    assert "uq_credit_wallet_buckets_wallet_bucket_bid" in source
    assert "uq_credit_ledger_entries_ledger_bid" in source
    assert "uq_credit_usage_rates_rate_bid" in source
    assert "uq_credit_usage_rates_lookup" in source
    assert "uq_billing_renewal_events_renewal_event_bid" in source
    assert "uq_billing_renewal_events_subscription_event_scheduled" in source
    assert "op.bulk_insert(rate_table, list(_USAGE_RATE_SEEDS))" in source
