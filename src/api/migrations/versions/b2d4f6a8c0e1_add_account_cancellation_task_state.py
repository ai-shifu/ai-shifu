"""add account cancellation task state.

Revision ID: b2d4f6a8c0e1
Revises: b1c2d3e4f5a6
Create Date: 2026-09-09 09:15:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2d4f6a8c0e1"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_account_cancellations",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Background execution attempt count",
        ),
    )
    op.add_column(
        "user_account_cancellations",
        sa.Column(
            "failure_code",
            sa.String(length=64),
            nullable=False,
            server_default="",
            comment="Bounded background execution failure code",
        ),
    )
    op.add_column(
        "user_account_cancellations",
        sa.Column(
            "last_attempt_at",
            sa.DateTime(),
            nullable=True,
            comment="Latest background execution attempt timestamp",
        ),
    )


def downgrade():
    op.drop_column("user_account_cancellations", "last_attempt_at")
    op.drop_column("user_account_cancellations", "failure_code")
    op.drop_column("user_account_cancellations", "attempt_count")
