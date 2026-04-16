from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any, Iterable, Mapping

from flaskr.service.billing.consts import (
    ALLOCATION_INTERVAL_MANUAL,
    ALLOCATION_INTERVAL_ONE_TIME,
    ALLOCATION_INTERVAL_PER_CYCLE,
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_NONE,
    BILLING_INTERVAL_YEAR,
    BILLING_MODE_MANUAL,
    BILLING_MODE_ONE_TIME,
    BILLING_MODE_RECURRING,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_TRIAL_PRODUCT_BID,
    BILLING_TRIAL_PRODUCT_CODE,
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,
    BILLING_TRIAL_PRODUCT_METADATA_STARTS_ON_FIRST_GRANT,
    BILLING_TRIAL_PRODUCT_METADATA_VALID_DAYS,
)
from flaskr.service.billing.models import BillingProduct

_CANONICAL_BILLING_PRODUCT_ROWS: tuple[dict[str, Any], ...] = (
    {
        "product_bid": BILLING_TRIAL_PRODUCT_BID,
        "product_code": BILLING_TRIAL_PRODUCT_CODE,
        "product_type": BILLING_PRODUCT_TYPE_PLAN,
        "billing_mode": BILLING_MODE_MANUAL,
        "billing_interval": BILLING_INTERVAL_NONE,
        "billing_interval_count": 0,
        "display_name_i18n_key": "module.billing.package.free.title",
        "description_i18n_key": "module.billing.package.free.description",
        "currency": "CNY",
        "price_amount": 0,
        "credit_amount": Decimal("100.0000000000"),
        "allocation_interval": ALLOCATION_INTERVAL_MANUAL,
        "auto_renew_enabled": 0,
        "entitlement_payload": None,
        "metadata": {
            BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG: True,
            BILLING_TRIAL_PRODUCT_METADATA_VALID_DAYS: 15,
            BILLING_TRIAL_PRODUCT_METADATA_STARTS_ON_FIRST_GRANT: True,
            "highlights": [
                "module.billing.package.features.free.publish",
                "module.billing.package.features.free.preview",
            ],
        },
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
        "sort_order": 5,
    },
    {
        "product_bid": "billing-product-plan-monthly",
        "product_code": "creator-plan-monthly",
        "product_type": BILLING_PRODUCT_TYPE_PLAN,
        "billing_mode": BILLING_MODE_RECURRING,
        "billing_interval": BILLING_INTERVAL_MONTH,
        "billing_interval_count": 1,
        "display_name_i18n_key": "module.billing.catalog.plans.creatorMonthly.title",
        "description_i18n_key": "module.billing.catalog.plans.creatorMonthly.description",
        "currency": "CNY",
        "price_amount": 990,
        "credit_amount": Decimal("5.0000000000"),
        "allocation_interval": ALLOCATION_INTERVAL_PER_CYCLE,
        "auto_renew_enabled": 1,
        "entitlement_payload": None,
        "metadata": {
            "highlights": [
                "module.billing.package.features.monthly.publish",
                "module.billing.package.features.monthly.preview",
            ]
        },
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
        "sort_order": 10,
    },
    {
        "product_bid": "billing-product-plan-monthly-pro",
        "product_code": "creator-plan-monthly-pro",
        "product_type": BILLING_PRODUCT_TYPE_PLAN,
        "billing_mode": BILLING_MODE_RECURRING,
        "billing_interval": BILLING_INTERVAL_MONTH,
        "billing_interval_count": 1,
        "display_name_i18n_key": "module.billing.catalog.plans.creatorMonthlyPro.title",
        "description_i18n_key": "module.billing.catalog.plans.creatorMonthlyPro.description",
        "currency": "CNY",
        "price_amount": 19900,
        "credit_amount": Decimal("100.0000000000"),
        "allocation_interval": ALLOCATION_INTERVAL_PER_CYCLE,
        "auto_renew_enabled": 1,
        "entitlement_payload": None,
        "metadata": {
            "badge": "recommended",
            "highlights": [
                "module.billing.package.features.monthly.publish",
                "module.billing.package.features.monthly.preview",
                "module.billing.package.features.monthly.support",
            ],
        },
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
        "sort_order": 20,
    },
    {
        "product_bid": "billing-product-plan-yearly-lite",
        "product_code": "creator-plan-yearly-lite",
        "product_type": BILLING_PRODUCT_TYPE_PLAN,
        "billing_mode": BILLING_MODE_RECURRING,
        "billing_interval": BILLING_INTERVAL_YEAR,
        "billing_interval_count": 1,
        "display_name_i18n_key": "module.billing.catalog.plans.creatorYearlyLite.title",
        "description_i18n_key": "module.billing.catalog.plans.creatorYearlyLite.description",
        "currency": "CNY",
        "price_amount": 800000,
        "credit_amount": Decimal("5000.0000000000"),
        "allocation_interval": ALLOCATION_INTERVAL_PER_CYCLE,
        "auto_renew_enabled": 1,
        "entitlement_payload": None,
        "metadata": {
            "highlights": [
                "module.billing.package.features.yearly.lite.ops",
                "module.billing.package.features.yearly.lite.publish",
            ]
        },
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
        "sort_order": 30,
    },
    {
        "product_bid": "billing-product-plan-yearly",
        "product_code": "creator-plan-yearly",
        "product_type": BILLING_PRODUCT_TYPE_PLAN,
        "billing_mode": BILLING_MODE_RECURRING,
        "billing_interval": BILLING_INTERVAL_YEAR,
        "billing_interval_count": 1,
        "display_name_i18n_key": "module.billing.catalog.plans.creatorYearly.title",
        "description_i18n_key": "module.billing.catalog.plans.creatorYearly.description",
        "currency": "CNY",
        "price_amount": 1500000,
        "credit_amount": Decimal("10000.0000000000"),
        "allocation_interval": ALLOCATION_INTERVAL_PER_CYCLE,
        "auto_renew_enabled": 1,
        "entitlement_payload": None,
        "metadata": {
            "highlights": [
                "module.billing.package.features.yearly.pro.branding",
                "module.billing.package.features.yearly.pro.domain",
                "module.billing.package.features.yearly.pro.priority",
                "module.billing.package.features.yearly.pro.analytics",
                "module.billing.package.features.yearly.pro.support",
            ]
        },
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
        "sort_order": 40,
    },
    {
        "product_bid": "billing-product-plan-yearly-premium",
        "product_code": "creator-plan-yearly-premium",
        "product_type": BILLING_PRODUCT_TYPE_PLAN,
        "billing_mode": BILLING_MODE_RECURRING,
        "billing_interval": BILLING_INTERVAL_YEAR,
        "billing_interval_count": 1,
        "display_name_i18n_key": "module.billing.catalog.plans.creatorYearlyPremium.title",
        "description_i18n_key": "module.billing.catalog.plans.creatorYearlyPremium.description",
        "currency": "CNY",
        "price_amount": 3000000,
        "credit_amount": Decimal("22000.0000000000"),
        "allocation_interval": ALLOCATION_INTERVAL_PER_CYCLE,
        "auto_renew_enabled": 1,
        "entitlement_payload": None,
        "metadata": {
            "badge": "best_value",
            "highlights": [
                "module.billing.package.features.yearly.premium.branding",
                "module.billing.package.features.yearly.premium.domain",
                "module.billing.package.features.yearly.premium.priority",
                "module.billing.package.features.yearly.premium.analytics",
                "module.billing.package.features.yearly.premium.support",
            ],
        },
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
        "sort_order": 50,
    },
    {
        "product_bid": "billing-product-topup-small",
        "product_code": "creator-topup-small",
        "product_type": BILLING_PRODUCT_TYPE_TOPUP,
        "billing_mode": BILLING_MODE_ONE_TIME,
        "billing_interval": BILLING_INTERVAL_NONE,
        "billing_interval_count": 0,
        "display_name_i18n_key": "module.billing.catalog.topups.creatorSmall.title",
        "description_i18n_key": "module.billing.catalog.topups.creatorSmall.description",
        "currency": "CNY",
        "price_amount": 5000,
        "credit_amount": Decimal("20.0000000000"),
        "allocation_interval": ALLOCATION_INTERVAL_ONE_TIME,
        "auto_renew_enabled": 0,
        "entitlement_payload": None,
        "metadata": None,
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
        "sort_order": 60,
    },
    {
        "product_bid": "billing-product-topup-medium",
        "product_code": "creator-topup-medium",
        "product_type": BILLING_PRODUCT_TYPE_TOPUP,
        "billing_mode": BILLING_MODE_ONE_TIME,
        "billing_interval": BILLING_INTERVAL_NONE,
        "billing_interval_count": 0,
        "display_name_i18n_key": "module.billing.catalog.topups.creatorMedium.title",
        "description_i18n_key": "module.billing.catalog.topups.creatorMedium.description",
        "currency": "CNY",
        "price_amount": 9900,
        "credit_amount": Decimal("50.0000000000"),
        "allocation_interval": ALLOCATION_INTERVAL_ONE_TIME,
        "auto_renew_enabled": 0,
        "entitlement_payload": None,
        "metadata": None,
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
        "sort_order": 70,
    },
    {
        "product_bid": "billing-product-topup-large",
        "product_code": "creator-topup-large",
        "product_type": BILLING_PRODUCT_TYPE_TOPUP,
        "billing_mode": BILLING_MODE_ONE_TIME,
        "billing_interval": BILLING_INTERVAL_NONE,
        "billing_interval_count": 0,
        "display_name_i18n_key": "module.billing.catalog.topups.creatorLarge.title",
        "description_i18n_key": "module.billing.catalog.topups.creatorLarge.description",
        "currency": "CNY",
        "price_amount": 19900,
        "credit_amount": Decimal("120.0000000000"),
        "allocation_interval": ALLOCATION_INTERVAL_ONE_TIME,
        "auto_renew_enabled": 0,
        "entitlement_payload": None,
        "metadata": None,
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
        "sort_order": 80,
    },
    {
        "product_bid": "billing-product-topup-xlarge",
        "product_code": "creator-topup-xlarge",
        "product_type": BILLING_PRODUCT_TYPE_TOPUP,
        "billing_mode": BILLING_MODE_ONE_TIME,
        "billing_interval": BILLING_INTERVAL_NONE,
        "billing_interval_count": 0,
        "display_name_i18n_key": "module.billing.catalog.topups.creatorXLarge.title",
        "description_i18n_key": "module.billing.catalog.topups.creatorXLarge.description",
        "currency": "CNY",
        "price_amount": 49900,
        "credit_amount": Decimal("320.0000000000"),
        "allocation_interval": ALLOCATION_INTERVAL_ONE_TIME,
        "auto_renew_enabled": 0,
        "entitlement_payload": None,
        "metadata": {"badge": "best_value"},
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
        "sort_order": 90,
    },
)

_BILLING_PRODUCT_ROWS_BY_BID = {
    str(row["product_bid"]): row for row in _CANONICAL_BILLING_PRODUCT_ROWS
}


def list_billing_product_rows(
    *,
    product_bids: Iterable[str] | None = None,
    overrides_by_bid: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    selected_bids = (
        tuple(str(product_bid) for product_bid in product_bids)
        if product_bids is not None
        else tuple(_BILLING_PRODUCT_ROWS_BY_BID.keys())
    )

    rows: list[dict[str, Any]] = []
    for product_bid in selected_bids:
        base_row = _BILLING_PRODUCT_ROWS_BY_BID.get(product_bid)
        if base_row is None:
            raise AssertionError(f"unknown billing product fixture: {product_bid}")

        payload = deepcopy(base_row)
        if overrides_by_bid and product_bid in overrides_by_bid:
            for key, value in overrides_by_bid[product_bid].items():
                payload[key] = deepcopy(value)
        rows.append(payload)
    return rows


def build_billing_products(
    *,
    product_bids: Iterable[str] | None = None,
    overrides_by_bid: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[BillingProduct]:
    products: list[BillingProduct] = []
    for row in list_billing_product_rows(
        product_bids=product_bids,
        overrides_by_bid=overrides_by_bid,
    ):
        payload = dict(row)
        payload["metadata_json"] = payload.pop("metadata", None)
        products.append(BillingProduct(**payload))
    return products


def build_billing_product(
    product_bid: str,
    *,
    overrides: Mapping[str, Any] | None = None,
) -> BillingProduct:
    overrides_by_bid = {product_bid: dict(overrides)} if overrides is not None else None
    return build_billing_products(
        product_bids=[product_bid],
        overrides_by_bid=overrides_by_bid,
    )[0]
