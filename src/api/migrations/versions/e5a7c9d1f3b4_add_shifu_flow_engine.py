"""add shifu flow engine setting.

Revision ID: e5a7c9d1f3b4
Revises: d4f6b8c0e2a3
Create Date: 2026-09-17 17:30:00.000000

Additive: one column on each of the two shifu tables, defaulting to the 1.0 runtime, so every
existing course keeps the behaviour it has today.

The ALTER names ALGORITHM=INSTANT rather than relying on MySQL to choose it. Adding a column with a
default is instant on 8.0, but "usually instant" is not a guarantee: if the conditions ever fail --
a table that has exhausted its instant-add budget, say -- the server would silently fall back to
COPY and rebuild a table with tens of thousands of rows while learners are using it. Naming the
algorithm turns that into a failed migration instead, which is the outcome worth having.
"""

from __future__ import annotations

from alembic import op

revision = "e5a7c9d1f3b4"
down_revision = "d4f6b8c0e2a3"
branch_labels = None
depends_on = None

_TABLES = ("shifu_draft_shifus", "shifu_published_shifus")
_COMMENT = "MarkdownFlow runtime that teaches this shifu: 1=1.0, 2=2.0"


def upgrade():
    for table in _TABLES:
        op.execute(
            f"ALTER TABLE `{table}` "
            f"ADD COLUMN `flow_engine` SMALLINT NOT NULL DEFAULT 1 "
            f"COMMENT '{_COMMENT}', "
            f"ALGORITHM=INSTANT"
        )


def downgrade():
    for table in _TABLES:
        op.drop_column(table, "flow_engine")
