"""drop obsolete shifu archive columns

Revision ID: ba723998409b
Revises: c68e52b7eb5b
Create Date: 2026-01-18 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ba723998409b"
down_revision = "c68e52b7eb5b"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade():
    for table_name in ("shifu_draft_shifus", "shifu_published_shifus"):
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            if _column_exists(table_name, "archived_at"):
                batch_op.drop_column("archived_at")
            if _column_exists(table_name, "archived"):
                batch_op.drop_column("archived")


def downgrade():
    archived_column = sa.Column(
        "archived",
        sa.SmallInteger(),
        nullable=False,
        server_default=sa.text("0"),
        comment="Archive flag: 0=active, 1=archived",
    )
    archived_at_column = sa.Column(
        "archived_at",
        sa.DateTime(),
        nullable=True,
        comment="Archived timestamp",
    )

    for table_name in ("shifu_draft_shifus", "shifu_published_shifus"):
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            if not _column_exists(table_name, "archived"):
                batch_op.add_column(archived_column.copy())
            if not _column_exists(table_name, "archived_at"):
                batch_op.add_column(archived_at_column.copy())
