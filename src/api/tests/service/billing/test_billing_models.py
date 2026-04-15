from __future__ import annotations

from flaskr.dao import db
from flaskr.service.billing import consts as billing_consts
from flaskr.service.billing.consts import (
    BILLING_CONFIG_KEY_CREDIT_PRECISION,
    BILLING_CONFIG_KEY_ENABLED,
    BILLING_CONFIG_KEY_LOW_BALANCE_THRESHOLD,
    BILLING_CONFIG_KEY_RATE_VERSION,
    BILLING_CONFIG_KEY_RENEWAL_TASK_CONFIG,
    BILLING_MODE_MANUAL,
    BILLING_MODE_ONE_TIME,
    BILLING_MODE_RECURRING,
    BILLING_PRODUCT_SEEDS,
    BILLING_TRIAL_PRODUCT_CODE,
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_METRIC_LLM_CACHE_TOKENS,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    BILLING_METRIC_TTS_REQUEST_COUNT,
    BILLING_SYS_CONFIG_SEEDS,
    CREDIT_USAGE_RATE_SEEDS,
)
from flaskr.service.billing.models import BillingProduct, CreditUsageRate
from flaskr.service.metering import consts as metering_consts
from flaskr.service.promo import consts as promo_consts
from flaskr.service.shifu import consts as shifu_consts
from flaskr.service.user import consts as user_consts


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
    assert len(BILLING_PRODUCT_SEEDS) == 10

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
    trial_product = next(
        row
        for row in BILLING_PRODUCT_SEEDS
        if row["product_code"] == BILLING_TRIAL_PRODUCT_CODE
    )

    assert len(plan_products) == 6
    assert len(topup_products) == 4
    paid_plan_products = [
        row
        for row in plan_products
        if row["product_code"] != BILLING_TRIAL_PRODUCT_CODE
    ]
    assert all(
        row["billing_mode"] == BILLING_MODE_RECURRING for row in paid_plan_products
    )
    assert all(row["billing_mode"] == BILLING_MODE_ONE_TIME for row in topup_products)
    assert trial_product["billing_mode"] == BILLING_MODE_MANUAL
    assert trial_product["price_amount"] == 0
    assert trial_product["metadata"][BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG] is True
    assert {row["product_code"] for row in BILLING_PRODUCT_SEEDS} == {
        BILLING_TRIAL_PRODUCT_CODE,
        "creator-plan-monthly",
        "creator-plan-monthly-pro",
        "creator-plan-yearly",
        "creator-plan-yearly-lite",
        "creator-plan-yearly-premium",
        "creator-topup-small",
        "creator-topup-medium",
        "creator-topup-large",
        "creator-topup-xlarge",
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


def test_billing_sys_config_seeds_cover_required_bootstrap_keys() -> None:
    assert len(BILLING_SYS_CONFIG_SEEDS) == 5
    assert {row["key"] for row in BILLING_SYS_CONFIG_SEEDS} == {
        BILLING_CONFIG_KEY_CREDIT_PRECISION,
        BILLING_CONFIG_KEY_ENABLED,
        BILLING_CONFIG_KEY_LOW_BALANCE_THRESHOLD,
        BILLING_CONFIG_KEY_RENEWAL_TASK_CONFIG,
        BILLING_CONFIG_KEY_RATE_VERSION,
    }
    assert all(row["is_encrypted"] == 0 for row in BILLING_SYS_CONFIG_SEEDS)


def test_billing_consts_keep_7100_segment_isolated_and_reuse_metering_usage_codes() -> (
    None
):
    billing_segment_values = {
        value
        for name, value in vars(billing_consts).items()
        if name.isupper() and isinstance(value, int) and 7100 <= value < 7600
    }

    assert billing_consts.BILL_USAGE_TYPE_LLM == metering_consts.BILL_USAGE_TYPE_LLM
    assert billing_consts.BILL_USAGE_TYPE_TTS == metering_consts.BILL_USAGE_TYPE_TTS
    assert (
        billing_consts.BILL_USAGE_SCENE_DEBUG == metering_consts.BILL_USAGE_SCENE_DEBUG
    )
    assert (
        billing_consts.BILL_USAGE_SCENE_PREVIEW
        == metering_consts.BILL_USAGE_SCENE_PREVIEW
    )
    assert billing_consts.BILL_USAGE_SCENE_PROD == metering_consts.BILL_USAGE_SCENE_PROD

    for module in (user_consts, promo_consts, shifu_consts, metering_consts):
        module_values = {
            value
            for name, value in vars(module).items()
            if name.isupper() and isinstance(value, int)
        }
        assert not (billing_segment_values & module_values)
