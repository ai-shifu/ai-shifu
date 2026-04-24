from __future__ import annotations

from pathlib import Path

from sqlalchemy import Numeric

from flaskr.service.billing.models import (
    BillingRenewalEvent,
    CreditLedgerEntry,
    CreditUsageRate,
    CreditWallet,
    CreditWalletBucket,
)

_API_ROOT = Path(__file__).resolve().parents[3]


def test_credit_schema_models_define_wallet_ledger_rate_and_renewal_tables() -> None:
    wallet_table = CreditWallet.__table__
    bucket_table = CreditWalletBucket.__table__
    ledger_table = CreditLedgerEntry.__table__
    rate_table = CreditUsageRate.__table__
    renewal_table = BillingRenewalEvent.__table__

    assert CreditWallet.__tablename__ == "credit_wallets"
    assert "available_credits" in wallet_table.c
    assert "reserved_credits" in wallet_table.c

    assert CreditWalletBucket.__tablename__ == "credit_wallet_buckets"
    assert "bucket_category" in bucket_table.c
    assert "priority" in bucket_table.c

    assert CreditLedgerEntry.__tablename__ == "credit_ledger_entries"
    assert "wallet_bucket_bid" in ledger_table.c
    assert "idempotency_key" in ledger_table.c

    assert CreditUsageRate.__tablename__ == "credit_usage_rates"
    assert "billing_metric" in rate_table.c
    assert "credits_per_unit" in rate_table.c
    assert isinstance(rate_table.c["credits_per_unit"].type, Numeric)
    assert rate_table.c["credits_per_unit"].type.precision == 20
    assert rate_table.c["credits_per_unit"].type.scale == 10

    assert BillingRenewalEvent.__tablename__ == "bill_renewal_events"
    assert "renewal_event_bid" in renewal_table.c
    assert "event_type" in renewal_table.c
    assert "scheduled_at" in renewal_table.c


def test_billing_rate_and_renewal_migration_creates_missing_schema_tables() -> None:
    source = (
        _API_ROOT / "migrations/versions/b114d7f5e2c1_add_billing_core_phase.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "b114d7f5e2c1"' in source
    assert 'op.create_table(\n        "credit_usage_rates",' in source
    assert 'op.create_table(\n        "bill_renewal_events",' in source
    assert "sa.Numeric(precision=20, scale=10)" in source
    assert "ix_credit_usage_rates_lookup" in source
    assert "ix_bill_renewal_events_status_scheduled" in source
    assert "ix_bill_renewal_events_subscription_event_scheduled" in source
