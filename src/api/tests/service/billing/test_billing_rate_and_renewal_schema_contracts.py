"""Protect billing rate and renewal schema compatibility."""

from __future__ import annotations

from flaskr.service.billing.models import (
    BillingRenewalEvent,
    CreditLedgerEntry,
    CreditUsageRate,
    CreditWallet,
    CreditWalletBucket,
)
from sqlalchemy import Numeric


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
