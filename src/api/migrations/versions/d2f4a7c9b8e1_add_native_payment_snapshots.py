"""add native payment snapshots

Revision ID: d2f4a7c9b8e1
Revises: 4d9f6c7b8a1e
Create Date: 2026-04-27 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "d2f4a7c9b8e1"
down_revision = "4d9f6c7b8a1e"
branch_labels = None
depends_on = None


def upgrade():
    _create_provider_table(
        table_name="order_alipay_orders",
        provider_bid_column="alipay_order_bid",
        table_comment="Order Alipay payment provider snapshots",
    )
    _create_provider_table(
        table_name="order_wechatpay_orders",
        provider_bid_column="wechatpay_order_bid",
        table_comment="Order WeChat Pay payment provider snapshots",
    )


def downgrade():
    op.drop_index(
        "ix_order_wechatpay_orders_biz_domain_bill_order_bid",
        table_name="order_wechatpay_orders",
    )
    op.drop_index(
        "ix_order_wechatpay_orders_biz_domain_order_bid",
        table_name="order_wechatpay_orders",
    )
    op.drop_index(
        op.f("ix_order_wechatpay_orders_transaction_id"),
        table_name="order_wechatpay_orders",
    )
    op.drop_index(
        op.f("ix_order_wechatpay_orders_provider_attempt_id"),
        table_name="order_wechatpay_orders",
    )
    op.drop_index(
        op.f("ix_order_wechatpay_orders_order_bid"),
        table_name="order_wechatpay_orders",
    )
    op.drop_index(
        op.f("ix_order_wechatpay_orders_shifu_bid"),
        table_name="order_wechatpay_orders",
    )
    op.drop_index(
        op.f("ix_order_wechatpay_orders_user_bid"),
        table_name="order_wechatpay_orders",
    )
    op.drop_index(
        op.f("ix_order_wechatpay_orders_creator_bid"),
        table_name="order_wechatpay_orders",
    )
    op.drop_index(
        op.f("ix_order_wechatpay_orders_bill_order_bid"),
        table_name="order_wechatpay_orders",
    )
    op.drop_index(
        op.f("ix_order_wechatpay_orders_biz_domain"),
        table_name="order_wechatpay_orders",
    )
    op.drop_index(
        op.f("ix_order_wechatpay_orders_wechatpay_order_bid"),
        table_name="order_wechatpay_orders",
    )
    op.drop_table("order_wechatpay_orders")

    op.drop_index(
        "ix_order_alipay_orders_biz_domain_bill_order_bid",
        table_name="order_alipay_orders",
    )
    op.drop_index(
        "ix_order_alipay_orders_biz_domain_order_bid",
        table_name="order_alipay_orders",
    )
    op.drop_index(
        op.f("ix_order_alipay_orders_transaction_id"),
        table_name="order_alipay_orders",
    )
    op.drop_index(
        op.f("ix_order_alipay_orders_provider_attempt_id"),
        table_name="order_alipay_orders",
    )
    op.drop_index(
        op.f("ix_order_alipay_orders_order_bid"),
        table_name="order_alipay_orders",
    )
    op.drop_index(
        op.f("ix_order_alipay_orders_shifu_bid"),
        table_name="order_alipay_orders",
    )
    op.drop_index(
        op.f("ix_order_alipay_orders_user_bid"),
        table_name="order_alipay_orders",
    )
    op.drop_index(
        op.f("ix_order_alipay_orders_creator_bid"),
        table_name="order_alipay_orders",
    )
    op.drop_index(
        op.f("ix_order_alipay_orders_bill_order_bid"),
        table_name="order_alipay_orders",
    )
    op.drop_index(
        op.f("ix_order_alipay_orders_biz_domain"),
        table_name="order_alipay_orders",
    )
    op.drop_index(
        op.f("ix_order_alipay_orders_alipay_order_bid"),
        table_name="order_alipay_orders",
    )
    op.drop_table("order_alipay_orders")


def _create_provider_table(
    *,
    table_name: str,
    provider_bid_column: str,
    table_comment: str,
) -> None:
    op.create_table(
        table_name,
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            provider_bid_column,
            sa.String(length=36),
            nullable=False,
            comment="Provider payment snapshot business identifier",
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
        mysql_comment=table_comment,
    )
    op.create_index(
        op.f(f"ix_{table_name}_{provider_bid_column}"),
        table_name,
        [provider_bid_column],
        unique=True,
    )
    for column_name in (
        "biz_domain",
        "bill_order_bid",
        "creator_bid",
        "user_bid",
        "shifu_bid",
        "order_bid",
        "provider_attempt_id",
        "transaction_id",
    ):
        op.create_index(
            op.f(f"ix_{table_name}_{column_name}"),
            table_name,
            [column_name],
            unique=False,
        )
    op.create_index(
        f"ix_{table_name}_biz_domain_order_bid",
        table_name,
        ["biz_domain", "order_bid"],
        unique=False,
    )
    op.create_index(
        f"ix_{table_name}_biz_domain_bill_order_bid",
        table_name,
        ["biz_domain", "bill_order_bid"],
        unique=False,
    )
