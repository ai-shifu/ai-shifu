"""drop the retired shifu flow engine setting.

Revision ID: d96fca5d4222
Revises: b5e2d7a9c1f4
Create Date: 2026-11-11 12:00:00.000000

Every course runs MarkdownFlow 2.0 since 1.0 was removed, and #3299 stopped reading and writing
`flow_engine`, so the column on both shifu tables is dead weight. Apply only after every
deployment sharing the database (including sim) runs code from #3299 or later. Older code still
maps the column.

MySQL drops it in one online rebuild per table (about 26k and 13k rows). ALGORITHM=INPLACE,
LOCK=NONE makes a fallback that would block writers fail the migration instead.

MySQL DDL is not transactional: if the first table's ALTER commits and the second fails (a
metadata-lock timeout, a dropped connection), the revision stays unstamped and a rerun would
fail on the column already gone. Each step therefore checks only whether `flow_engine` is still
on that table (or, on downgrade, already back), so a rerun finishes the remaining table. Offline
`--sql` export has no database to inspect and emits every statement.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "d96fca5d4222"
down_revision = "b5e2d7a9c1f4"
branch_labels = None
depends_on = None

_TABLES = ("shifu_draft_shifus", "shifu_published_shifus")
_COMMENT = "MarkdownFlow runtime that teaches this shifu: 1=1.0, 2=2.0"


def _is_mysql() -> bool:
    return context.get_context().dialect.name == "mysql"


def _has_flow_engine(table: str) -> bool:
    columns = sa.inspect(op.get_bind()).get_columns(table)
    return any(column["name"] == "flow_engine" for column in columns)


def upgrade() -> None:
    """Drop the flow engine column from draft and published shifus."""
    for table in _TABLES:
        if not context.is_offline_mode() and not _has_flow_engine(table):
            continue
        if _is_mysql():
            op.execute(
                f"ALTER TABLE `{table}` DROP COLUMN `flow_engine`, "
                f"ALGORITHM=INPLACE, LOCK=NONE"
            )
        else:
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_column("flow_engine")


def downgrade() -> None:
    """Restore the column with its original definition."""
    for table in reversed(_TABLES):
        if not context.is_offline_mode() and _has_flow_engine(table):
            continue
        if _is_mysql():
            op.execute(
                f"ALTER TABLE `{table}` "
                f"ADD COLUMN `flow_engine` SMALLINT NOT NULL DEFAULT 1 "
                f"COMMENT '{_COMMENT}', "
                f"ALGORITHM=INPLACE, LOCK=NONE"
            )
        else:
            with op.batch_alter_table(table) as batch_op:
                batch_op.add_column(
                    sa.Column(
                        "flow_engine",
                        sa.SmallInteger(),
                        nullable=False,
                        server_default="1",
                        comment=_COMMENT,
                    )
                )
