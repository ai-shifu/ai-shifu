"""Add course answer aliases.

Revision ID: 772f773d65fe
Revises: b5e2d7a9c1f4
Create Date: 2026-11-08 16:33:09.274242

"""

import sqlalchemy as sa
from alembic import op

revision = "772f773d65fe"
down_revision = "b5e2d7a9c1f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the scoped alias table without changing existing memory rows."""
    op.create_table(
        "var_course_answer_aliases",
        sa.Column("user_bid", sa.String(length=32), nullable=False),
        sa.Column("shifu_bid", sa.String(length=32), nullable=False),
        sa.Column("alias_digest", sa.String(length=64), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("question_key", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("user_bid", "shifu_bid", "alias_digest"),
        comment="Course-scoped links from legacy answer bindings to question keys.",
    )


def downgrade() -> None:
    """Drop alias metadata while retaining the stored question answers."""
    op.drop_table("var_course_answer_aliases")
