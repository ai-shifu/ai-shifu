"""add billing core tables

Revision ID: 4fd52d0d9a01
Revises: 7b3c5d9e1a2f
Create Date: 2026-04-08 00:00:00.000000

"""

from __future__ import annotations

from decimal import Decimal

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "4fd52d0d9a01"
down_revision = "7b3c5d9e1a2f"
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

    product_table = sa.table(
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
        sa.column("price_amount", mysql.BIGINT()),
        sa.column("credit_amount", sa.Numeric(precision=20, scale=10)),
        sa.column("allocation_interval", sa.SmallInteger()),
        sa.column("auto_renew_enabled", sa.SmallInteger()),
        sa.column("entitlement_payload", sa.JSON()),
        sa.column("metadata", sa.JSON()),
        sa.column("status", sa.SmallInteger()),
        sa.column("sort_order", sa.Integer()),
        sa.column("deleted", sa.SmallInteger()),
    )
    op.bulk_insert(product_table, list(_PRODUCT_SEEDS))


def downgrade():
    op.drop_table("credit_ledger_entries")
    op.drop_table("credit_wallet_buckets")
    op.drop_table("credit_wallets")
    op.drop_table("billing_orders")
    op.drop_table("billing_subscriptions")
    op.drop_table("billing_products")
