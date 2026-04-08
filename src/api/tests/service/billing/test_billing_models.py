from __future__ import annotations

from flaskr.dao import db
from flaskr.service.billing.consts import (
    BILLING_MODE_ONE_TIME,
    BILLING_MODE_RECURRING,
    BILLING_PRODUCT_SEEDS,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
)
from flaskr.service.billing.models import BillingProduct


def test_billing_models_register_core_tables() -> None:
    tables = db.metadata.tables

    assert "billing_products" in tables
    assert "billing_subscriptions" in tables
    assert "billing_orders" in tables
    assert "credit_wallets" in tables
    assert "credit_wallet_buckets" in tables
    assert "credit_ledger_entries" in tables

    billing_products = tables["billing_products"]
    assert "product_code" in billing_products.c
    assert "credit_amount" in billing_products.c
    assert billing_products.c.credit_amount.type.precision == 20
    assert billing_products.c.credit_amount.type.scale == 10

    credit_ledger_entries = tables["credit_ledger_entries"]
    assert "wallet_bucket_bid" in credit_ledger_entries.c
    assert "idempotency_key" in credit_ledger_entries.c
    assert credit_ledger_entries.c.amount.type.precision == 20
    assert credit_ledger_entries.c.amount.type.scale == 10


def test_billing_product_seeds_cover_plan_and_topup_catalog() -> None:
    assert len(BILLING_PRODUCT_SEEDS) == 4

    plan_products = [
        row
        for row in BILLING_PRODUCT_SEEDS
        if row["product_type"] == BILLING_PRODUCT_TYPE_PLAN
    ]
    topup_products = [
        row
        for row in BILLING_PRODUCT_SEEDS
        if row["product_type"] == BILLING_PRODUCT_TYPE_TOPUP
    ]

    assert len(plan_products) == 2
    assert len(topup_products) == 2
    assert all(row["billing_mode"] == BILLING_MODE_RECURRING for row in plan_products)
    assert all(row["billing_mode"] == BILLING_MODE_ONE_TIME for row in topup_products)
    assert {row["product_code"] for row in BILLING_PRODUCT_SEEDS} == {
        "creator-plan-monthly",
        "creator-plan-yearly",
        "creator-topup-small",
        "creator-topup-large",
    }


def test_billing_product_model_uses_catalog_table_name() -> None:
    assert BillingProduct.__tablename__ == "billing_products"
