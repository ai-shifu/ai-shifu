"""Billing domain constants and seed catalog definitions."""

from __future__ import annotations

from decimal import Decimal

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

CREDIT_BUCKET_CATEGORY_FREE = 7431
CREDIT_BUCKET_CATEGORY_SUBSCRIPTION = 7432
CREDIT_BUCKET_CATEGORY_TOPUP = 7433

CREDIT_BUCKET_STATUS_ACTIVE = 7441
CREDIT_BUCKET_STATUS_EXHAUSTED = 7442
CREDIT_BUCKET_STATUS_EXPIRED = 7443
CREDIT_BUCKET_STATUS_CANCELED = 7444


BILLING_PRODUCT_TYPE_LABELS = {
    BILLING_PRODUCT_TYPE_PLAN: "plan",
    BILLING_PRODUCT_TYPE_TOPUP: "topup",
    BILLING_PRODUCT_TYPE_GRANT: "grant",
    BILLING_PRODUCT_TYPE_CUSTOM: "custom",
}

BILLING_INTERVAL_LABELS = {
    BILLING_INTERVAL_NONE: "none",
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


BILLING_PRODUCT_SEEDS = (
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
        "price_amount": 9900,
        "credit_amount": Decimal("300000.0000000000"),
        "allocation_interval": ALLOCATION_INTERVAL_PER_CYCLE,
        "auto_renew_enabled": 1,
        "entitlement_payload": None,
        "metadata": None,
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
        "sort_order": 10,
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
        "price_amount": 99900,
        "credit_amount": Decimal("3600000.0000000000"),
        "allocation_interval": ALLOCATION_INTERVAL_PER_CYCLE,
        "auto_renew_enabled": 1,
        "entitlement_payload": None,
        "metadata": {"badge": "recommended"},
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
        "sort_order": 20,
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
        "price_amount": 19900,
        "credit_amount": Decimal("500000.0000000000"),
        "allocation_interval": ALLOCATION_INTERVAL_ONE_TIME,
        "auto_renew_enabled": 0,
        "entitlement_payload": None,
        "metadata": None,
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
        "sort_order": 30,
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
        "price_amount": 69900,
        "credit_amount": Decimal("2000000.0000000000"),
        "allocation_interval": ALLOCATION_INTERVAL_ONE_TIME,
        "auto_renew_enabled": 0,
        "entitlement_payload": None,
        "metadata": {"badge": "best_value"},
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
        "sort_order": 40,
    },
)
