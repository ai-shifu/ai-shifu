"""add billing core phase

Revision ID: b114d7f5e2c1
Revises: 2b7c9d1e4f6a
Create Date: 2026-04-09 20:00:00.000000

"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "b114d7f5e2c1"
down_revision = "2b7c9d1e4f6a"
branch_labels = None
depends_on = None


_PRODUCT_SEEDS = (
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

_BILLING_SYS_CONFIG_SEEDS = (
    {
        "config_bid": "billing-config-enabled",
        "key": "BILLING_ENABLED",
        "value": "1",
        "is_encrypted": 0,
        "remark": "Creator billing feature flag",
        "deleted": 0,
        "updated_by": "system",
    },
    {
        "config_bid": "billing-config-low-balance-threshold",
        "key": "BILLING_LOW_BALANCE_THRESHOLD",
        "value": "0.0000000000",
        "is_encrypted": 0,
        "remark": "Low balance alert threshold in credits",
        "deleted": 0,
        "updated_by": "system",
    },
    {
        "config_bid": "billing-config-renewal-task-config",
        "key": "BILLING_RENEWAL_TASK_CONFIG",
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
        "config_bid": "billing-config-rate-version",
        "key": "BILLING_RATE_VERSION",
        "value": "bootstrap-v1",
        "is_encrypted": 0,
        "remark": "Billing rate version bootstrap marker",
        "deleted": 0,
        "updated_by": "system",
    },
)


def _build_usage_rate_seeds() -> tuple[dict[str, object], ...]:
    seeds: list[dict[str, object]] = []
    effective_from = datetime(2026, 1, 1, 0, 0, 0)
    scene_specs = (
        ("debug", 1201),
        ("preview", 1202),
        ("production", 1203),
    )
    llm_metrics = (
        ("input", 7451),
        ("cache", 7452),
        ("output", 7453),
    )
    for scene_name, usage_scene in scene_specs:
        for metric_name, billing_metric in llm_metrics:
            seeds.append(
                {
                    "rate_bid": f"credit-rate-llm-{scene_name}-{metric_name}-default",
                    "usage_type": 1101,
                    "provider": "*",
                    "model": "*",
                    "usage_scene": usage_scene,
                    "billing_metric": billing_metric,
                    "unit_size": 1000,
                    "credits_per_unit": Decimal("0.0000000000"),
                    "rounding_mode": 7421,
                    "effective_from": effective_from,
                    "effective_to": None,
                    "status": 7151,
                    "deleted": 0,
                }
            )
        seeds.append(
            {
                "rate_bid": f"credit-rate-tts-{scene_name}-request-default",
                "usage_type": 1102,
                "provider": "*",
                "model": "*",
                "usage_scene": usage_scene,
                "billing_metric": 7454,
                "unit_size": 1,
                "credits_per_unit": Decimal("0.0000000000"),
                "rounding_mode": 7421,
                "effective_from": effective_from,
                "effective_to": None,
                "status": 7151,
                "deleted": 0,
            }
        )
    return tuple(seeds)


_USAGE_RATE_SEEDS = _build_usage_rate_seeds()


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
    op.create_table(
        "billing_products",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "product_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing product business identifier",
        ),
        sa.Column(
            "product_code",
            sa.String(length=64),
            nullable=False,
            comment="Billing product code",
        ),
        sa.Column(
            "product_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing product type code",
        ),
        sa.Column(
            "billing_mode",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing mode code",
        ),
        sa.Column(
            "billing_interval",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing interval code",
        ),
        sa.Column(
            "billing_interval_count",
            sa.Integer(),
            nullable=False,
            comment="Billing interval count",
        ),
        sa.Column(
            "display_name_i18n_key",
            sa.String(length=128),
            nullable=False,
            comment="Display name i18n key",
        ),
        sa.Column(
            "description_i18n_key",
            sa.String(length=128),
            nullable=False,
            comment="Description i18n key",
        ),
        sa.Column(
            "currency", sa.String(length=16), nullable=False, comment="Currency code"
        ),
        sa.Column(
            "price_amount",
            mysql.BIGINT(),
            nullable=False,
            comment="Product price amount",
        ),
        sa.Column(
            "credit_amount",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Credit amount",
        ),
        sa.Column(
            "allocation_interval",
            sa.SmallInteger(),
            nullable=False,
            comment="Credit allocation interval code",
        ),
        sa.Column(
            "auto_renew_enabled",
            sa.SmallInteger(),
            nullable=False,
            comment="Auto renew enabled flag",
        ),
        sa.Column(
            "entitlement_payload",
            sa.JSON(),
            nullable=True,
            comment="Entitlement payload",
        ),
        sa.Column(
            "metadata", sa.JSON(), nullable=True, comment="Billing product metadata"
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing product status code",
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, comment="Sort order"),
        sa.Column(
            "deleted", sa.SmallInteger(), nullable=False, comment="Deletion flag"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_code"),
        comment="Billing product catalog",
    )
    with op.batch_alter_table("billing_products", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_products_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_billing_products_product_bid"), ["product_bid"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_billing_products_product_type"),
            ["product_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_products_status"), ["status"], unique=False
        )
        batch_op.create_index(
            "ix_billing_products_product_type_status",
            ["product_type", "status"],
            unique=False,
        )

    op.create_table(
        "billing_subscriptions",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "subscription_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing subscription business identifier",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "product_bid",
            sa.String(length=36),
            nullable=False,
            comment="Current billing product business identifier",
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing subscription status code",
        ),
        sa.Column(
            "billing_provider",
            sa.String(length=32),
            nullable=False,
            comment="Billing provider name",
        ),
        sa.Column(
            "provider_subscription_id",
            sa.String(length=255),
            nullable=False,
            comment="Provider subscription identifier",
        ),
        sa.Column(
            "provider_customer_id",
            sa.String(length=255),
            nullable=False,
            comment="Provider customer identifier",
        ),
        sa.Column(
            "billing_anchor_at",
            sa.DateTime(),
            nullable=True,
            comment="Billing anchor timestamp",
        ),
        sa.Column(
            "current_period_start_at",
            sa.DateTime(),
            nullable=True,
            comment="Current period start timestamp",
        ),
        sa.Column(
            "current_period_end_at",
            sa.DateTime(),
            nullable=True,
            comment="Current period end timestamp",
        ),
        sa.Column(
            "grace_period_end_at",
            sa.DateTime(),
            nullable=True,
            comment="Grace period end timestamp",
        ),
        sa.Column(
            "cancel_at_period_end",
            sa.SmallInteger(),
            nullable=False,
            comment="Cancel at period end flag",
        ),
        sa.Column(
            "next_product_bid",
            sa.String(length=36),
            nullable=False,
            comment="Next billing product business identifier",
        ),
        sa.Column(
            "last_renewed_at",
            sa.DateTime(),
            nullable=True,
            comment="Last renewed timestamp",
        ),
        sa.Column(
            "last_failed_at",
            sa.DateTime(),
            nullable=True,
            comment="Last failed timestamp",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="Billing subscription metadata",
        ),
        sa.Column(
            "deleted", sa.SmallInteger(), nullable=False, comment="Deletion flag"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Billing subscriptions",
    )
    with op.batch_alter_table("billing_subscriptions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_subscriptions_billing_provider"),
            ["billing_provider"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_subscriptions_creator_bid"),
            ["creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_subscriptions_creator_status",
            ["creator_bid", "status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_subscriptions_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_billing_subscriptions_next_product_bid"),
            ["next_product_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_subscriptions_product_bid"),
            ["product_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_subscriptions_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_billing_subscriptions_subscription_bid"),
            ["subscription_bid"],
            unique=False,
        )

    op.create_table(
        "billing_orders",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "billing_order_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing order business identifier",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "order_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing order type code",
        ),
        sa.Column(
            "product_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing product business identifier",
        ),
        sa.Column(
            "subscription_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing subscription business identifier",
        ),
        sa.Column(
            "currency", sa.String(length=16), nullable=False, comment="Currency code"
        ),
        sa.Column(
            "payable_amount", mysql.BIGINT(), nullable=False, comment="Payable amount"
        ),
        sa.Column("paid_amount", mysql.BIGINT(), nullable=False, comment="Paid amount"),
        sa.Column(
            "payment_provider",
            sa.String(length=32),
            nullable=False,
            comment="Payment provider name",
        ),
        sa.Column(
            "channel", sa.String(length=64), nullable=False, comment="Payment channel"
        ),
        sa.Column(
            "provider_reference_id",
            sa.String(length=255),
            nullable=False,
            comment="Provider reference identifier",
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing order status code",
        ),
        sa.Column("paid_at", sa.DateTime(), nullable=True, comment="Paid timestamp"),
        sa.Column(
            "failed_at", sa.DateTime(), nullable=True, comment="Failed timestamp"
        ),
        sa.Column(
            "refunded_at", sa.DateTime(), nullable=True, comment="Refunded timestamp"
        ),
        sa.Column(
            "failure_code",
            sa.String(length=255),
            nullable=False,
            comment="Failure code",
        ),
        sa.Column(
            "failure_message",
            sa.String(length=255),
            nullable=False,
            comment="Failure message",
        ),
        sa.Column(
            "metadata", sa.JSON(), nullable=True, comment="Billing order metadata"
        ),
        sa.Column(
            "deleted", sa.SmallInteger(), nullable=False, comment="Deletion flag"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Billing orders",
    )
    with op.batch_alter_table("billing_orders", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_orders_billing_order_bid"),
            ["billing_order_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_orders_creator_bid"), ["creator_bid"], unique=False
        )
        batch_op.create_index(
            "ix_billing_orders_creator_status", ["creator_bid", "status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_billing_orders_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_billing_orders_order_type"), ["order_type"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_billing_orders_payment_provider"),
            ["payment_provider"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_orders_product_bid"), ["product_bid"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_billing_orders_provider_reference_id"),
            ["provider_reference_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_orders_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_billing_orders_subscription_bid"),
            ["subscription_bid"],
            unique=False,
        )

    op.create_table(
        "credit_wallets",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "wallet_bid",
            sa.String(length=36),
            nullable=False,
            comment="Credit wallet business identifier",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "available_credits",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Available credits",
        ),
        sa.Column(
            "reserved_credits",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Reserved credits",
        ),
        sa.Column(
            "lifetime_granted_credits",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Lifetime granted credits",
        ),
        sa.Column(
            "lifetime_consumed_credits",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Lifetime consumed credits",
        ),
        sa.Column(
            "last_settled_usage_id",
            mysql.BIGINT(),
            nullable=False,
            comment="Last settled usage record id",
        ),
        sa.Column("version", sa.Integer(), nullable=False, comment="Wallet version"),
        sa.Column(
            "deleted", sa.SmallInteger(), nullable=False, comment="Deletion flag"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("creator_bid"),
        comment="Credit wallets",
    )
    with op.batch_alter_table("credit_wallets", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_credit_wallets_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_credit_wallets_last_settled_usage_id"),
            ["last_settled_usage_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_wallets_wallet_bid"), ["wallet_bid"], unique=False
        )

    op.create_table(
        "credit_wallet_buckets",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "wallet_bucket_bid",
            sa.String(length=36),
            nullable=False,
            comment="Credit wallet bucket business identifier",
        ),
        sa.Column(
            "wallet_bid",
            sa.String(length=36),
            nullable=False,
            comment="Credit wallet business identifier",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "bucket_category",
            sa.SmallInteger(),
            nullable=False,
            comment="Credit bucket category code",
        ),
        sa.Column(
            "source_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing ledger source type code",
        ),
        sa.Column(
            "source_bid",
            sa.String(length=36),
            nullable=False,
            comment="Credit bucket source business identifier",
        ),
        sa.Column(
            "priority",
            sa.SmallInteger(),
            nullable=False,
            comment="Credit bucket priority",
        ),
        sa.Column(
            "original_credits",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Original credits",
        ),
        sa.Column(
            "available_credits",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Available credits",
        ),
        sa.Column(
            "reserved_credits",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Reserved credits",
        ),
        sa.Column(
            "consumed_credits",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Consumed credits",
        ),
        sa.Column(
            "expired_credits",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Expired credits",
        ),
        sa.Column(
            "effective_from",
            sa.DateTime(),
            nullable=False,
            comment="Effective from timestamp",
        ),
        sa.Column(
            "effective_to",
            sa.DateTime(),
            nullable=True,
            comment="Effective to timestamp",
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Credit bucket status code",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="Credit wallet bucket metadata",
        ),
        sa.Column(
            "deleted", sa.SmallInteger(), nullable=False, comment="Deletion flag"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Credit wallet buckets",
    )
    with op.batch_alter_table("credit_wallet_buckets", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_credit_wallet_buckets_bucket_category"),
            ["bucket_category"],
            unique=False,
        )
        batch_op.create_index(
            "ix_credit_wallet_buckets_creator_status_priority_effective_to",
            ["creator_bid", "status", "priority", "effective_to"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_wallet_buckets_creator_bid"),
            ["creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_wallet_buckets_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_credit_wallet_buckets_effective_from"),
            ["effective_from"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_wallet_buckets_effective_to"),
            ["effective_to"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_wallet_buckets_priority"), ["priority"], unique=False
        )
        batch_op.create_index(
            "ix_credit_wallet_buckets_source_type_source_bid",
            ["source_type", "source_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_wallet_buckets_source_bid"),
            ["source_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_wallet_buckets_source_type"),
            ["source_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_wallet_buckets_status"), ["status"], unique=False
        )
        batch_op.create_index(
            "ix_credit_wallet_buckets_wallet_status_priority_effective_to",
            ["wallet_bid", "status", "priority", "effective_to"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_wallet_buckets_wallet_bid"),
            ["wallet_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_wallet_buckets_wallet_bucket_bid"),
            ["wallet_bucket_bid"],
            unique=False,
        )

    op.create_table(
        "credit_ledger_entries",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "ledger_bid",
            sa.String(length=36),
            nullable=False,
            comment="Credit ledger business identifier",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "wallet_bid",
            sa.String(length=36),
            nullable=False,
            comment="Credit wallet business identifier",
        ),
        sa.Column(
            "wallet_bucket_bid",
            sa.String(length=36),
            nullable=False,
            comment="Credit wallet bucket business identifier",
        ),
        sa.Column(
            "entry_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing ledger entry type code",
        ),
        sa.Column(
            "source_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing ledger source type code",
        ),
        sa.Column(
            "source_bid",
            sa.String(length=36),
            nullable=False,
            comment="Ledger source business identifier",
        ),
        sa.Column(
            "idempotency_key",
            sa.String(length=128),
            nullable=False,
            comment="Ledger idempotency key",
        ),
        sa.Column(
            "amount",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Ledger amount",
        ),
        sa.Column(
            "balance_after",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Balance after entry",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(),
            nullable=True,
            comment="Entry expiration timestamp",
        ),
        sa.Column(
            "consumable_from",
            sa.DateTime(),
            nullable=True,
            comment="Consumable from timestamp",
        ),
        sa.Column(
            "metadata", sa.JSON(), nullable=True, comment="Billing ledger metadata"
        ),
        sa.Column(
            "deleted", sa.SmallInteger(), nullable=False, comment="Deletion flag"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "creator_bid",
            "idempotency_key",
            name="uq_credit_ledger_entries_creator_idempotency",
        ),
        comment="Credit ledger entries",
    )
    with op.batch_alter_table("credit_ledger_entries", schema=None) as batch_op:
        batch_op.create_index(
            "ix_credit_ledger_entries_creator_created",
            ["creator_bid", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_ledger_entries_creator_bid"),
            ["creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_ledger_entries_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_credit_ledger_entries_entry_type"),
            ["entry_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_ledger_entries_expires_at"),
            ["expires_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_ledger_entries_idempotency_key"),
            ["idempotency_key"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_ledger_entries_ledger_bid"),
            ["ledger_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_credit_ledger_entries_source_type_source_bid",
            ["source_type", "source_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_ledger_entries_source_bid"),
            ["source_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_ledger_entries_source_type"),
            ["source_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_ledger_entries_wallet_bid"),
            ["wallet_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_ledger_entries_wallet_bucket_bid"),
            ["wallet_bucket_bid"],
            unique=False,
        )

    op.bulk_insert(_PRODUCT_TABLE, list(_PRODUCT_SEEDS))
    _upsert_products(_TARGET_PRODUCT_SEEDS)

    op.create_table(
        "credit_usage_rates",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column("rate_bid", sa.String(length=36), nullable=False),
        sa.Column("usage_type", sa.SmallInteger(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("usage_scene", sa.SmallInteger(), nullable=False),
        sa.Column("billing_metric", sa.SmallInteger(), nullable=False),
        sa.Column("unit_size", sa.Integer(), nullable=False),
        sa.Column(
            "credits_per_unit",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
        ),
        sa.Column("rounding_mode", sa.SmallInteger(), nullable=False),
        sa.Column("effective_from", sa.DateTime(), nullable=False),
        sa.Column("effective_to", sa.DateTime(), nullable=True),
        sa.Column("status", sa.SmallInteger(), nullable=False),
        sa.Column("deleted", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Credit usage rates",
    )
    with op.batch_alter_table("credit_usage_rates", schema=None) as batch_op:
        batch_op.create_index(
            "ix_credit_usage_rates_lookup",
            [
                "usage_type",
                "provider",
                "model",
                "usage_scene",
                "billing_metric",
                "effective_from",
            ],
            unique=False,
        )
        batch_op.create_index(
            "ix_credit_usage_rates_billing_metric",
            ["billing_metric"],
            unique=False,
        )
        batch_op.create_index(
            "ix_credit_usage_rates_rate_bid",
            ["rate_bid"],
            unique=False,
        )

    op.create_table(
        "billing_renewal_events",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column("renewal_event_bid", sa.String(length=36), nullable=False),
        sa.Column("subscription_bid", sa.String(length=36), nullable=False),
        sa.Column("creator_bid", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.SmallInteger(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.SmallInteger(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("deleted", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Billing renewal events",
    )
    with op.batch_alter_table("billing_renewal_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_billing_renewal_events_status_scheduled",
            ["status", "scheduled_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_renewal_events_subscription_event_scheduled",
            ["subscription_bid", "event_type", "scheduled_at"],
            unique=False,
        )

    with op.batch_alter_table("billing_products", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_billing_products_product_bid",
            ["product_bid"],
        )

    with op.batch_alter_table("billing_subscriptions", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_billing_subscriptions_subscription_bid",
            ["subscription_bid"],
        )

    with op.batch_alter_table("billing_orders", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_billing_orders_billing_order_bid",
            ["billing_order_bid"],
        )

    with op.batch_alter_table("credit_wallets", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_credit_wallets_wallet_bid",
            ["wallet_bid"],
        )

    with op.batch_alter_table("credit_wallet_buckets", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_credit_wallet_buckets_wallet_bucket_bid",
            ["wallet_bucket_bid"],
        )

    with op.batch_alter_table("credit_ledger_entries", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_credit_ledger_entries_ledger_bid",
            ["ledger_bid"],
        )

    with op.batch_alter_table("credit_usage_rates", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_credit_usage_rates_rate_bid",
            ["rate_bid"],
        )
        batch_op.create_unique_constraint(
            "uq_credit_usage_rates_lookup",
            [
                "usage_type",
                "provider",
                "model",
                "usage_scene",
                "billing_metric",
                "effective_from",
            ],
        )

    with op.batch_alter_table("billing_renewal_events", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_billing_renewal_events_renewal_event_bid",
            ["renewal_event_bid"],
        )
        batch_op.create_unique_constraint(
            "uq_billing_renewal_events_subscription_event_scheduled",
            ["subscription_bid", "event_type", "scheduled_at"],
        )

    rate_table = sa.table(
        "credit_usage_rates",
        sa.column("rate_bid", sa.String(length=36)),
        sa.column("usage_type", sa.SmallInteger()),
        sa.column("provider", sa.String(length=32)),
        sa.column("model", sa.String(length=100)),
        sa.column("usage_scene", sa.SmallInteger()),
        sa.column("billing_metric", sa.SmallInteger()),
        sa.column("unit_size", sa.Integer()),
        sa.column("credits_per_unit", sa.Numeric(precision=20, scale=10)),
        sa.column("rounding_mode", sa.SmallInteger()),
        sa.column("effective_from", sa.DateTime()),
        sa.column("effective_to", sa.DateTime()),
        sa.column("status", sa.SmallInteger()),
        sa.column("deleted", sa.SmallInteger()),
    )
    op.bulk_insert(rate_table, list(_USAGE_RATE_SEEDS))

    config_table = sa.table(
        "sys_configs",
        sa.column("config_bid", sa.String(length=36)),
        sa.column("key", sa.String(length=255)),
        sa.column("value", sa.Text()),
        sa.column("is_encrypted", sa.SmallInteger()),
        sa.column("remark", sa.Text()),
        sa.column("deleted", sa.SmallInteger()),
        sa.column("updated_by", sa.String(length=36)),
    )
    op.bulk_insert(config_table, list(_BILLING_SYS_CONFIG_SEEDS))

    with op.batch_alter_table("order_pingxx_orders", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "biz_domain",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'order'"),
                comment="Business domain",
            )
        )
        batch_op.add_column(
            sa.Column(
                "billing_order_bid",
                sa.String(length=36),
                nullable=False,
                server_default=sa.text("''"),
                comment="Billing order business identifier",
            )
        )
        batch_op.add_column(
            sa.Column(
                "creator_bid",
                sa.String(length=36),
                nullable=False,
                server_default=sa.text("''"),
                comment="Creator business identifier",
            )
        )
        batch_op.create_index(
            "ix_order_pingxx_orders_biz_domain", ["biz_domain"], unique=False
        )
        batch_op.create_index(
            "ix_order_pingxx_orders_billing_order_bid",
            ["billing_order_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_order_pingxx_orders_creator_bid",
            ["creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_order_pingxx_orders_biz_domain_order_bid",
            ["biz_domain", "order_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_order_pingxx_orders_biz_domain_billing_order_bid",
            ["biz_domain", "billing_order_bid"],
            unique=False,
        )

    with op.batch_alter_table("order_stripe_orders", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "biz_domain",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'order'"),
                comment="Business domain",
            )
        )
        batch_op.add_column(
            sa.Column(
                "billing_order_bid",
                sa.String(length=36),
                nullable=False,
                server_default=sa.text("''"),
                comment="Billing order business identifier",
            )
        )
        batch_op.add_column(
            sa.Column(
                "creator_bid",
                sa.String(length=36),
                nullable=False,
                server_default=sa.text("''"),
                comment="Creator business identifier",
            )
        )
        batch_op.create_index(
            "ix_order_stripe_orders_biz_domain", ["biz_domain"], unique=False
        )
        batch_op.create_index(
            "ix_order_stripe_orders_billing_order_bid",
            ["billing_order_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_order_stripe_orders_creator_bid",
            ["creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_order_stripe_orders_biz_domain_order_bid",
            ["biz_domain", "order_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_order_stripe_orders_biz_domain_billing_order_bid",
            ["biz_domain", "billing_order_bid"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("order_stripe_orders", schema=None) as batch_op:
        batch_op.drop_index("ix_order_stripe_orders_biz_domain_billing_order_bid")
        batch_op.drop_index("ix_order_stripe_orders_biz_domain_order_bid")
        batch_op.drop_index("ix_order_stripe_orders_creator_bid")
        batch_op.drop_index("ix_order_stripe_orders_billing_order_bid")
        batch_op.drop_index("ix_order_stripe_orders_biz_domain")
        batch_op.drop_column("creator_bid")
        batch_op.drop_column("billing_order_bid")
        batch_op.drop_column("biz_domain")

    with op.batch_alter_table("order_pingxx_orders", schema=None) as batch_op:
        batch_op.drop_index("ix_order_pingxx_orders_biz_domain_billing_order_bid")
        batch_op.drop_index("ix_order_pingxx_orders_biz_domain_order_bid")
        batch_op.drop_index("ix_order_pingxx_orders_creator_bid")
        batch_op.drop_index("ix_order_pingxx_orders_billing_order_bid")
        batch_op.drop_index("ix_order_pingxx_orders_biz_domain")
        batch_op.drop_column("creator_bid")
        batch_op.drop_column("billing_order_bid")
        batch_op.drop_column("biz_domain")

    config_table = sa.table("sys_configs", sa.column("key", sa.String(length=255)))
    op.execute(
        config_table.delete().where(
            config_table.c.key.in_([row["key"] for row in _BILLING_SYS_CONFIG_SEEDS])
        )
    )

    rate_table = sa.table(
        "credit_usage_rates", sa.column("rate_bid", sa.String(length=36))
    )
    op.execute(
        rate_table.delete().where(
            rate_table.c.rate_bid.in_([row["rate_bid"] for row in _USAGE_RATE_SEEDS])
        )
    )

    with op.batch_alter_table("billing_renewal_events", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_billing_renewal_events_subscription_event_scheduled",
            type_="unique",
        )
        batch_op.drop_constraint(
            "uq_billing_renewal_events_renewal_event_bid",
            type_="unique",
        )

    with op.batch_alter_table("credit_usage_rates", schema=None) as batch_op:
        batch_op.drop_constraint("uq_credit_usage_rates_lookup", type_="unique")
        batch_op.drop_constraint("uq_credit_usage_rates_rate_bid", type_="unique")

    with op.batch_alter_table("credit_ledger_entries", schema=None) as batch_op:
        batch_op.drop_constraint("uq_credit_ledger_entries_ledger_bid", type_="unique")

    with op.batch_alter_table("credit_wallet_buckets", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_credit_wallet_buckets_wallet_bucket_bid",
            type_="unique",
        )

    with op.batch_alter_table("credit_wallets", schema=None) as batch_op:
        batch_op.drop_constraint("uq_credit_wallets_wallet_bid", type_="unique")

    with op.batch_alter_table("billing_orders", schema=None) as batch_op:
        batch_op.drop_constraint("uq_billing_orders_billing_order_bid", type_="unique")

    with op.batch_alter_table("billing_subscriptions", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_billing_subscriptions_subscription_bid",
            type_="unique",
        )

    with op.batch_alter_table("billing_products", schema=None) as batch_op:
        batch_op.drop_constraint("uq_billing_products_product_bid", type_="unique")

    op.drop_table("billing_renewal_events")
    op.drop_table("credit_usage_rates")
    op.drop_table("credit_ledger_entries")
    op.drop_table("credit_wallet_buckets")
    op.drop_table("credit_wallets")
    op.drop_table("billing_orders")
    op.drop_table("billing_subscriptions")
    op.drop_table("billing_products")
