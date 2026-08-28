"""add campaign provider discounts.

Revision ID: e9a1b2c3d4f5
Revises: d8c4f6a1b2e3
Create Date: 2026-08-25 18:45:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "e9a1b2c3d4f5"
down_revision = "d8c4f6a1b2e3"
branch_labels = None
depends_on = None


ACTIVE_STATUS = 7943


def _billing_base_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "deleted", sa.SmallInteger(), nullable=False, comment="Deletion flag"
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, comment="Creation timestamp"
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, comment="Last update timestamp"
        ),
    ]


def upgrade():
    op.create_table(
        "bill_campaign_provider_discounts",
        sa.Column(
            "campaign_provider_discount_bid",
            sa.String(length=36),
            nullable=False,
            comment="Campaign provider discount business identifier",
        ),
        sa.Column(
            "campaign_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing campaign business identifier",
        ),
        sa.Column(
            "product_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing product business identifier",
        ),
        sa.Column(
            "product_provider_price_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing product provider price mapping business identifier",
        ),
        sa.Column(
            "provider",
            sa.String(length=32),
            nullable=False,
            comment="Payment provider name",
        ),
        sa.Column(
            "provider_account_id",
            sa.String(length=255),
            nullable=False,
            comment="Provider account identifier",
        ),
        sa.Column(
            "provider_product_id",
            sa.String(length=255),
            nullable=False,
            comment="Provider product identifier",
        ),
        sa.Column(
            "provider_price_id",
            sa.String(length=255),
            nullable=False,
            comment="Provider price identifier",
        ),
        sa.Column(
            "provider_coupon_id",
            sa.String(length=255),
            nullable=False,
            comment="Provider coupon identifier",
        ),
        sa.Column(
            "livemode",
            sa.SmallInteger(),
            nullable=False,
            comment="Provider live mode flag",
        ),
        sa.Column(
            "benefit_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Campaign benefit type code",
        ),
        sa.Column(
            "discount_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Campaign discount type code",
        ),
        sa.Column(
            "list_price_amount",
            mysql.BIGINT(),
            nullable=False,
            comment="List price amount in minor units",
        ),
        sa.Column(
            "campaign_price_amount",
            mysql.BIGINT(),
            nullable=False,
            comment="Campaign price amount in minor units",
        ),
        sa.Column(
            "discount_amount",
            mysql.BIGINT(),
            nullable=False,
            comment="Discount amount in minor units",
        ),
        sa.Column(
            "discount_percent",
            sa.Numeric(precision=6, scale=2),
            nullable=False,
            comment="Discount percent value",
        ),
        sa.Column(
            "currency", sa.String(length=16), nullable=False, comment="Currency code"
        ),
        sa.Column(
            "duration",
            sa.String(length=16),
            nullable=False,
            comment="Provider discount duration",
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Provider discount status code",
        ),
        sa.Column(
            "provider_coupon_live_scope",
            sa.String(length=16),
            sa.Computed(
                "CASE WHEN deleted = 0 AND provider_coupon_id <> '' THEN 'live' ELSE NULL END",
                persisted=True,
            ),
            nullable=True,
            comment="Generated key enforcing one live provider coupon mapping",
        ),
        sa.Column(
            "active_scope",
            sa.String(length=16),
            sa.Computed(
                f"CASE WHEN status = {ACTIVE_STATUS} AND deleted = 0 THEN 'active' ELSE NULL END",
                persisted=True,
            ),
            nullable=True,
            comment="Generated key enforcing one active discount per campaign SKU price",
        ),
        sa.Column(
            "validated_at",
            sa.DateTime(),
            nullable=True,
            comment="Last provider validation timestamp",
        ),
        sa.Column(
            "activated_at", sa.DateTime(), nullable=True, comment="Activation timestamp"
        ),
        sa.Column(
            "retired_at", sa.DateTime(), nullable=True, comment="Retirement timestamp"
        ),
        sa.Column(
            "failure_code",
            sa.String(length=64),
            nullable=False,
            comment="Provider discount failure code",
        ),
        sa.Column(
            "failure_message",
            sa.String(length=500),
            nullable=False,
            comment="Provider discount failure message",
        ),
        sa.Column(
            "replaces_discount_bid",
            sa.String(length=36),
            nullable=False,
            comment="Previous provider discount business identifier",
        ),
        sa.Column(
            "metadata", sa.JSON(), nullable=True, comment="Provider discount metadata"
        ),
        sa.Column(
            "created_user_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator user business identifier",
        ),
        sa.Column(
            "updated_user_bid",
            sa.String(length=36),
            nullable=False,
            comment="Last updater user business identifier",
        ),
        *_billing_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_provider_discount_bid",
            name="uq_bill_campaign_provider_discounts_bid",
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_account_id",
            "provider_coupon_id",
            "provider_coupon_live_scope",
            name="uq_bill_campaign_provider_discounts_coupon",
        ),
        sa.UniqueConstraint(
            "campaign_bid",
            "product_bid",
            "product_provider_price_bid",
            "provider",
            "provider_account_id",
            "active_scope",
            name="uq_bill_campaign_provider_discounts_active_scope",
        ),
        comment="Provider discounts published from billing campaigns",
    )
    op.create_index(
        "ix_bill_campaign_provider_discounts_campaign_product",
        "bill_campaign_provider_discounts",
        [
            "campaign_bid",
            "product_bid",
            "product_provider_price_bid",
            "provider",
            "provider_account_id",
        ],
    )
    op.create_index(
        "ix_bill_campaign_provider_discounts_product_status",
        "bill_campaign_provider_discounts",
        ["product_bid", "status"],
    )
    for column in (
        "campaign_bid",
        "product_bid",
        "product_provider_price_bid",
        "provider",
        "provider_price_id",
        "provider_coupon_id",
        "status",
        "created_user_bid",
        "updated_user_bid",
        "deleted",
    ):
        op.create_index(
            f"ix_bill_campaign_provider_discounts_{column}",
            "bill_campaign_provider_discounts",
            [column],
        )


def downgrade():
    op.drop_table("bill_campaign_provider_discounts")
