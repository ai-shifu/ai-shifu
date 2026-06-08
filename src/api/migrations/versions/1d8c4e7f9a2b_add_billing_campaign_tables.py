"""add billing campaign tables

Revision ID: 1d8c4e7f9a2b
Revises: d2f4a7c9b8e1
Create Date: 2026-05-17

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "1d8c4e7f9a2b"
down_revision = "d2f4a7c9b8e1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "bill_orders",
        sa.Column(
            "campaign_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Applied billing campaign business identifier",
        ),
    )
    op.add_column(
        "bill_orders",
        sa.Column(
            "campaign_benefit_type",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
            comment="Applied billing campaign benefit type code",
        ),
    )
    op.add_column(
        "bill_orders",
        sa.Column(
            "campaign_discount_amount",
            mysql.BIGINT(),
            nullable=False,
            server_default="0",
            comment="Applied billing campaign discount amount in minor units",
        ),
    )
    op.add_column(
        "bill_orders",
        sa.Column(
            "campaign_bonus_credit_amount",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            server_default="0",
            comment="Applied billing campaign bonus credit amount",
        ),
    )
    with op.batch_alter_table("bill_orders", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_bill_orders_campaign_bid"),
            ["campaign_bid"],
            unique=False,
        )

    op.create_table(
        "bill_campaigns",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag",
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
        sa.Column(
            "campaign_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing campaign business identifier",
        ),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
            comment="Operator-facing campaign name",
        ),
        sa.Column(
            "note",
            sa.String(length=500),
            nullable=False,
            comment="Operator-facing campaign note",
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
            "discount_amount",
            mysql.BIGINT(),
            nullable=False,
            comment="Fixed discount amount in minor units",
        ),
        sa.Column(
            "discount_percent",
            sa.Numeric(precision=6, scale=2),
            nullable=False,
            comment="Percent discount value",
        ),
        sa.Column(
            "bonus_credit_amount",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Bonus credit amount",
        ),
        sa.Column(
            "enabled",
            sa.SmallInteger(),
            nullable=False,
            comment="Enabled flag",
        ),
        sa.Column(
            "start_at",
            sa.DateTime(),
            nullable=False,
            comment="Campaign start timestamp",
        ),
        sa.Column(
            "end_at",
            sa.DateTime(),
            nullable=False,
            comment="Campaign end timestamp",
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_bid", name="uq_bill_campaigns_campaign_bid"),
        comment="Billing campaign definitions",
    )
    with op.batch_alter_table("bill_campaigns", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_bill_campaigns_campaign_bid"),
            ["campaign_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_campaigns_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_bill_campaigns_enabled"), ["enabled"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_bill_campaigns_benefit_type"),
            ["benefit_type"],
            unique=False,
        )
        batch_op.create_index(
            "ix_bill_campaigns_enabled_start_end",
            ["enabled", "start_at", "end_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_campaigns_start_at"), ["start_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_bill_campaigns_end_at"), ["end_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_bill_campaigns_created_user_bid"),
            ["created_user_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_campaigns_updated_user_bid"),
            ["updated_user_bid"],
            unique=False,
        )

    op.create_table(
        "bill_campaign_products",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag",
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
            "product_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing product type snapshot",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_bid",
            "product_bid",
            name="uq_bill_campaign_products_campaign_product",
        ),
        comment="Billing campaign product bindings",
    )
    with op.batch_alter_table("bill_campaign_products", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_bill_campaign_products_campaign_bid"),
            ["campaign_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_campaign_products_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_bill_campaign_products_product_bid"),
            ["product_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_campaign_products_product_type"),
            ["product_type"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("bill_campaign_products", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bill_campaign_products_product_type"))
        batch_op.drop_index(batch_op.f("ix_bill_campaign_products_product_bid"))
        batch_op.drop_index(batch_op.f("ix_bill_campaign_products_deleted"))
        batch_op.drop_index(batch_op.f("ix_bill_campaign_products_campaign_bid"))
    op.drop_table("bill_campaign_products")

    with op.batch_alter_table("bill_campaigns", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bill_campaigns_updated_user_bid"))
        batch_op.drop_index(batch_op.f("ix_bill_campaigns_created_user_bid"))
        batch_op.drop_index(batch_op.f("ix_bill_campaigns_end_at"))
        batch_op.drop_index(batch_op.f("ix_bill_campaigns_start_at"))
        batch_op.drop_index("ix_bill_campaigns_enabled_start_end")
        batch_op.drop_index(batch_op.f("ix_bill_campaigns_benefit_type"))
        batch_op.drop_index(batch_op.f("ix_bill_campaigns_enabled"))
        batch_op.drop_index(batch_op.f("ix_bill_campaigns_deleted"))
        batch_op.drop_index(batch_op.f("ix_bill_campaigns_campaign_bid"))
    op.drop_table("bill_campaigns")

    with op.batch_alter_table("bill_orders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bill_orders_campaign_bid"))
    op.drop_column("bill_orders", "campaign_bonus_credit_amount")
    op.drop_column("bill_orders", "campaign_discount_amount")
    op.drop_column("bill_orders", "campaign_benefit_type")
    op.drop_column("bill_orders", "campaign_bid")
