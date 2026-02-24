"""add position to learn_generated_audios

Revision ID: 3ef04a9b5d37
Revises: 6b956399315e
Create Date: 2026-02-09 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3ef04a9b5d37"
down_revision = "6b956399315e"
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
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                comment="Audio segment position within a generated block (0-based)",
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
