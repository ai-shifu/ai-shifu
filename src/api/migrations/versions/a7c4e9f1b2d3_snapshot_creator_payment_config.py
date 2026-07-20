"""snapshot creator payment config on learner orders

Revision ID: a7c4e9f1b2d3
Revises: f6b2a4d8c9e0
Create Date: 2026-07-12 16:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "a7c4e9f1b2d3"
down_revision = "f6b2a4d8c9e0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("order_orders", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "creator_bid",
                sa.String(length=36),
                nullable=False,
                server_default="",
                comment="Course owner identifier",
            )
        )
        batch_op.add_column(
            sa.Column(
                "payment_integration_bid",
                sa.String(length=36),
                nullable=False,
                server_default="",
                comment="Snapshotted creator integration",
            )
        )
        batch_op.create_index(
            batch_op.f("ix_order_orders_creator_bid"), ["creator_bid"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_order_orders_payment_integration_bid"),
            ["payment_integration_bid"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("order_orders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_order_orders_payment_integration_bid"))
        batch_op.drop_index(batch_op.f("ix_order_orders_creator_bid"))
        batch_op.drop_column("payment_integration_bid")
        batch_op.drop_column("creator_bid")
