"""add billing core phase

Revision ID: b114d7f5e2c1
Revises: 1c8f4b7a9d2e
Create Date: 2026-04-09 20:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "b114d7f5e2c1"
down_revision = "1c8f4b7a9d2e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bill_products",
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
            comment="Billing product type: 7111=plan, 7112=topup, 7113=grant, 7114=custom",
        ),
        sa.Column(
            "billing_mode",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing mode: 7121=recurring, 7122=one_time, 7123=manual",
        ),
        sa.Column(
            "billing_interval",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing interval: 7131=none, 7132=month, 7133=year, 7134=day",
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
            comment="Credit allocation interval: 7141=per_cycle, 7142=one_time, 7143=manual",
        ),
        sa.Column(
            "auto_renew_enabled",
            sa.SmallInteger(),
            nullable=False,
            comment="Auto renew enabled flag: 0=disabled, 1=enabled",
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
            comment="Billing product status: 7151=active, 7152=inactive",
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, comment="Sort order"),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
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
    with op.batch_alter_table("bill_products", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_bill_products_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_bill_products_product_bid"), ["product_bid"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_bill_products_product_type"),
            ["product_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_products_status"), ["status"], unique=False
        )
        batch_op.create_index(
            "ix_bill_products_product_type_status",
            ["product_type", "status"],
            unique=False,
        )

    op.create_table(
        "bill_subscriptions",
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
            comment="Billing subscription status: 7201=draft, 7202=active, 7203=past_due, 7204=paused, 7205=cancel_scheduled, 7206=canceled, 7207=expired",
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
            comment="Cancel at period end flag: 0=no, 1=yes",
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
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
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
    with op.batch_alter_table("bill_subscriptions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_bill_subscriptions_billing_provider"),
            ["billing_provider"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_subscriptions_creator_bid"),
            ["creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_bill_subscriptions_creator_status",
            ["creator_bid", "status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_subscriptions_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_bill_subscriptions_next_product_bid"),
            ["next_product_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_subscriptions_product_bid"),
            ["product_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_subscriptions_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_bill_subscriptions_subscription_bid"),
            ["subscription_bid"],
            unique=False,
        )

    op.create_table(
        "bill_orders",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "bill_order_bid",
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
            comment="Billing order type: 7301=subscription_start, 7302=subscription_upgrade, 7303=subscription_renewal, 7304=topup, 7305=manual, 7306=refund",
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
            comment="Billing order status: 7311=init, 7312=pending, 7313=paid, 7314=failed, 7315=refunded, 7316=canceled, 7317=timeout",
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
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
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
    with op.batch_alter_table("bill_orders", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_bill_orders_bill_order_bid"),
            ["bill_order_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_orders_creator_bid"), ["creator_bid"], unique=False
        )
        batch_op.create_index(
            "ix_bill_orders_creator_status", ["creator_bid", "status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_bill_orders_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_bill_orders_order_type"), ["order_type"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_bill_orders_payment_provider"),
            ["payment_provider"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_orders_product_bid"), ["product_bid"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_bill_orders_provider_reference_id"),
            ["provider_reference_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_orders_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_bill_orders_subscription_bid"),
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
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
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
            comment="Credit bucket category: 7431=free, 7432=subscription, 7433=topup",
        ),
        sa.Column(
            "source_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing ledger source type: 7411=subscription, 7412=topup, 7413=gift, 7414=usage, 7415=refund, 7416=manual",
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
            comment="Credit bucket status: 7441=active, 7442=exhausted, 7443=expired, 7444=canceled",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="Credit wallet bucket metadata",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
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
            comment="Billing ledger entry type: 7401=grant, 7402=consume, 7403=refund, 7404=expire, 7405=adjustment, 7406=hold, 7407=release",
        ),
        sa.Column(
            "source_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing ledger source type: 7411=subscription, 7412=topup, 7413=gift, 7414=usage, 7415=refund, 7416=manual",
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
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
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

    op.create_table(
        "credit_usage_rates",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "rate_bid",
            sa.String(length=36),
            nullable=False,
            comment="Credit usage rate business identifier",
        ),
        sa.Column(
            "usage_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Usage type: 1101=LLM, 1102=TTS",
        ),
        sa.Column(
            "provider",
            sa.String(length=32),
            nullable=False,
            comment="Provider name",
        ),
        sa.Column(
            "model",
            sa.String(length=100),
            nullable=False,
            comment="Provider model",
        ),
        sa.Column(
            "usage_scene",
            sa.SmallInteger(),
            nullable=False,
            comment="Usage scene: 1201=debug, 1202=preview, 1203=production",
        ),
        sa.Column(
            "billing_metric",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing metric: 7451=llm_input_tokens, 7452=llm_cache_tokens, 7453=llm_output_tokens, 7454=tts_request_count, 7455=tts_output_chars, 7456=tts_input_chars",
        ),
        sa.Column(
            "unit_size",
            sa.Integer(),
            nullable=False,
            comment="Billing unit size",
        ),
        sa.Column(
            "credits_per_unit",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Credits per unit",
        ),
        sa.Column(
            "rounding_mode",
            sa.SmallInteger(),
            nullable=False,
            comment="Rounding mode: 7421=ceil, 7422=floor, 7423=round",
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
            comment="Credit usage rate status: 7151=active, 7152=inactive",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
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
        "bill_renewal_events",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "renewal_event_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing renewal event business identifier",
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
            "event_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing renewal event type: 7501=renewal, 7502=retry, 7503=cancel_effective, 7504=downgrade_effective, 7505=expire, 7506=reconcile",
        ),
        sa.Column(
            "scheduled_at",
            sa.DateTime(),
            nullable=False,
            comment="Scheduled timestamp",
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing renewal event status: 7511=pending, 7512=processing, 7513=succeeded, 7514=failed, 7515=canceled",
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            comment="Attempt count",
        ),
        sa.Column(
            "last_error",
            sa.String(length=255),
            nullable=False,
            comment="Last error message",
        ),
        sa.Column(
            "payload",
            sa.JSON(),
            nullable=True,
            comment="Renewal event payload",
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(),
            nullable=True,
            comment="Processed timestamp",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
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
        comment="Billing renewal events",
    )
    with op.batch_alter_table("bill_renewal_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_bill_renewal_events_status_scheduled",
            ["status", "scheduled_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_bill_renewal_events_subscription_event_scheduled",
            ["subscription_bid", "event_type", "scheduled_at"],
            unique=False,
        )

    op.create_table(
        "bill_entitlements",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "entitlement_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing entitlement business identifier",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "source_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Entitlement source type: 7411=subscription, 7412=topup, 7413=gift, 7414=usage, 7415=refund, 7416=manual",
        ),
        sa.Column(
            "source_bid",
            sa.String(length=36),
            nullable=False,
            comment="Entitlement source business identifier",
        ),
        sa.Column(
            "branding_enabled",
            sa.SmallInteger(),
            nullable=False,
            comment="Branding enabled flag: 0=disabled, 1=enabled",
        ),
        sa.Column(
            "custom_domain_enabled",
            sa.SmallInteger(),
            nullable=False,
            comment="Custom domain enabled flag: 0=disabled, 1=enabled",
        ),
        sa.Column(
            "priority_class",
            sa.SmallInteger(),
            nullable=False,
            comment="Priority class: 7701=standard, 7702=priority, 7703=vip",
        ),
        sa.Column(
            "analytics_tier",
            sa.SmallInteger(),
            nullable=False,
            comment="Analytics tier: 7711=basic, 7712=advanced, 7713=enterprise",
        ),
        sa.Column(
            "support_tier",
            sa.SmallInteger(),
            nullable=False,
            comment="Support tier: 7721=self_serve, 7722=business_hours, 7723=priority",
        ),
        sa.Column(
            "feature_payload",
            sa.JSON(),
            nullable=True,
            comment="Entitlement feature payload",
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
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
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
            "entitlement_bid",
            name="uq_bill_entitlements_entitlement_bid",
        ),
        comment="Billing entitlements",
    )
    with op.batch_alter_table("bill_entitlements", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_bill_entitlements_creator_bid"),
            ["creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_bill_entitlements_creator_effective_to",
            ["creator_bid", "effective_to"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_entitlements_deleted"),
            ["deleted"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_entitlements_effective_from"),
            ["effective_from"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_entitlements_effective_to"),
            ["effective_to"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_entitlements_entitlement_bid"),
            ["entitlement_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_entitlements_source_bid"),
            ["source_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_entitlements_source_type"),
            ["source_type"],
            unique=False,
        )
        batch_op.create_index(
            "ix_bill_entitlements_source_type_source_bid",
            ["source_type", "source_bid"],
            unique=False,
        )

    op.create_table(
        "bill_domain_bindings",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "domain_binding_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing domain binding business identifier",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "host",
            sa.String(length=255),
            nullable=False,
            comment="Custom domain host",
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Domain binding status: 7601=pending, 7602=verified, 7603=failed, 7604=disabled",
        ),
        sa.Column(
            "verification_method",
            sa.SmallInteger(),
            nullable=False,
            comment="Verification method: 7611=dns_txt, 7612=cname, 7613=file",
        ),
        sa.Column(
            "verification_token",
            sa.String(length=255),
            nullable=False,
            comment="Verification token",
        ),
        sa.Column(
            "last_verified_at",
            sa.DateTime(),
            nullable=True,
            comment="Last verified timestamp",
        ),
        sa.Column(
            "ssl_status",
            sa.SmallInteger(),
            nullable=False,
            comment="SSL status: 7621=not_requested, 7622=provisioning, 7623=active, 7624=failed",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="Domain binding metadata",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
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
            "domain_binding_bid",
            name="uq_bill_domain_bindings_domain_binding_bid",
        ),
        sa.UniqueConstraint(
            "host",
            name="uq_bill_domain_bindings_host",
        ),
        comment="Billing domain bindings",
    )
    with op.batch_alter_table("bill_domain_bindings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_bill_domain_bindings_creator_bid"),
            ["creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_bill_domain_bindings_creator_status",
            ["creator_bid", "status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_domain_bindings_deleted"),
            ["deleted"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_domain_bindings_domain_binding_bid"),
            ["domain_binding_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_domain_bindings_host"),
            ["host"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_domain_bindings_status"),
            ["status"],
            unique=False,
        )

    op.create_table(
        "bill_daily_usage_metrics",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "daily_usage_metric_bid",
            sa.String(length=36),
            nullable=False,
            comment="Daily usage metric business identifier",
        ),
        sa.Column(
            "stat_date",
            sa.String(length=10),
            nullable=False,
            comment="Statistic date",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "shifu_bid",
            sa.String(length=36),
            nullable=False,
            comment="Shifu business identifier",
        ),
        sa.Column(
            "usage_scene",
            sa.SmallInteger(),
            nullable=False,
            comment="Usage scene: 1201=debug, 1202=preview, 1203=production",
        ),
        sa.Column(
            "usage_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Usage type: 1101=LLM, 1102=TTS",
        ),
        sa.Column(
            "provider",
            sa.String(length=32),
            nullable=False,
            comment="Provider name",
        ),
        sa.Column(
            "model",
            sa.String(length=100),
            nullable=False,
            comment="Provider model",
        ),
        sa.Column(
            "billing_metric",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing metric: 7451=llm_input_tokens, 7452=llm_cache_tokens, 7453=llm_output_tokens, 7454=tts_request_count, 7455=tts_output_chars, 7456=tts_input_chars",
        ),
        sa.Column(
            "raw_amount",
            mysql.BIGINT(),
            nullable=False,
            comment="Raw amount",
        ),
        sa.Column(
            "record_count",
            mysql.BIGINT(),
            nullable=False,
            comment="Record count",
        ),
        sa.Column(
            "consumed_credits",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Consumed credits",
        ),
        sa.Column(
            "window_started_at",
            sa.DateTime(),
            nullable=False,
            comment="Window start timestamp",
        ),
        sa.Column(
            "window_ended_at",
            sa.DateTime(),
            nullable=False,
            comment="Window end timestamp",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
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
            "daily_usage_metric_bid",
            name="uq_bill_daily_usage_metrics_daily_usage_metric_bid",
        ),
        sa.UniqueConstraint(
            "stat_date",
            "creator_bid",
            "shifu_bid",
            "usage_scene",
            "usage_type",
            "provider",
            "model",
            "billing_metric",
            name="uq_bill_daily_usage_metrics_lookup",
        ),
        comment="Billing daily usage metrics",
    )
    with op.batch_alter_table("bill_daily_usage_metrics", schema=None) as batch_op:
        batch_op.create_index(
            "ix_bill_daily_usage_metrics_stat_creator",
            ["stat_date", "creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_bill_daily_usage_metrics_billing_metric",
            ["billing_metric"],
            unique=False,
        )

    op.create_table(
        "bill_daily_ledger_summary",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "daily_ledger_summary_bid",
            sa.String(length=36),
            nullable=False,
            comment="Daily ledger summary business identifier",
        ),
        sa.Column(
            "stat_date",
            sa.String(length=10),
            nullable=False,
            comment="Statistic date",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "entry_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing ledger entry type: 7401=grant, 7402=consume, 7403=refund, 7404=expire, 7405=adjustment, 7406=hold, 7407=release",
        ),
        sa.Column(
            "source_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing ledger source type: 7411=subscription, 7412=topup, 7413=gift, 7414=usage, 7415=refund, 7416=manual",
        ),
        sa.Column(
            "amount",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Ledger amount total",
        ),
        sa.Column(
            "entry_count",
            mysql.BIGINT(),
            nullable=False,
            comment="Ledger entry count",
        ),
        sa.Column(
            "window_started_at",
            sa.DateTime(),
            nullable=False,
            comment="Window start timestamp",
        ),
        sa.Column(
            "window_ended_at",
            sa.DateTime(),
            nullable=False,
            comment="Window end timestamp",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
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
            "daily_ledger_summary_bid",
            name="uq_bill_daily_ledger_summary_daily_ledger_summary_bid",
        ),
        sa.UniqueConstraint(
            "stat_date",
            "creator_bid",
            "entry_type",
            "source_type",
            name="uq_bill_daily_ledger_summary_lookup",
        ),
        comment="Billing daily ledger summary",
    )
    with op.batch_alter_table("bill_daily_ledger_summary", schema=None) as batch_op:
        batch_op.create_index(
            "ix_bill_daily_ledger_summary_stat_creator",
            ["stat_date", "creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_bill_daily_ledger_summary_source_type",
            ["source_type"],
            unique=False,
        )

    with op.batch_alter_table("bill_products", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_bill_products_product_bid",
            ["product_bid"],
        )

    with op.batch_alter_table("bill_subscriptions", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_bill_subscriptions_subscription_bid",
            ["subscription_bid"],
        )

    with op.batch_alter_table("bill_orders", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_bill_orders_bill_order_bid",
            ["bill_order_bid"],
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

    with op.batch_alter_table("bill_renewal_events", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_bill_renewal_events_renewal_event_bid",
            ["renewal_event_bid"],
        )
        batch_op.create_unique_constraint(
            "uq_bill_renewal_events_subscription_event_scheduled",
            ["subscription_bid", "event_type", "scheduled_at"],
        )

    with op.batch_alter_table("order_pingxx_orders", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "biz_domain",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'order'"),
                comment="Business domain: order=legacy learner order, billing=creator billing",
            )
        )
        batch_op.add_column(
            sa.Column(
                "bill_order_bid",
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
            "ix_order_pingxx_orders_bill_order_bid",
            ["bill_order_bid"],
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
            "ix_order_pingxx_orders_biz_domain_bill_order_bid",
            ["biz_domain", "bill_order_bid"],
            unique=False,
        )

    with op.batch_alter_table("order_stripe_orders", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "biz_domain",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'order'"),
                comment="Business domain: order=legacy learner order, billing=creator billing",
            )
        )
        batch_op.add_column(
            sa.Column(
                "bill_order_bid",
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
            "ix_order_stripe_orders_bill_order_bid",
            ["bill_order_bid"],
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
            "ix_order_stripe_orders_biz_domain_bill_order_bid",
            ["biz_domain", "bill_order_bid"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("order_stripe_orders", schema=None) as batch_op:
        batch_op.drop_index("ix_order_stripe_orders_biz_domain_bill_order_bid")
        batch_op.drop_index("ix_order_stripe_orders_biz_domain_order_bid")
        batch_op.drop_index("ix_order_stripe_orders_creator_bid")
        batch_op.drop_index("ix_order_stripe_orders_bill_order_bid")
        batch_op.drop_index("ix_order_stripe_orders_biz_domain")
        batch_op.drop_column("creator_bid")
        batch_op.drop_column("bill_order_bid")
        batch_op.drop_column("biz_domain")

    with op.batch_alter_table("order_pingxx_orders", schema=None) as batch_op:
        batch_op.drop_index("ix_order_pingxx_orders_biz_domain_bill_order_bid")
        batch_op.drop_index("ix_order_pingxx_orders_biz_domain_order_bid")
        batch_op.drop_index("ix_order_pingxx_orders_creator_bid")
        batch_op.drop_index("ix_order_pingxx_orders_bill_order_bid")
        batch_op.drop_index("ix_order_pingxx_orders_biz_domain")
        batch_op.drop_column("creator_bid")
        batch_op.drop_column("bill_order_bid")
        batch_op.drop_column("biz_domain")

    with op.batch_alter_table("bill_renewal_events", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_bill_renewal_events_subscription_event_scheduled",
            type_="unique",
        )
        batch_op.drop_constraint(
            "uq_bill_renewal_events_renewal_event_bid",
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

    with op.batch_alter_table("bill_orders", schema=None) as batch_op:
        batch_op.drop_constraint("uq_bill_orders_bill_order_bid", type_="unique")

    with op.batch_alter_table("bill_subscriptions", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_bill_subscriptions_subscription_bid",
            type_="unique",
        )

    with op.batch_alter_table("bill_products", schema=None) as batch_op:
        batch_op.drop_constraint("uq_bill_products_product_bid", type_="unique")

    op.drop_table("bill_daily_ledger_summary")
    op.drop_table("bill_daily_usage_metrics")
    op.drop_table("bill_domain_bindings")
    op.drop_table("bill_entitlements")
    op.drop_table("bill_renewal_events")
    op.drop_table("credit_usage_rates")
    op.drop_table("credit_ledger_entries")
    op.drop_table("credit_wallet_buckets")
    op.drop_table("credit_wallets")
    op.drop_table("bill_orders")
    op.drop_table("bill_subscriptions")
    op.drop_table("bill_products")
