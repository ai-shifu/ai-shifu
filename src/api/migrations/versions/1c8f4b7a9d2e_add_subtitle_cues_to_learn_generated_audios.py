"""add subtitle cues to learn_generated_audios

Revision ID: 1c8f4b7a9d2e
Revises: 7b3c5d9e1a2f
Create Date: 2026-03-31 15:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1c8f4b7a9d2e"
down_revision = "7b3c5d9e1a2f"
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
    except sa.exc.NoSuchTableError:
        return False
    return any(column["name"] == column_name for column in columns)


def upgrade():
    table_name = "learn_generated_audios"
    if not _table_exists(table_name):
        return
    if _column_exists(table_name, "subtitle_cues"):
        return

    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "subtitle_cues",
                sa.JSON(),
                nullable=True,
                comment="Subtitle cues aligned with synthesized TTS segments",
            )
        )


def downgrade():
    table_name = "learn_generated_audios"
    if not _table_exists(table_name):
        return
    if not _column_exists(table_name, "subtitle_cues"):
        return

    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.drop_column("subtitle_cues")
