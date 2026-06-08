"""add billing campaign product rule columns

Revision ID: 4f2b7d8e9c1a
Revises: 1d8c4e7f9a2b
Create Date: 2026-05-17

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "4f2b7d8e9c1a"
down_revision = "1d8c4e7f9a2b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "bill_campaign_products",
        sa.Column(
            "discount_type",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
            comment="Per-product campaign discount type code",
        ),
    )
    op.add_column(
        "bill_campaign_products",
        sa.Column(
            "discount_amount",
            mysql.BIGINT(),
            nullable=False,
            server_default="0",
            comment="Per-product campaign discount amount in minor units",
        ),
    )
    op.add_column(
        "bill_campaign_products",
        sa.Column(
            "discount_percent",
            sa.Numeric(precision=6, scale=2),
            nullable=False,
            server_default="0",
            comment="Per-product campaign discount percent",
        ),
    )
    op.add_column(
        "bill_campaign_products",
        sa.Column(
            "campaign_price_amount",
            mysql.BIGINT(),
            nullable=False,
            server_default="0",
            comment="Per-product campaign price amount in minor units",
        ),
    )
    op.add_column(
        "bill_campaign_products",
        sa.Column(
            "bonus_credit_amount",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            server_default="0",
            comment="Per-product campaign bonus credit amount",
        ),
    )


def downgrade():
    op.drop_column("bill_campaign_products", "bonus_credit_amount")
    op.drop_column("bill_campaign_products", "campaign_price_amount")
    op.drop_column("bill_campaign_products", "discount_percent")
    op.drop_column("bill_campaign_products", "discount_amount")
    op.drop_column("bill_campaign_products", "discount_type")
