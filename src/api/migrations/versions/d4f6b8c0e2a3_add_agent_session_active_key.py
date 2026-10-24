"""add learn agent sessions active key.

Revision ID: d4f6b8c0e2a3
Revises: c3e5a7b9d1f2
Create Date: 2026-09-17 16:45:00.000000

Separate from the create-table revision because that one has already been applied where the table
was made ahead of this change; alembic records revisions, not table shapes, so a column added to it
would never reach those databases.

Additive: one nullable column and one unique index over it. MySQL treats NULLs as distinct, so the
index constrains only live sessions and discarded rows accumulate freely.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4f6b8c0e2a3"
down_revision = "c3e5a7b9d1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "learn_agent_sessions",
        sa.Column(
            "active_key",
            sa.String(length=80),
            nullable=True,
            comment=(
                "user_bid:outline_item_bid while this row is the live session, NULL once "
                "discarded; unique, so two concurrent starts cannot both create one"
            ),
        ),
    )
    op.create_index(
        "uq_learn_agent_sessions_active",
        "learn_agent_sessions",
        ["active_key"],
        unique=True,
    )


def downgrade():
    op.drop_index("uq_learn_agent_sessions_active", table_name="learn_agent_sessions")
    op.drop_column("learn_agent_sessions", "active_key")
