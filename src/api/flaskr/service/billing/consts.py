"""Billing domain constants and seed catalog definitions."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping

from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILL_USAGE_TYPE_TTS,
)

BILLING_PRODUCT_TYPE_PLAN = 7111
BILLING_PRODUCT_TYPE_TOPUP = 7112
BILLING_PRODUCT_TYPE_GRANT = 7113
BILLING_PRODUCT_TYPE_CUSTOM = 7114

BILLING_MODE_RECURRING = 7121
BILLING_MODE_ONE_TIME = 7122
BILLING_MODE_MANUAL = 7123

BILLING_INTERVAL_NONE = 7131
BILLING_INTERVAL_MONTH = 7132
BILLING_INTERVAL_YEAR = 7133
BILLING_INTERVAL_DAY = 7134

ALLOCATION_INTERVAL_PER_CYCLE = 7141
ALLOCATION_INTERVAL_ONE_TIME = 7142
ALLOCATION_INTERVAL_MANUAL = 7143

BILLING_PRODUCT_STATUS_ACTIVE = 7151
BILLING_PRODUCT_STATUS_INACTIVE = 7152

BILLING_SUBSCRIPTION_STATUS_DRAFT = 7201
BILLING_SUBSCRIPTION_STATUS_ACTIVE = 7202
BILLING_SUBSCRIPTION_STATUS_PAST_DUE = 7203
BILLING_SUBSCRIPTION_STATUS_PAUSED = 7204
BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED = 7205
BILLING_SUBSCRIPTION_STATUS_CANCELED = 7206
BILLING_SUBSCRIPTION_STATUS_EXPIRED = 7207

BILLING_ORDER_TYPE_SUBSCRIPTION_START = 7301
BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE = 7302
BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL = 7303
BILLING_ORDER_TYPE_TOPUP = 7304
BILLING_ORDER_TYPE_MANUAL = 7305
BILLING_ORDER_TYPE_REFUND = 7306

BILLING_ORDER_STATUS_INIT = 7311
BILLING_ORDER_STATUS_PENDING = 7312
BILLING_ORDER_STATUS_PAID = 7313
BILLING_ORDER_STATUS_FAILED = 7314
BILLING_ORDER_STATUS_REFUNDED = 7315
BILLING_ORDER_STATUS_CANCELED = 7316
BILLING_ORDER_STATUS_TIMEOUT = 7317

CREDIT_LEDGER_ENTRY_TYPE_GRANT = 7401
CREDIT_LEDGER_ENTRY_TYPE_CONSUME = 7402
CREDIT_LEDGER_ENTRY_TYPE_REFUND = 7403
CREDIT_LEDGER_ENTRY_TYPE_EXPIRE = 7404
CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT = 7405
CREDIT_LEDGER_ENTRY_TYPE_HOLD = 7406
CREDIT_LEDGER_ENTRY_TYPE_RELEASE = 7407

CREDIT_SOURCE_TYPE_SUBSCRIPTION = 7411
CREDIT_SOURCE_TYPE_TOPUP = 7412
CREDIT_SOURCE_TYPE_GIFT = 7413
CREDIT_SOURCE_TYPE_USAGE = 7414
CREDIT_SOURCE_TYPE_REFUND = 7415
CREDIT_SOURCE_TYPE_MANUAL = 7416

CREDIT_ROUNDING_MODE_CEIL = 7421
CREDIT_ROUNDING_MODE_FLOOR = 7422
CREDIT_ROUNDING_MODE_ROUND = 7423

BILLING_METRIC_LLM_INPUT_TOKENS = 7451
BILLING_METRIC_LLM_CACHE_TOKENS = 7452
BILLING_METRIC_LLM_OUTPUT_TOKENS = 7453
BILLING_METRIC_TTS_REQUEST_COUNT = 7454
BILLING_METRIC_TTS_OUTPUT_CHARS = 7455
BILLING_METRIC_TTS_INPUT_CHARS = 7456

CREDIT_BUCKET_CATEGORY_FREE = 7431
CREDIT_BUCKET_CATEGORY_SUBSCRIPTION = 7432
CREDIT_BUCKET_CATEGORY_TOPUP = 7433

CREDIT_BUCKET_STATUS_ACTIVE = 7441
CREDIT_BUCKET_STATUS_EXHAUSTED = 7442
CREDIT_BUCKET_STATUS_EXPIRED = 7443
CREDIT_BUCKET_STATUS_CANCELED = 7444

CREDIT_USAGE_RATE_STATUS_ACTIVE = BILLING_PRODUCT_STATUS_ACTIVE
CREDIT_USAGE_RATE_STATUS_INACTIVE = BILLING_PRODUCT_STATUS_INACTIVE

BILLING_RENEWAL_EVENT_TYPE_RENEWAL = 7501
BILLING_RENEWAL_EVENT_TYPE_RETRY = 7502
BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE = 7503
BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE = 7504
BILLING_RENEWAL_EVENT_TYPE_EXPIRE = 7505
BILLING_RENEWAL_EVENT_TYPE_RECONCILE = 7506

BILLING_RENEWAL_EVENT_STATUS_PENDING = 7511
BILLING_RENEWAL_EVENT_STATUS_PROCESSING = 7512
BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED = 7513
BILLING_RENEWAL_EVENT_STATUS_FAILED = 7514
BILLING_RENEWAL_EVENT_STATUS_CANCELED = 7515

BILLING_DOMAIN_BINDING_STATUS_PENDING = 7601
BILLING_DOMAIN_BINDING_STATUS_VERIFIED = 7602
BILLING_DOMAIN_BINDING_STATUS_FAILED = 7603
BILLING_DOMAIN_BINDING_STATUS_DISABLED = 7604

BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT = 7611
BILLING_DOMAIN_VERIFICATION_METHOD_CNAME = 7612
BILLING_DOMAIN_VERIFICATION_METHOD_FILE = 7613

BILLING_DOMAIN_SSL_STATUS_NOT_REQUESTED = 7621
BILLING_DOMAIN_SSL_STATUS_PROVISIONING = 7622
BILLING_DOMAIN_SSL_STATUS_ACTIVE = 7623
BILLING_DOMAIN_SSL_STATUS_FAILED = 7624

BILLING_ENTITLEMENT_PRIORITY_CLASS_STANDARD = 7701
BILLING_ENTITLEMENT_PRIORITY_CLASS_PRIORITY = 7702
BILLING_ENTITLEMENT_PRIORITY_CLASS_VIP = 7703

BILLING_ENTITLEMENT_ANALYTICS_TIER_BASIC = 7711
BILLING_ENTITLEMENT_ANALYTICS_TIER_ADVANCED = 7712
BILLING_ENTITLEMENT_ANALYTICS_TIER_ENTERPRISE = 7713

BILLING_ENTITLEMENT_SUPPORT_TIER_SELF_SERVE = 7721
BILLING_ENTITLEMENT_SUPPORT_TIER_BUSINESS_HOURS = 7722
BILLING_ENTITLEMENT_SUPPORT_TIER_PRIORITY = 7723


BILLING_PRODUCT_TYPE_LABELS = {
    BILLING_PRODUCT_TYPE_PLAN: "plan",
    BILLING_PRODUCT_TYPE_TOPUP: "topup",
    BILLING_PRODUCT_TYPE_GRANT: "grant",
    BILLING_PRODUCT_TYPE_CUSTOM: "custom",
}

BILLING_INTERVAL_LABELS = {
    BILLING_INTERVAL_NONE: "none",
    BILLING_INTERVAL_DAY: "day",
    BILLING_INTERVAL_MONTH: "month",
    BILLING_INTERVAL_YEAR: "year",
}

BILLING_SUBSCRIPTION_STATUS_LABELS = {
    BILLING_SUBSCRIPTION_STATUS_DRAFT: "draft",
    BILLING_SUBSCRIPTION_STATUS_ACTIVE: "active",
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE: "past_due",
    BILLING_SUBSCRIPTION_STATUS_PAUSED: "paused",
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED: "cancel_scheduled",
    BILLING_SUBSCRIPTION_STATUS_CANCELED: "canceled",
    BILLING_SUBSCRIPTION_STATUS_EXPIRED: "expired",
}

BILLING_ORDER_TYPE_LABELS = {
    BILLING_ORDER_TYPE_SUBSCRIPTION_START: "subscription_start",
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE: "subscription_upgrade",
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL: "subscription_renewal",
    BILLING_ORDER_TYPE_TOPUP: "topup",
    BILLING_ORDER_TYPE_MANUAL: "manual",
    BILLING_ORDER_TYPE_REFUND: "refund",
}

BILLING_ORDER_STATUS_LABELS = {
    BILLING_ORDER_STATUS_INIT: "init",
    BILLING_ORDER_STATUS_PENDING: "pending",
    BILLING_ORDER_STATUS_PAID: "paid",
    BILLING_ORDER_STATUS_FAILED: "failed",
    BILLING_ORDER_STATUS_REFUNDED: "refunded",
    BILLING_ORDER_STATUS_CANCELED: "canceled",
    BILLING_ORDER_STATUS_TIMEOUT: "timeout",
}

CREDIT_LEDGER_ENTRY_TYPE_LABELS = {
    CREDIT_LEDGER_ENTRY_TYPE_GRANT: "grant",
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME: "consume",
    CREDIT_LEDGER_ENTRY_TYPE_REFUND: "refund",
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE: "expire",
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT: "adjustment",
    CREDIT_LEDGER_ENTRY_TYPE_HOLD: "hold",
    CREDIT_LEDGER_ENTRY_TYPE_RELEASE: "release",
}

CREDIT_SOURCE_TYPE_LABELS = {
    CREDIT_SOURCE_TYPE_SUBSCRIPTION: "subscription",
    CREDIT_SOURCE_TYPE_TOPUP: "topup",
    CREDIT_SOURCE_TYPE_GIFT: "gift",
    CREDIT_SOURCE_TYPE_USAGE: "usage",
    CREDIT_SOURCE_TYPE_REFUND: "refund",
    CREDIT_SOURCE_TYPE_MANUAL: "manual",
}

BILLING_METRIC_LABELS = {
    BILLING_METRIC_LLM_INPUT_TOKENS: "llm_input_tokens",
    BILLING_METRIC_LLM_CACHE_TOKENS: "llm_cache_tokens",
    BILLING_METRIC_LLM_OUTPUT_TOKENS: "llm_output_tokens",
    BILLING_METRIC_TTS_REQUEST_COUNT: "tts_request_count",
    BILLING_METRIC_TTS_OUTPUT_CHARS: "tts_output_chars",
    BILLING_METRIC_TTS_INPUT_CHARS: "tts_input_chars",
}

CREDIT_BUCKET_CATEGORY_LABELS = {
    CREDIT_BUCKET_CATEGORY_FREE: "free",
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION: "subscription",
    CREDIT_BUCKET_CATEGORY_TOPUP: "topup",
}

CREDIT_BUCKET_STATUS_LABELS = {
    CREDIT_BUCKET_STATUS_ACTIVE: "active",
    CREDIT_BUCKET_STATUS_EXHAUSTED: "exhausted",
    CREDIT_BUCKET_STATUS_EXPIRED: "expired",
    CREDIT_BUCKET_STATUS_CANCELED: "canceled",
}

CREDIT_USAGE_RATE_STATUS_LABELS = {
    CREDIT_USAGE_RATE_STATUS_ACTIVE: "active",
    CREDIT_USAGE_RATE_STATUS_INACTIVE: "inactive",
}

BILLING_RENEWAL_EVENT_TYPE_LABELS = {
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL: "renewal",
    BILLING_RENEWAL_EVENT_TYPE_RETRY: "retry",
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE: "cancel_effective",
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE: "downgrade_effective",
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE: "expire",
    BILLING_RENEWAL_EVENT_TYPE_RECONCILE: "reconcile",
}

BILLING_RENEWAL_EVENT_STATUS_LABELS = {
    BILLING_RENEWAL_EVENT_STATUS_PENDING: "pending",
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING: "processing",
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED: "succeeded",
    BILLING_RENEWAL_EVENT_STATUS_FAILED: "failed",
    BILLING_RENEWAL_EVENT_STATUS_CANCELED: "canceled",
}

BILLING_DOMAIN_BINDING_STATUS_LABELS = {
    BILLING_DOMAIN_BINDING_STATUS_PENDING: "pending",
    BILLING_DOMAIN_BINDING_STATUS_VERIFIED: "verified",
    BILLING_DOMAIN_BINDING_STATUS_FAILED: "failed",
    BILLING_DOMAIN_BINDING_STATUS_DISABLED: "disabled",
}

BILLING_DOMAIN_VERIFICATION_METHOD_LABELS = {
    BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT: "dns_txt",
    BILLING_DOMAIN_VERIFICATION_METHOD_CNAME: "cname",
    BILLING_DOMAIN_VERIFICATION_METHOD_FILE: "file",
}

BILLING_DOMAIN_SSL_STATUS_LABELS = {
    BILLING_DOMAIN_SSL_STATUS_NOT_REQUESTED: "not_requested",
    BILLING_DOMAIN_SSL_STATUS_PROVISIONING: "provisioning",
    BILLING_DOMAIN_SSL_STATUS_ACTIVE: "active",
    BILLING_DOMAIN_SSL_STATUS_FAILED: "failed",
}

BILLING_ENTITLEMENT_PRIORITY_CLASS_LABELS = {
    BILLING_ENTITLEMENT_PRIORITY_CLASS_STANDARD: "standard",
    BILLING_ENTITLEMENT_PRIORITY_CLASS_PRIORITY: "priority",
    BILLING_ENTITLEMENT_PRIORITY_CLASS_VIP: "vip",
}

BILLING_ENTITLEMENT_ANALYTICS_TIER_LABELS = {
    BILLING_ENTITLEMENT_ANALYTICS_TIER_BASIC: "basic",
    BILLING_ENTITLEMENT_ANALYTICS_TIER_ADVANCED: "advanced",
    BILLING_ENTITLEMENT_ANALYTICS_TIER_ENTERPRISE: "enterprise",
}

BILLING_ENTITLEMENT_SUPPORT_TIER_LABELS = {
    BILLING_ENTITLEMENT_SUPPORT_TIER_SELF_SERVE: "self_serve",
    BILLING_ENTITLEMENT_SUPPORT_TIER_BUSINESS_HOURS: "business_hours",
    BILLING_ENTITLEMENT_SUPPORT_TIER_PRIORITY: "priority",
}

BILLING_TRIAL_PRODUCT_BID = "bill-product-plan-trial"
BILLING_TRIAL_PRODUCT_CODE = "creator-plan-trial"
BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG = "public_trial_offer"
BILLING_TRIAL_PRODUCT_METADATA_VALID_DAYS = "trial_valid_days"
BILLING_TRIAL_PRODUCT_METADATA_STARTS_ON_FIRST_GRANT = "starts_on_first_grant"
BILLING_LEGACY_NEW_CREATOR_TRIAL_PROGRAM_CODE = "new_creator_v1"

BILL_CONFIG_KEY_ENABLED = "BILL_ENABLED"
BILL_CONFIG_KEY_CREDIT_PRECISION = "BILL_CREDIT_PRECISION"
BILL_CONFIG_KEY_LOW_BALANCE_THRESHOLD = "BILL_LOW_BALANCE_THRESHOLD"
BILL_CONFIG_KEY_RENEWAL_TASK_CONFIG = "BILL_RENEWAL_TASK_CONFIG"
BILL_CONFIG_KEY_RATE_VERSION = "BILL_RATE_VERSION"


BILLING_BOOTSTRAP_PRODUCT_ROWS: tuple[dict[str, Any], ...] = (
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
        "deleted": 0,
    },
    {
        "product_bid": "bill-product-plan-monthly",
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
        "deleted": 0,
    },
    {
        "product_bid": "bill-product-plan-monthly-pro",
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
        "deleted": 0,
    },
    {
        "product_bid": "bill-product-plan-yearly-lite",
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
        "deleted": 0,
    },
    {
        "product_bid": "bill-product-plan-yearly",
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
        "deleted": 0,
    },
    {
        "product_bid": "bill-product-plan-yearly-premium",
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
        "deleted": 0,
    },
    {
        "product_bid": "bill-product-topup-small",
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
        "deleted": 0,
    },
    {
        "product_bid": "bill-product-topup-medium",
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
        "deleted": 0,
    },
    {
        "product_bid": "bill-product-topup-large",
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
        "deleted": 0,
    },
    {
        "product_bid": "bill-product-topup-xlarge",
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
        "deleted": 0,
    },
)

_BILLING_BOOTSTRAP_PRODUCT_ROWS_BY_BID = {
    str(row["product_bid"]): row for row in BILLING_BOOTSTRAP_PRODUCT_ROWS
}


def list_billing_bootstrap_product_rows(
    *,
    product_bids: Iterable[str] | None = None,
    overrides_by_bid: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    selected_bids = (
        tuple(str(product_bid) for product_bid in product_bids)
        if product_bids is not None
        else tuple(_BILLING_BOOTSTRAP_PRODUCT_ROWS_BY_BID.keys())
    )

    rows: list[dict[str, Any]] = []
    for product_bid in selected_bids:
        base_row = _BILLING_BOOTSTRAP_PRODUCT_ROWS_BY_BID.get(product_bid)
        if base_row is None:
            raise AssertionError(f"unknown billing product seed: {product_bid}")

        payload = deepcopy(base_row)
        if overrides_by_bid and product_bid in overrides_by_bid:
            for key, value in overrides_by_bid[product_bid].items():
                payload[key] = deepcopy(value)
        rows.append(payload)
    return rows


@dataclass(slots=True, frozen=True)
class CreditUsageRateSeed:
    rate_bid: str
    usage_type: int
    provider: str
    model: str
    usage_scene: int
    billing_metric: int
    unit_size: int
    credits_per_unit: Decimal
    rounding_mode: int
    effective_from: datetime
    effective_to: datetime | None
    status: int

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


def _build_credit_usage_rate_seeds() -> tuple[CreditUsageRateSeed, ...]:
    seeds: list[CreditUsageRateSeed] = []
    effective_from = datetime(2026, 1, 1, 0, 0, 0)
    scene_specs = (
        ("debug", BILL_USAGE_SCENE_DEBUG),
        ("preview", BILL_USAGE_SCENE_PREVIEW),
        ("production", BILL_USAGE_SCENE_PROD),
    )
    llm_metrics = (
        ("input", BILLING_METRIC_LLM_INPUT_TOKENS),
        ("cache", BILLING_METRIC_LLM_CACHE_TOKENS),
        ("output", BILLING_METRIC_LLM_OUTPUT_TOKENS),
    )
    for scene_name, usage_scene in scene_specs:
        for metric_name, billing_metric in llm_metrics:
            seeds.append(
                CreditUsageRateSeed(
                    rate_bid=f"credit-rate-llm-{scene_name}-{metric_name}-default",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="*",
                    model="*",
                    usage_scene=usage_scene,
                    billing_metric=billing_metric,
                    unit_size=1000,
                    credits_per_unit=Decimal("0.0000000000"),
                    rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
                    effective_from=effective_from,
                    effective_to=None,
                    status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
                )
            )
        seeds.append(
            CreditUsageRateSeed(
                rate_bid=f"credit-rate-tts-{scene_name}-request-default",
                usage_type=BILL_USAGE_TYPE_TTS,
                provider="*",
                model="*",
                usage_scene=usage_scene,
                billing_metric=BILLING_METRIC_TTS_REQUEST_COUNT,
                unit_size=1,
                credits_per_unit=Decimal("0.0000000000"),
                rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
                effective_from=effective_from,
                effective_to=None,
                status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
            )
        )
    return tuple(seeds)


CREDIT_USAGE_RATE_SEEDS = _build_credit_usage_rate_seeds()

BILL_SYS_CONFIG_SEEDS = (
    {
        "config_bid": "bill-config-credit-precision",
        "key": BILL_CONFIG_KEY_CREDIT_PRECISION,
        "value": "2",
        "is_encrypted": 0,
        "remark": "Fractional digits used for billing credit display and settlement rounding",
        "deleted": 0,
        "updated_by": "system",
    },
    {
        "config_bid": "bill-config-low-balance-threshold",
        "key": BILL_CONFIG_KEY_LOW_BALANCE_THRESHOLD,
        "value": "0.0000000000",
        "is_encrypted": 0,
        "remark": "Low balance alert threshold in credits",
        "deleted": 0,
        "updated_by": "system",
    },
    {
        "config_bid": "bill-config-renewal-task-config",
        "key": BILL_CONFIG_KEY_RENEWAL_TASK_CONFIG,
        "value": json.dumps(
            {
                "enabled": 0,
                "batch_size": 100,
                "lookahead_minutes": 60,
                "queue": "billing-renewal",
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        "is_encrypted": 0,
        "remark": "Renewal task bootstrap config",
        "deleted": 0,
        "updated_by": "system",
    },
    {
        "config_bid": "bill-config-rate-version",
        "key": BILL_CONFIG_KEY_RATE_VERSION,
        "value": "bootstrap-v1",
        "is_encrypted": 0,
        "remark": "Billing rate version bootstrap marker",
        "deleted": 0,
        "updated_by": "system",
    },
)
