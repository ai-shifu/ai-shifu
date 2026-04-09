"""Add biz-domain columns to legacy provider raw tables.

Revision ID: f6a7b8c9d0e1
Revises: f1a2b3c4d5e6
Create Date: 2026-04-09 15:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f6a7b8c9d0e1"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
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
            batch_op.f("ix_order_pingxx_orders_biz_domain"),
            ["biz_domain"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_order_pingxx_orders_billing_order_bid"),
            ["billing_order_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_order_pingxx_orders_creator_bid"),
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
            batch_op.f("ix_order_stripe_orders_biz_domain"),
            ["biz_domain"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_order_stripe_orders_billing_order_bid"),
            ["billing_order_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_order_stripe_orders_creator_bid"),
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
        batch_op.drop_index(batch_op.f("ix_order_stripe_orders_creator_bid"))
        batch_op.drop_index(batch_op.f("ix_order_stripe_orders_billing_order_bid"))
        batch_op.drop_index(batch_op.f("ix_order_stripe_orders_biz_domain"))
        batch_op.drop_column("creator_bid")
        batch_op.drop_column("billing_order_bid")
        batch_op.drop_column("biz_domain")

    with op.batch_alter_table("order_pingxx_orders", schema=None) as batch_op:
        batch_op.drop_index("ix_order_pingxx_orders_biz_domain_billing_order_bid")
        batch_op.drop_index("ix_order_pingxx_orders_biz_domain_order_bid")
        batch_op.drop_index(batch_op.f("ix_order_pingxx_orders_creator_bid"))
        batch_op.drop_index(batch_op.f("ix_order_pingxx_orders_billing_order_bid"))
        batch_op.drop_index(batch_op.f("ix_order_pingxx_orders_biz_domain"))
        batch_op.drop_column("creator_bid")
        batch_op.drop_column("billing_order_bid")
        batch_op.drop_column("biz_domain")
