"""expand billing product catalog

Revision ID: f1a2b3c4d5e6
Revises: d4e5f6a7b8c9
Create Date: 2026-04-09 17:00:00.000000

"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


_PRODUCT_TABLE = sa.table(
    "billing_products",
    sa.column("product_bid", sa.String(length=36)),
    sa.column("product_code", sa.String(length=64)),
    sa.column("product_type", sa.SmallInteger()),
    sa.column("billing_mode", sa.SmallInteger()),
    sa.column("billing_interval", sa.SmallInteger()),
    sa.column("billing_interval_count", sa.Integer()),
    sa.column("display_name_i18n_key", sa.String(length=128)),
    sa.column("description_i18n_key", sa.String(length=128)),
    sa.column("currency", sa.String(length=16)),
    sa.column("price_amount", sa.BigInteger()),
    sa.column("credit_amount", sa.Numeric(precision=20, scale=10)),
    sa.column("allocation_interval", sa.SmallInteger()),
    sa.column("auto_renew_enabled", sa.SmallInteger()),
    sa.column("entitlement_payload", sa.JSON()),
    sa.column("metadata", sa.JSON()),
    sa.column("status", sa.SmallInteger()),
    sa.column("sort_order", sa.Integer()),
    sa.column("deleted", sa.SmallInteger()),
    sa.column("created_at", sa.DateTime()),
    sa.column("updated_at", sa.DateTime()),
)


_LEGACY_PRODUCT_SEEDS = (
    {
        "product_bid": "billing-product-plan-monthly",
        "product_code": "creator-plan-monthly",
        "product_type": 7111,
        "billing_mode": 7121,
        "billing_interval": 7132,
        "billing_interval_count": 1,
        "display_name_i18n_key": "module.billing.catalog.plans.creatorMonthly.title",
        "description_i18n_key": "module.billing.catalog.plans.creatorMonthly.description",
        "currency": "CNY",
        "price_amount": 9900,
        "credit_amount": Decimal("300000.0000000000"),
        "allocation_interval": 7141,
        "auto_renew_enabled": 1,
        "entitlement_payload": None,
        "metadata": None,
        "status": 7151,
        "sort_order": 10,
        "deleted": 0,
    },
    {
        "product_bid": "billing-product-plan-yearly",
        "product_code": "creator-plan-yearly",
        "product_type": 7111,
        "billing_mode": 7121,
        "billing_interval": 7133,
        "billing_interval_count": 1,
        "display_name_i18n_key": "module.billing.catalog.plans.creatorYearly.title",
        "description_i18n_key": "module.billing.catalog.plans.creatorYearly.description",
        "currency": "CNY",
        "price_amount": 99900,
        "credit_amount": Decimal("3600000.0000000000"),
        "allocation_interval": 7141,
        "auto_renew_enabled": 1,
        "entitlement_payload": None,
        "metadata": {"badge": "recommended"},
        "status": 7151,
        "sort_order": 20,
        "deleted": 0,
    },
    {
        "product_bid": "billing-product-topup-small",
        "product_code": "creator-topup-small",
        "product_type": 7112,
        "billing_mode": 7122,
        "billing_interval": 7131,
        "billing_interval_count": 0,
        "display_name_i18n_key": "module.billing.catalog.topups.creatorSmall.title",
        "description_i18n_key": "module.billing.catalog.topups.creatorSmall.description",
        "currency": "CNY",
        "price_amount": 19900,
        "credit_amount": Decimal("500000.0000000000"),
        "allocation_interval": 7142,
        "auto_renew_enabled": 0,
        "entitlement_payload": None,
        "metadata": None,
        "status": 7151,
        "sort_order": 30,
        "deleted": 0,
    },
    {
        "product_bid": "billing-product-topup-large",
        "product_code": "creator-topup-large",
        "product_type": 7112,
        "billing_mode": 7122,
        "billing_interval": 7131,
        "billing_interval_count": 0,
        "display_name_i18n_key": "module.billing.catalog.topups.creatorLarge.title",
        "description_i18n_key": "module.billing.catalog.topups.creatorLarge.description",
        "currency": "CNY",
        "price_amount": 69900,
        "credit_amount": Decimal("2000000.0000000000"),
        "allocation_interval": 7142,
        "auto_renew_enabled": 0,
        "entitlement_payload": None,
        "metadata": {"badge": "best_value"},
        "status": 7151,
        "sort_order": 40,
        "deleted": 0,
    },
)


_TARGET_PRODUCT_SEEDS = (
    {
        "product_bid": "billing-product-plan-monthly",
        "product_code": "creator-plan-monthly",
        "product_type": 7111,
        "billing_mode": 7121,
        "billing_interval": 7132,
        "billing_interval_count": 1,
        "display_name_i18n_key": "module.billing.catalog.plans.creatorMonthly.title",
        "description_i18n_key": "module.billing.catalog.plans.creatorMonthly.description",
        "currency": "CNY",
        "price_amount": 990,
        "credit_amount": Decimal("5.0000000000"),
        "allocation_interval": 7141,
        "auto_renew_enabled": 1,
        "entitlement_payload": None,
        "metadata": {
            "highlights": [
                "module.billing.package.features.monthly.publish",
                "module.billing.package.features.monthly.preview",
            ]
        },
        "status": 7151,
        "sort_order": 10,
        "deleted": 0,
    },
    {
        "product_bid": "billing-product-plan-monthly-pro",
        "product_code": "creator-plan-monthly-pro",
        "product_type": 7111,
        "billing_mode": 7121,
        "billing_interval": 7132,
        "billing_interval_count": 1,
        "display_name_i18n_key": "module.billing.catalog.plans.creatorMonthlyPro.title",
        "description_i18n_key": "module.billing.catalog.plans.creatorMonthlyPro.description",
        "currency": "CNY",
        "price_amount": 19900,
        "credit_amount": Decimal("100.0000000000"),
        "allocation_interval": 7141,
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
        "status": 7151,
        "sort_order": 20,
        "deleted": 0,
    },
    {
        "product_bid": "billing-product-plan-yearly-lite",
        "product_code": "creator-plan-yearly-lite",
        "product_type": 7111,
        "billing_mode": 7121,
        "billing_interval": 7133,
        "billing_interval_count": 1,
        "display_name_i18n_key": "module.billing.catalog.plans.creatorYearlyLite.title",
        "description_i18n_key": "module.billing.catalog.plans.creatorYearlyLite.description",
        "currency": "CNY",
        "price_amount": 800000,
        "credit_amount": Decimal("5000.0000000000"),
        "allocation_interval": 7141,
        "auto_renew_enabled": 1,
        "entitlement_payload": None,
        "metadata": {
            "highlights": [
                "module.billing.package.features.yearly.lite.ops",
                "module.billing.package.features.yearly.lite.publish",
            ]
        },
        "status": 7151,
        "sort_order": 30,
        "deleted": 0,
    },
    {
        "product_bid": "billing-product-plan-yearly",
        "product_code": "creator-plan-yearly",
        "product_type": 7111,
        "billing_mode": 7121,
        "billing_interval": 7133,
        "billing_interval_count": 1,
        "display_name_i18n_key": "module.billing.catalog.plans.creatorYearly.title",
        "description_i18n_key": "module.billing.catalog.plans.creatorYearly.description",
        "currency": "CNY",
        "price_amount": 1500000,
        "credit_amount": Decimal("10000.0000000000"),
        "allocation_interval": 7141,
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
        "status": 7151,
        "sort_order": 40,
        "deleted": 0,
    },
    {
        "product_bid": "billing-product-plan-yearly-premium",
        "product_code": "creator-plan-yearly-premium",
        "product_type": 7111,
        "billing_mode": 7121,
        "billing_interval": 7133,
        "billing_interval_count": 1,
        "display_name_i18n_key": "module.billing.catalog.plans.creatorYearlyPremium.title",
        "description_i18n_key": "module.billing.catalog.plans.creatorYearlyPremium.description",
        "currency": "CNY",
        "price_amount": 3000000,
        "credit_amount": Decimal("22000.0000000000"),
        "allocation_interval": 7141,
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
        "status": 7151,
        "sort_order": 50,
        "deleted": 0,
    },
    {
        "product_bid": "billing-product-topup-small",
        "product_code": "creator-topup-small",
        "product_type": 7112,
        "billing_mode": 7122,
        "billing_interval": 7131,
        "billing_interval_count": 0,
        "display_name_i18n_key": "module.billing.catalog.topups.creatorSmall.title",
        "description_i18n_key": "module.billing.catalog.topups.creatorSmall.description",
        "currency": "CNY",
        "price_amount": 5000,
        "credit_amount": Decimal("20.0000000000"),
        "allocation_interval": 7142,
        "auto_renew_enabled": 0,
        "entitlement_payload": None,
        "metadata": None,
        "status": 7151,
        "sort_order": 60,
        "deleted": 0,
    },
    {
        "product_bid": "billing-product-topup-medium",
        "product_code": "creator-topup-medium",
        "product_type": 7112,
        "billing_mode": 7122,
        "billing_interval": 7131,
        "billing_interval_count": 0,
        "display_name_i18n_key": "module.billing.catalog.topups.creatorMedium.title",
        "description_i18n_key": "module.billing.catalog.topups.creatorMedium.description",
        "currency": "CNY",
        "price_amount": 9900,
        "credit_amount": Decimal("50.0000000000"),
        "allocation_interval": 7142,
        "auto_renew_enabled": 0,
        "entitlement_payload": None,
        "metadata": None,
        "status": 7151,
        "sort_order": 70,
        "deleted": 0,
    },
    {
        "product_bid": "billing-product-topup-large",
        "product_code": "creator-topup-large",
        "product_type": 7112,
        "billing_mode": 7122,
        "billing_interval": 7131,
        "billing_interval_count": 0,
        "display_name_i18n_key": "module.billing.catalog.topups.creatorLarge.title",
        "description_i18n_key": "module.billing.catalog.topups.creatorLarge.description",
        "currency": "CNY",
        "price_amount": 19900,
        "credit_amount": Decimal("120.0000000000"),
        "allocation_interval": 7142,
        "auto_renew_enabled": 0,
        "entitlement_payload": None,
        "metadata": None,
        "status": 7151,
        "sort_order": 80,
        "deleted": 0,
    },
    {
        "product_bid": "billing-product-topup-xlarge",
        "product_code": "creator-topup-xlarge",
        "product_type": 7112,
        "billing_mode": 7122,
        "billing_interval": 7131,
        "billing_interval_count": 0,
        "display_name_i18n_key": "module.billing.catalog.topups.creatorXLarge.title",
        "description_i18n_key": "module.billing.catalog.topups.creatorXLarge.description",
        "currency": "CNY",
        "price_amount": 49900,
        "credit_amount": Decimal("320.0000000000"),
        "allocation_interval": 7142,
        "auto_renew_enabled": 0,
        "entitlement_payload": None,
        "metadata": {"badge": "best_value"},
        "status": 7151,
        "sort_order": 90,
        "deleted": 0,
    },
)


_NEW_PRODUCT_BIDS = (
    "billing-product-plan-monthly-pro",
    "billing-product-plan-yearly-lite",
    "billing-product-plan-yearly-premium",
    "billing-product-topup-medium",
    "billing-product-topup-xlarge",
)


def _upsert_products(rows: tuple[dict[str, object], ...]) -> None:
    bind = op.get_bind()
    now = datetime.utcnow()

    for row in rows:
        payload = dict(row)
        payload["updated_at"] = now
        result = bind.execute(
            _PRODUCT_TABLE.update()
            .where(_PRODUCT_TABLE.c.product_bid == payload["product_bid"])
            .values(**payload)
        )
        if result.rowcount == 0:
            insert_payload = dict(payload)
            insert_payload["created_at"] = now
            bind.execute(_PRODUCT_TABLE.insert().values(**insert_payload))


def upgrade():
    _upsert_products(_TARGET_PRODUCT_SEEDS)


def downgrade():
    bind = op.get_bind()
    bind.execute(
        _PRODUCT_TABLE.delete().where(
            _PRODUCT_TABLE.c.product_bid.in_(_NEW_PRODUCT_BIDS)
        )
    )
    _upsert_products(_LEGACY_PRODUCT_SEEDS)
