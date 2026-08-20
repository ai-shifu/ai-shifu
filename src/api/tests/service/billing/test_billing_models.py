"""Verify billing persistence-model behavior."""

from __future__ import annotations

from datetime import datetime

import pytest
from flaskr.dao import db
from flaskr.service.billing import consts as billing_consts
from flaskr.service.billing.consts import (
    BILL_CONFIG_KEY_CREDIT_NOTIFICATION_SMS_CONFIG,
    BILL_CONFIG_KEY_CREDIT_PRECISION,
    BILL_CONFIG_KEY_LOW_BALANCE_THRESHOLD,
    BILL_CONFIG_KEY_RATE_VERSION,
    BILL_CONFIG_KEY_RENEWAL_TASK_CONFIG,
    BILL_SYS_CONFIG_SEEDS,
    BILLING_INTERVAL_DAY,
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_YEAR,
    BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE,
    BILLING_METRIC_LLM_CACHE_TOKENS,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    BILLING_METRIC_TTS_REQUEST_COUNT,
    BILLING_PROVIDER_PRICE_ACTIVE_SCOPE,
    BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
    BILLING_PROVIDER_PRICE_STATUS_DRAFT,
    BILLING_PROVIDER_PRICE_STATUS_INVALID,
    BILLING_PROVIDER_PRICE_STATUS_LABELS,
    BILLING_PROVIDER_PRICE_STATUS_RETIRED,
    BILLING_TRIAL_PRODUCT_BID,
    BILLING_TRIAL_PRODUCT_CODE,
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,
    BILLING_TRIAL_PRODUCT_METADATA_STARTS_ON_FIRST_GRANT,
    BILLING_TRIAL_PRODUCT_METADATA_VALID_DAYS,
    CREDIT_USAGE_RATE_SEEDS,
)
from flaskr.service.billing.models import (
    BillingProduct,
    BillingProductProviderPrice,
    CreditUsageRate,
    NotificationRecord,
)
from flaskr.service.billing.queries import (
    calculate_billing_cycle_end,
    calculate_self_managed_billing_cycle_end,
    calculate_self_managed_billing_cycle_end_after_boundary,
)
from flaskr.service.metering import consts as metering_consts
from flaskr.service.promo import consts as promo_consts
from flaskr.service.shifu import consts as shifu_consts
from flaskr.service.user import consts as user_consts
from sqlalchemy.exc import IntegrityError


def _provider_price(
    *,
    provider_price_bid: str,
    product_bid: str,
    provider_price_id: str,
    provider_product_id: str = "prod_shared",
    status: int = BILLING_PROVIDER_PRICE_STATUS_DRAFT,
) -> BillingProductProviderPrice:
    return BillingProductProviderPrice(
        provider_price_bid=provider_price_bid,
        product_bid=product_bid,
        provider="stripe",
        provider_account_id="acct_test",
        provider_product_id=provider_product_id,
        provider_price_id=provider_price_id,
        livemode=0,
        currency="USD",
        unit_amount=5900,
        billing_mode=billing_consts.BILLING_MODE_RECURRING,
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=1,
        status=status,
    )


def test_billing_models_register_core_tables() -> None:
    tables = db.metadata.tables

    assert "bill_products" in tables
    assert "bill_subscriptions" in tables
    assert "bill_orders" in tables
    assert "bill_product_provider_prices" in tables
    assert "bill_campaigns" in tables
    assert "bill_campaign_products" in tables
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
    assert "campaign_bid" in tables["bill_orders"].c
    assert "expires_at" in tables["bill_orders"].c
    provider_prices = tables["bill_product_provider_prices"]
    assert "provider_product_id" in provider_prices.c
    assert "provider_price_id" in provider_prices.c
    assert "provider_price_live_scope" in provider_prices.c
    assert "active_scope" in provider_prices.c
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


def test_credit_usage_rate_seed_bids_fit_column_and_stay_unique() -> None:
    rate_bid_column_length = CreditUsageRate.rate_bid.type.length
    bids = [row["rate_bid"] for row in CREDIT_USAGE_RATE_SEEDS]

    assert all(len(bid) <= rate_bid_column_length for bid in bids)
    assert len(set(bids)) == len(bids)
    # Legacy non-strict MySQL truncated the original longer bids on insert, so
    # existing rows store 36-char prefixes; seeds must keep matching them.
    assert "credit-rate-llm-production-output-de" in bids
    assert "credit-rate-tts-production-request-d" in bids


def test_billing_product_model_uses_catalog_table_name() -> None:
    assert BillingProduct.__tablename__ == "bill_products"


def test_billing_product_provider_price_model_defines_mapping_constraints() -> None:
    table = BillingProductProviderPrice.__table__
    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.name
    }

    assert BillingProductProviderPrice.__tablename__ == "bill_product_provider_prices"
    assert unique_constraints["uq_bill_product_provider_prices_bid"] == (
        "provider_price_bid",
    )
    assert unique_constraints["uq_bill_product_provider_prices_provider_price"] == (
        "provider",
        "provider_account_id",
        "livemode",
        "provider_price_id",
        "provider_price_live_scope",
    )
    assert unique_constraints["uq_bill_product_provider_prices_active_scope"] == (
        "product_bid",
        "provider",
        "provider_account_id",
        "livemode",
        "active_scope",
    )


def test_billing_provider_price_status_constants_remain_stable() -> None:
    assert BILLING_PROVIDER_PRICE_STATUS_DRAFT == 7901
    assert BILLING_PROVIDER_PRICE_STATUS_ACTIVE == 7902
    assert BILLING_PROVIDER_PRICE_STATUS_RETIRED == 7903
    assert BILLING_PROVIDER_PRICE_STATUS_INVALID == 7904
    assert BILLING_PROVIDER_PRICE_ACTIVE_SCOPE == "active"
    assert BILLING_PROVIDER_PRICE_STATUS_LABELS == {
        BILLING_PROVIDER_PRICE_STATUS_DRAFT: "draft",
        BILLING_PROVIDER_PRICE_STATUS_ACTIVE: "active",
        BILLING_PROVIDER_PRICE_STATUS_RETIRED: "retired",
        BILLING_PROVIDER_PRICE_STATUS_INVALID: "invalid",
    }


def test_provider_price_constraints_allow_shared_product_with_distinct_prices(
    app,
) -> None:
    with app.app_context():
        db.session.add_all(
            [
                _provider_price(
                    provider_price_bid="provider-price-growth-month",
                    product_bid="bill-product-growth-month",
                    provider_price_id="price_growth_month",
                    provider_product_id="prod_growth_shared",
                ),
                _provider_price(
                    provider_price_bid="provider-price-growth-year",
                    product_bid="bill-product-growth-year",
                    provider_price_id="price_growth_year",
                    provider_product_id="prod_growth_shared",
                ),
            ]
        )
        db.session.commit()

        # Scoped to this test's own provider product: the shared default is
        # also written by the other tests here, so querying it would make this
        # assertion depend on which of them ran first.
        rows = BillingProductProviderPrice.query.filter(
            BillingProductProviderPrice.provider_product_id == "prod_growth_shared"
        ).all()
        assert {row.provider_price_id for row in rows} == {
            "price_growth_month",
            "price_growth_year",
        }


def test_provider_price_constraints_reject_duplicate_provider_price(app) -> None:
    with app.app_context():
        db.session.add(
            _provider_price(
                provider_price_bid="provider-price-duplicate-1",
                product_bid="bill-product-duplicate-1",
                provider_price_id="price_duplicate",
            )
        )
        db.session.commit()

        db.session.add(
            _provider_price(
                provider_price_bid="provider-price-duplicate-2",
                product_bid="bill-product-duplicate-2",
                provider_price_id="price_duplicate",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_provider_price_constraints_allow_repeated_soft_delete_lifecycle(app) -> None:
    with app.app_context():
        first = _provider_price(
            provider_price_bid="provider-price-lifecycle-1",
            product_bid="bill-product-lifecycle-1",
            provider_price_id="price_lifecycle",
        )
        db.session.add(first)
        db.session.commit()

        first.deleted = 1
        db.session.commit()

        second = _provider_price(
            provider_price_bid="provider-price-lifecycle-2",
            product_bid="bill-product-lifecycle-2",
            provider_price_id="price_lifecycle",
        )
        db.session.add(second)
        db.session.commit()

        second.deleted = 1
        db.session.commit()

        rows = BillingProductProviderPrice.query.filter(
            BillingProductProviderPrice.provider_price_id == "price_lifecycle"
        ).all()
        assert len(rows) == 2
        assert {row.deleted for row in rows} == {1}


def test_provider_price_constraints_reject_second_active_price_for_sku(app) -> None:
    with app.app_context():
        db.session.add(
            _provider_price(
                provider_price_bid="provider-price-active-1",
                product_bid="bill-product-active-scope",
                provider_price_id="price_active_1",
                status=BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
            )
        )
        db.session.commit()

        db.session.add(
            _provider_price(
                provider_price_bid="provider-price-active-2",
                product_bid="bill-product-active-scope",
                provider_price_id="price_active_2",
                status=BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_provider_price_constraints_allow_multiple_drafts_for_sku(app) -> None:
    with app.app_context():
        db.session.add_all(
            [
                _provider_price(
                    provider_price_bid="provider-price-draft-1",
                    product_bid="bill-product-draft-scope",
                    provider_price_id="price_draft_1",
                ),
                _provider_price(
                    provider_price_bid="provider-price-draft-2",
                    product_bid="bill-product-draft-scope",
                    provider_price_id="price_draft_2",
                ),
            ]
        )
        db.session.commit()

        rows = BillingProductProviderPrice.query.filter(
            BillingProductProviderPrice.product_bid == "bill-product-draft-scope"
        ).all()
        assert {row.provider_price_id for row in rows} == {
            "price_draft_1",
            "price_draft_2",
        }


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


def test_calculate_self_managed_billing_cycle_end_uses_validity_day_end() -> None:
    daily_product = BillingProduct(
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

    assert calculate_self_managed_billing_cycle_end(
        daily_product,
        cycle_start_at=datetime(2026, 4, 16, 12, 0, 0),
    ) == datetime(2026, 4, 22, 15, 59, 59)
    assert calculate_self_managed_billing_cycle_end(
        monthly_product,
        cycle_start_at=datetime(2026, 4, 16, 12, 0, 0),
    ) == datetime(2026, 5, 15, 15, 59, 59)
    assert calculate_self_managed_billing_cycle_end(
        monthly_product,
        cycle_start_at=datetime(2026, 1, 31, 12, 0, 0),
    ) == datetime(2026, 3, 1, 15, 59, 59)
    assert calculate_self_managed_billing_cycle_end(
        yearly_product,
        cycle_start_at=datetime(2026, 4, 16, 12, 0, 0),
    ) == datetime(2027, 4, 16, 15, 59, 59)
    assert calculate_self_managed_billing_cycle_end(
        yearly_product,
        cycle_start_at=datetime(2024, 2, 29, 12, 0, 0),
    ) == datetime(2025, 3, 1, 15, 59, 59)


def test_calculate_self_managed_billing_cycle_end_stores_local_day_end_as_utc_naive() -> (
    None
):
    monthly_product = BillingProduct(
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=1,
    )

    assert calculate_self_managed_billing_cycle_end(
        monthly_product,
        cycle_start_at=datetime(2026, 5, 29, 7, 13, 24),
    ) == datetime(2026, 6, 27, 15, 59, 59)
    assert calculate_self_managed_billing_cycle_end_after_boundary(
        monthly_product,
        cycle_boundary_at=datetime(2026, 6, 27, 15, 59, 59),
    ) == datetime(2026, 7, 27, 15, 59, 59)


def test_credit_usage_rate_model_registers_unique_constraints() -> None:
    unique_constraint_names = {
        constraint.name
        for constraint in CreditUsageRate.__table__.constraints
        if getattr(constraint, "name", None)
    }

    assert "uq_credit_usage_rates_rate_bid" in unique_constraint_names
    assert "uq_credit_usage_rates_lookup" in unique_constraint_names


def test_billing_sys_config_seeds_cover_required_bootstrap_keys() -> None:
    assert len(BILL_SYS_CONFIG_SEEDS) == 5
    assert {row["key"] for row in BILL_SYS_CONFIG_SEEDS} == {
        BILL_CONFIG_KEY_CREDIT_NOTIFICATION_SMS_CONFIG,
        BILL_CONFIG_KEY_CREDIT_PRECISION,
        BILL_CONFIG_KEY_LOW_BALANCE_THRESHOLD,
        BILL_CONFIG_KEY_RENEWAL_TASK_CONFIG,
        BILL_CONFIG_KEY_RATE_VERSION,
    }
    assert all(row["is_encrypted"] == 0 for row in BILL_SYS_CONFIG_SEEDS)


def test_notification_records_model_uses_shared_notification_table() -> None:
    table = NotificationRecord.__table__

    assert NotificationRecord.__tablename__ == "notification_records"
    assert "notification_bid" in table.c
    assert "notification_type" in table.c
    assert "channel" in table.c
    assert "creator_bid" in table.c
    assert "dedupe_key" in table.c
    assert "template_params" in table.c
    assert "policy_snapshot" in table.c
    assert "provider_response" in table.c

    unique_constraint_names = {
        constraint.name
        for constraint in table.constraints
        if getattr(constraint, "name", None)
    }
    assert "uq_notification_records_notification_bid" in unique_constraint_names
    assert "uq_notification_records_dedupe_key" in unique_constraint_names


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
