"""add billing product provider prices.

Revision ID: c7b9e1a2d4f6
Revises: a9c3d5e7f1b2
Create Date: 2026-08-20 12:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "c7b9e1a2d4f6"
down_revision = "a9c3d5e7f1b2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bill_product_provider_prices",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "provider_price_bid",
            sa.String(length=36),
            nullable=False,
            comment="Provider price mapping business identifier",
        ),
        sa.Column(
            "product_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing product business identifier",
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
            "livemode",
            sa.SmallInteger(),
            nullable=False,
            comment="Provider live mode flag",
        ),
        sa.Column(
            "currency",
            sa.String(length=16),
            nullable=False,
            comment="Provider price currency code",
        ),
        sa.Column(
            "unit_amount",
            mysql.BIGINT(),
            nullable=False,
            comment="Provider price unit amount",
        ),
        sa.Column(
            "billing_mode",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing mode code validated against the provider price",
        ),
        sa.Column(
            "billing_interval",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing interval code validated against the provider price",
        ),
        sa.Column(
            "billing_interval_count",
            sa.Integer(),
            nullable=False,
            comment="Billing interval count validated against the provider price",
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Provider price mapping status code",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag",
        ),
        sa.Column(
            "provider_price_live_scope",
            sa.String(length=16),
            sa.Computed(
                "CASE WHEN deleted = 0 THEN 'live' ELSE NULL END",
                persisted=True,
            ),
            nullable=True,
            comment="Generated key enforcing one live provider price mapping",
        ),
        sa.Column(
            "active_scope",
            sa.String(length=16),
            sa.Computed(
                "CASE WHEN status = 7902 AND deleted = 0 THEN 'active' ELSE NULL END",
                persisted=True,
            ),
            nullable=True,
            comment="Generated key enforcing one active price per SKU scope",
        ),
        sa.Column(
            "validated_at",
            sa.DateTime(),
            nullable=True,
            comment="Last provider validation timestamp",
        ),
        sa.Column(
            "activated_at",
            sa.DateTime(),
            nullable=True,
            comment="Activation timestamp",
        ),
        sa.Column(
            "retired_at",
            sa.DateTime(),
            nullable=True,
            comment="Retirement timestamp",
        ),
        sa.Column(
            "validation_error",
            sa.Text(),
            nullable=True,
            comment="Last validation error summary",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="Provider price mapping metadata",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_price_bid",
            name="uq_bill_product_provider_prices_bid",
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_account_id",
            "livemode",
            "provider_price_id",
            "provider_price_live_scope",
            name="uq_bill_product_provider_prices_provider_price",
        ),
        sa.UniqueConstraint(
            "product_bid",
            "provider",
            "provider_account_id",
            "livemode",
            "active_scope",
            name="uq_bill_product_provider_prices_active_scope",
        ),
        comment="Provider price mappings for billing products",
    )
    with op.batch_alter_table("bill_product_provider_prices", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_bill_product_provider_prices_deleted"),
            ["deleted"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_product_provider_prices_product_bid"),
            ["product_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_product_provider_prices_provider"),
            ["provider"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_product_provider_prices_provider_price_bid"),
            ["provider_price_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_product_provider_prices_provider_price_id"),
            ["provider_price_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_product_provider_prices_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            "ix_bill_product_provider_prices_product_status",
            ["product_bid", "status"],
            unique=False,
        )
        batch_op.create_index(
            "ix_bill_product_provider_prices_provider_status",
            ["provider", "status"],
            unique=False,
        )
        batch_op.create_index(
            "ix_bill_product_provider_prices_provider_product",
            ["provider", "provider_account_id", "provider_product_id"],
            unique=False,
        )


def downgrade():
    op.drop_table("bill_product_provider_prices")
