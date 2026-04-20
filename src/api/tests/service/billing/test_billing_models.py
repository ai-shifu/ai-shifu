from __future__ import annotations

from datetime import datetime

from flaskr.dao import db
from flaskr.service.billing import consts as billing_consts
from flaskr.service.billing.consts import (
    BILLING_INTERVAL_DAY,
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_YEAR,
    BILL_CONFIG_KEY_CREDIT_PRECISION,
    BILL_CONFIG_KEY_LOW_BALANCE_THRESHOLD,
    BILL_CONFIG_KEY_RATE_VERSION,
    BILL_CONFIG_KEY_RENEWAL_TASK_CONFIG,
    BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE,
    BILLING_TRIAL_PRODUCT_BID,
    BILLING_TRIAL_PRODUCT_CODE,
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,
    BILLING_TRIAL_PRODUCT_METADATA_STARTS_ON_FIRST_GRANT,
    BILLING_TRIAL_PRODUCT_METADATA_VALID_DAYS,
    BILLING_METRIC_LLM_CACHE_TOKENS,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    BILLING_METRIC_TTS_REQUEST_COUNT,
    BILL_SYS_CONFIG_SEEDS,
    CREDIT_USAGE_RATE_SEEDS,
)
from flaskr.service.billing.models import BillingProduct, CreditUsageRate
from flaskr.service.billing.queries import calculate_billing_cycle_end
from flaskr.service.metering import consts as metering_consts
from flaskr.service.promo import consts as promo_consts
from flaskr.service.shifu import consts as shifu_consts
from flaskr.service.user import consts as user_consts


def test_billing_models_register_core_tables() -> None:
    tables = db.metadata.tables

    assert "bill_products" in tables
    assert "bill_subscriptions" in tables
    assert "bill_orders" in tables
    assert "credit_wallets" in tables
    assert "credit_wallet_buckets" in tables
    assert "credit_ledger_entries" in tables

    bill_products = tables["bill_products"]
    assert "product_code" in bill_products.c
    assert "credit_amount" in bill_products.c
    assert bill_products.c.credit_amount.type.precision == 20
    assert bill_products.c.credit_amount.type.scale == 10

    credit_ledger_entries = tables["credit_ledger_entries"]
    assert "wallet_bucket_bid" in credit_ledger_entries.c
    assert "idempotency_key" in credit_ledger_entries.c
    assert credit_ledger_entries.c.amount.type.precision == 20
    assert credit_ledger_entries.c.amount.type.scale == 10


def test_billing_trial_constants_remain_stable() -> None:
    assert BILLING_TRIAL_PRODUCT_BID == "bill-product-plan-trial"
    assert BILLING_TRIAL_PRODUCT_CODE == "creator-plan-trial"
    assert BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG == "public_trial_offer"
    assert BILLING_TRIAL_PRODUCT_METADATA_VALID_DAYS == "trial_valid_days"
    assert BILLING_TRIAL_PRODUCT_METADATA_STARTS_ON_FIRST_GRANT == (
        "starts_on_first_grant"
    )
    assert BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE == "new_creator_v1"


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
    assert BillingProduct.__tablename__ == "bill_products"


def test_calculate_billing_cycle_end_supports_day_month_and_year_intervals() -> None:
    cycle_start = datetime(2026, 4, 16, 12, 0, 0)

    daily_product = BillingProduct(
        billing_interval=BILLING_INTERVAL_DAY,
        billing_interval_count=1,
    )
    weekly_product = BillingProduct(
        billing_interval=BILLING_INTERVAL_DAY,
        billing_interval_count=7,
    )
    monthly_product = BillingProduct(
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=1,
    )
    yearly_product = BillingProduct(
        billing_interval=BILLING_INTERVAL_YEAR,
        billing_interval_count=1,
    )

    assert calculate_billing_cycle_end(
        daily_product,
        cycle_start_at=cycle_start,
    ) == datetime(2026, 4, 17, 12, 0, 0)
    assert calculate_billing_cycle_end(
        weekly_product,
        cycle_start_at=cycle_start,
    ) == datetime(2026, 4, 23, 12, 0, 0)
    assert calculate_billing_cycle_end(
        monthly_product,
        cycle_start_at=cycle_start,
    ) == datetime(2026, 5, 16, 12, 0, 0)
    assert calculate_billing_cycle_end(
        yearly_product,
        cycle_start_at=cycle_start,
    ) == datetime(2027, 4, 16, 12, 0, 0)


def test_credit_usage_rate_model_registers_unique_constraints() -> None:
    unique_constraint_names = {
        constraint.name
        for constraint in CreditUsageRate.__table__.constraints
        if getattr(constraint, "name", None)
    }

    assert "uq_credit_usage_rates_rate_bid" in unique_constraint_names
    assert "uq_credit_usage_rates_lookup" in unique_constraint_names


def test_billing_sys_config_seeds_cover_required_bootstrap_keys() -> None:
    assert len(BILL_SYS_CONFIG_SEEDS) == 4
    assert {row["key"] for row in BILL_SYS_CONFIG_SEEDS} == {
        BILL_CONFIG_KEY_CREDIT_PRECISION,
        BILL_CONFIG_KEY_LOW_BALANCE_THRESHOLD,
        BILL_CONFIG_KEY_RENEWAL_TASK_CONFIG,
        BILL_CONFIG_KEY_RATE_VERSION,
    }
    assert all(row["is_encrypted"] == 0 for row in BILL_SYS_CONFIG_SEEDS)


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
