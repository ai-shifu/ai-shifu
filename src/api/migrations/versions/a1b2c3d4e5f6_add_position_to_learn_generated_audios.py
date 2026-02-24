"""add position to learn_generated_audios

Revision ID: a1b2c3d4e5f6
Revises: 8f4c1a2b7d9e
Create Date: 2026-02-24 15:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "8f4c1a2b7d9e"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        columns = inspector.get_columns(table_name)
    except Exception:
        return False
    return any(column["name"] == column_name for column in columns)


def upgrade():
    table_name = "learn_generated_audios"
    if not _table_exists(table_name):
        return
    if _column_exists(table_name, "position"):
        return
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "position",
                sa.SmallInteger(),
                nullable=False,
                server_default=sa.text("0"),
                comment="Audio position index within the block (0-based)",
            )
        )


def downgrade():
    table_name = "learn_generated_audios"
    if not _table_exists(table_name):
        return
    if not _column_exists(table_name, "position"):
        return
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.drop_column("position")
