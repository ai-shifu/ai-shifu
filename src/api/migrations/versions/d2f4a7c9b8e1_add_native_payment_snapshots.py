"""add native payment snapshots

Revision ID: d2f4a7c9b8e1
Revises: b114d7f5e2c1
Create Date: 2026-04-27 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "d2f4a7c9b8e1"
down_revision = "b114d7f5e2c1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "order_native_payment_orders",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "native_payment_order_bid",
            sa.String(length=36),
            nullable=False,
            comment="Native payment snapshot business identifier",
        ),
        sa.Column(
            "biz_domain",
            sa.String(length=16),
            nullable=False,
            comment="Business domain",
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
            "user_bid",
            sa.String(length=36),
            nullable=False,
            comment="User business identifier",
        ),
        sa.Column(
            "shifu_bid",
            sa.String(length=36),
            nullable=False,
            comment="Shifu business identifier",
        ),
        sa.Column(
            "order_bid",
            sa.String(length=36),
            nullable=False,
            comment="Order business identifier",
        ),
        sa.Column(
            "payment_provider",
            sa.String(length=32),
            nullable=False,
            comment="Native payment provider",
        ),
        sa.Column(
            "provider_attempt_id",
            sa.String(length=64),
            nullable=False,
            comment="Provider-side merchant order identifier",
        ),
        sa.Column(
            "transaction_id",
            sa.String(length=128),
            nullable=False,
            comment="Provider transaction identifier",
        ),
        sa.Column(
            "channel",
            sa.String(length=36),
            nullable=False,
            comment="Payment channel",
        ),
        sa.Column(
            "amount",
            mysql.BIGINT(),
            nullable=False,
            comment="Payment amount",
        ),
        sa.Column(
            "currency",
            sa.String(length=36),
            nullable=False,
            comment="Currency",
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Status of the order: 0=pending, 1=paid, 2=refunded, 3=closed, 4=failed",
        ),
        sa.Column(
            "raw_status",
            sa.String(length=64),
            nullable=False,
            comment="Provider raw status or event type",
        ),
        sa.Column(
            "raw_request",
            sa.Text(),
            nullable=False,
            comment="Raw provider request payload",
        ),
        sa.Column(
            "raw_response",
            sa.Text(),
            nullable=False,
            comment="Raw provider response payload",
        ),
        sa.Column(
            "raw_notification",
            sa.Text(),
            nullable=False,
            comment="Raw provider notification payload",
        ),
        sa.Column(
            "metadata_json",
            sa.Text(),
            nullable=False,
            comment="Provider metadata JSON string",
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
            comment="Creation time",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Update time",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_comment="Order native payment provider snapshots",
    )
    op.create_index(
        op.f("ix_order_native_payment_orders_native_payment_order_bid"),
        "order_native_payment_orders",
        ["native_payment_order_bid"],
        unique=False,
    )
    op.create_index(
        op.f("ix_order_native_payment_orders_biz_domain"),
        "order_native_payment_orders",
        ["biz_domain"],
        unique=False,
    )
    op.create_index(
        op.f("ix_order_native_payment_orders_bill_order_bid"),
        "order_native_payment_orders",
        ["bill_order_bid"],
        unique=False,
    )
    op.create_index(
        op.f("ix_order_native_payment_orders_creator_bid"),
        "order_native_payment_orders",
        ["creator_bid"],
        unique=False,
    )
    op.create_index(
        op.f("ix_order_native_payment_orders_user_bid"),
        "order_native_payment_orders",
        ["user_bid"],
        unique=False,
    )
    op.create_index(
        op.f("ix_order_native_payment_orders_shifu_bid"),
        "order_native_payment_orders",
        ["shifu_bid"],
        unique=False,
    )
    op.create_index(
        op.f("ix_order_native_payment_orders_order_bid"),
        "order_native_payment_orders",
        ["order_bid"],
        unique=False,
    )
    op.create_index(
        op.f("ix_order_native_payment_orders_payment_provider"),
        "order_native_payment_orders",
        ["payment_provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_order_native_payment_orders_provider_attempt_id"),
        "order_native_payment_orders",
        ["provider_attempt_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_order_native_payment_orders_transaction_id"),
        "order_native_payment_orders",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_order_native_payment_orders_biz_domain_order_bid",
        "order_native_payment_orders",
        ["biz_domain", "order_bid"],
        unique=False,
    )
    op.create_index(
        "ix_order_native_payment_orders_biz_domain_bill_order_bid",
        "order_native_payment_orders",
        ["biz_domain", "bill_order_bid"],
        unique=False,
    )
    op.create_index(
        "ix_order_native_payment_orders_provider_attempt",
        "order_native_payment_orders",
        ["payment_provider", "provider_attempt_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_order_native_payment_orders_provider_attempt",
        table_name="order_native_payment_orders",
    )
    op.drop_index(
        "ix_order_native_payment_orders_biz_domain_bill_order_bid",
        table_name="order_native_payment_orders",
    )
    op.drop_index(
        "ix_order_native_payment_orders_biz_domain_order_bid",
        table_name="order_native_payment_orders",
    )
    op.drop_index(
        op.f("ix_order_native_payment_orders_transaction_id"),
        table_name="order_native_payment_orders",
    )
    op.drop_index(
        op.f("ix_order_native_payment_orders_provider_attempt_id"),
        table_name="order_native_payment_orders",
    )
    op.drop_index(
        op.f("ix_order_native_payment_orders_payment_provider"),
        table_name="order_native_payment_orders",
    )
    op.drop_index(
        op.f("ix_order_native_payment_orders_order_bid"),
        table_name="order_native_payment_orders",
    )
    op.drop_index(
        op.f("ix_order_native_payment_orders_shifu_bid"),
        table_name="order_native_payment_orders",
    )
    op.drop_index(
        op.f("ix_order_native_payment_orders_user_bid"),
        table_name="order_native_payment_orders",
    )
    op.drop_index(
        op.f("ix_order_native_payment_orders_creator_bid"),
        table_name="order_native_payment_orders",
    )
    op.drop_index(
        op.f("ix_order_native_payment_orders_bill_order_bid"),
        table_name="order_native_payment_orders",
    )
    op.drop_index(
        op.f("ix_order_native_payment_orders_biz_domain"),
        table_name="order_native_payment_orders",
    )
    op.drop_index(
        op.f("ix_order_native_payment_orders_native_payment_order_bid"),
        table_name="order_native_payment_orders",
    )
    op.drop_table("order_native_payment_orders")
