"""add stripe payment channel

Revision ID: c9c92880fc67
Revises: a4d68cce5ce6
Create Date: 2025-10-29 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "c9c92880fc67"
down_revision = "a4d68cce5ce6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "order_orders",
        sa.Column(
            "payment_channel",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'pingxx'"),
            comment="Payment channel",
        ),
    )
    with op.batch_alter_table("order_orders", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_order_orders_payment_channel"),
            ["payment_channel"],
            unique=False,
        )

    op.execute(
        "UPDATE order_orders SET payment_channel = 'pingxx' "
        "WHERE payment_channel IS NULL OR payment_channel = ''"
    )

    op.create_table(
        "order_stripe_orders",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column(
            "stripe_order_bid",
            sa.String(length=36),
            nullable=False,
            comment="Stripe order business identifier",
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
            "payment_intent_id",
            sa.String(length=255),
            nullable=False,
            comment="Stripe payment intent identifier",
        ),
        sa.Column(
            "checkout_session_id",
            sa.String(length=255),
            nullable=False,
            comment="Stripe checkout session identifier",
        ),
        sa.Column(
            "latest_charge_id",
            sa.String(length=255),
            nullable=False,
            comment="Latest Stripe charge identifier",
        ),
        sa.Column(
            "amount",
            mysql.BIGINT(),
            nullable=False,
            comment="Payment amount in cents",
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
            "receipt_url",
            sa.String(length=255),
            nullable=False,
            comment="Stripe receipt URL",
        ),
        sa.Column(
            "payment_method",
            sa.String(length=255),
            nullable=False,
            comment="Stripe payment method identifier",
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
            "metadata_json",
            sa.Text(),
            nullable=False,
            comment="Stripe metadata JSON string",
        ),
        sa.Column(
            "payment_intent_object",
            sa.Text(),
            nullable=False,
            comment="Stripe payment intent raw object",
        ),
        sa.Column(
            "checkout_session_object",
            sa.Text(),
            nullable=False,
            comment="Stripe checkout session raw object",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="Creation time"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="Update time"),
        sa.PrimaryKeyConstraint("id"),
        comment="Order stripe orders",
    )

    with op.batch_alter_table("order_stripe_orders", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_order_stripe_orders_stripe_order_bid"),
            ["stripe_order_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_order_stripe_orders_user_bid"),
            ["user_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_order_stripe_orders_shifu_bid"),
            ["shifu_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_order_stripe_orders_order_bid"),
            ["order_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_order_stripe_orders_payment_intent_id"),
            ["payment_intent_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_order_stripe_orders_checkout_session_id"),
            ["checkout_session_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_order_stripe_orders_latest_charge_id"),
            ["latest_charge_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("order_stripe_orders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_order_stripe_orders_latest_charge_id"))
        batch_op.drop_index(batch_op.f("ix_order_stripe_orders_checkout_session_id"))
        batch_op.drop_index(batch_op.f("ix_order_stripe_orders_payment_intent_id"))
        batch_op.drop_index(batch_op.f("ix_order_stripe_orders_order_bid"))
        batch_op.drop_index(batch_op.f("ix_order_stripe_orders_shifu_bid"))
        batch_op.drop_index(batch_op.f("ix_order_stripe_orders_user_bid"))
        batch_op.drop_index(batch_op.f("ix_order_stripe_orders_stripe_order_bid"))

    op.drop_table("order_stripe_orders")

    with op.batch_alter_table("order_orders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_order_orders_payment_channel"))

    op.drop_column("order_orders", "payment_channel")
