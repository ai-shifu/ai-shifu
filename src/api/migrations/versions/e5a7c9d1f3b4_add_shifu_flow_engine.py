"""add shifu flow engine setting.

Revision ID: e5a7c9d1f3b4
Revises: d4f6b8c0e2a3
Create Date: 2026-09-17 17:30:00.000000

Additive: one column on each of the two shifu tables, defaulting to the 1.0 runtime, so every
existing course keeps the behaviour it has today.

The ALTER names ALGORITHM=INPLACE, LOCK=NONE rather than letting the server choose. Left to itself
it would very likely pick something cheap, but "very likely" is not a guarantee: a silent fall back
to COPY would rebuild tables of 26k and 13k rows while learners are on them. Naming both turns that
into a failed migration instead, which is the outcome worth having.

LOCK=NONE is the part that matters -- it requires the table to stay readable and writable for the
whole operation. ALGORITHM=INSTANT would be the stronger claim, but the MySQL build used here
(8.0.36, "Source distribution") rejects that syntax outright: it has no
`innodb_instant_alter_column_allowed` variable and returns error 1845 even for a plain add-with-
default on an empty table. Both dev01 and production run that same build.
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
            f"ALGORITHM=INPLACE, LOCK=NONE"
        )


def downgrade():
    for table in _TABLES:
        op.drop_column(table, "flow_engine")
