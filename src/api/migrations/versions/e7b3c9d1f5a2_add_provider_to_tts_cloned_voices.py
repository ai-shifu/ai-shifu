"""add provider to tts cloned voices

Revision ID: e7b3c9d1f5a2
Revises: b8d5f0a2c3e4
Create Date: 2026-08-10 16:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e7b3c9d1f5a2"
down_revision = "b8d5f0a2c3e4"
branch_labels = None
depends_on = None

TABLE_NAME = "tts_minimax_cloned_voices"
COLUMN_NAME = "provider"
INDEX_NAME = "ix_tts_minimax_cloned_voices_provider"


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        columns = inspector.get_columns(table_name)
    except (sa.exc.NoSuchTableError, sa.exc.DatabaseError):
        return False
    return any(column.get("name") == column_name for column in columns)


def upgrade():
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        return

    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                COLUMN_NAME,
                sa.String(length=32),
                nullable=False,
                server_default="minimax",
                comment="TTS provider owning this cloned voice",
            )
        )
        batch_op.create_index(INDEX_NAME, [COLUMN_NAME])


def downgrade():
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        return

    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.drop_index(INDEX_NAME)
        batch_op.drop_column(COLUMN_NAME)
