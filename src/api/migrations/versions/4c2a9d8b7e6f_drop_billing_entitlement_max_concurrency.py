"""drop billing entitlement max_concurrency

Revision ID: 4c2a9d8b7e6f
Revises: 9a6b3c2d1e4f
Create Date: 2026-04-17 10:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "4c2a9d8b7e6f"
down_revision = "9a6b3c2d1e4f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("billing_entitlements", schema=None) as batch_op:
        batch_op.drop_column("max_concurrency")


def downgrade():
    with op.batch_alter_table("billing_entitlements", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "max_concurrency",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
                comment="Max concurrency",
            )
        )
        batch_op.alter_column("max_concurrency", server_default=None)
