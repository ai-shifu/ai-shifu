"""add billing order expires_at

Revision ID: c5d8e1f2a3b4
Revises: b8c1d2e3f4a5
Create Date: 2026-06-09 15:40:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c5d8e1f2a3b4"
down_revision = "b8c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("bill_orders") as batch_op:
        batch_op.add_column(
            sa.Column(
                "expires_at",
                sa.DateTime(),
                nullable=True,
                comment="Checkout expiration timestamp",
            )
        )
        batch_op.create_index(batch_op.f("ix_bill_orders_expires_at"), ["expires_at"])


def downgrade():
    with op.batch_alter_table("bill_orders") as batch_op:
        batch_op.drop_index(batch_op.f("ix_bill_orders_expires_at"))
        batch_op.drop_column("expires_at")
