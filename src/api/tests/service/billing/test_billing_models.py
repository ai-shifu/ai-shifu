from __future__ import annotations

from flaskr.dao import db
from flaskr.service.billing.consts import (
    BILLING_MODE_ONE_TIME,
    BILLING_MODE_RECURRING,
    BILLING_PRODUCT_SEEDS,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_METRIC_LLM_CACHE_TOKENS,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    BILLING_METRIC_TTS_REQUEST_COUNT,
    CREDIT_USAGE_RATE_SEEDS,
)
from flaskr.service.billing.models import BillingProduct, CreditUsageRate


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


def test_credit_usage_rate_seeds_cover_all_scenes_with_bootstrap_defaults() -> None:
    assert len(CREDIT_USAGE_RATE_SEEDS) == 12
    assert {row["provider"] for row in CREDIT_USAGE_RATE_SEEDS} == {"*"}
    assert {row["model"] for row in CREDIT_USAGE_RATE_SEEDS} == {"*"}
    assert {row["usage_scene"] for row in CREDIT_USAGE_RATE_SEEDS} == {
        1201,
        1202,
        1203,
    }
    assert {row["billing_metric"] for row in CREDIT_USAGE_RATE_SEEDS} == {
        BILLING_METRIC_LLM_INPUT_TOKENS,
        BILLING_METRIC_LLM_CACHE_TOKENS,
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        BILLING_METRIC_TTS_REQUEST_COUNT,
    }
    assert all(row["credits_per_unit"] == 0 for row in CREDIT_USAGE_RATE_SEEDS)


def test_billing_product_model_uses_catalog_table_name() -> None:
    assert BillingProduct.__tablename__ == "billing_products"


def test_credit_usage_rate_model_registers_unique_constraints() -> None:
    unique_constraint_names = {
        constraint.name
        for constraint in CreditUsageRate.__table__.constraints
        if getattr(constraint, "name", None)
    }

    assert "uq_credit_usage_rates_rate_bid" in unique_constraint_names
    assert "uq_credit_usage_rates_lookup" in unique_constraint_names
