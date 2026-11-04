"""record who granted learner orders.

Revision ID: b5e2d7a9c1f4
Revises: c3d8e1f4a6b2
Create Date: 2026-11-04 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b5e2d7a9c1f4"
down_revision = "c3d8e1f4a6b2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("order_orders", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "granted_by_user_bid",
                sa.String(length=36),
                nullable=False,
                server_default="",
                comment="Open API caller that granted this order; empty otherwise",
            )
        )
        batch_op.create_index(
            batch_op.f("ix_order_orders_granted_by_user_bid"),
            ["granted_by_user_bid"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("order_orders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_order_orders_granted_by_user_bid"))
        batch_op.drop_column("granted_by_user_bid")
