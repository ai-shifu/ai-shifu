"""add minimax clone first synthesized at

Revision ID: b7c3e1f9a2d4
Revises: d4e5f6a7b8c9
Create Date: 2026-06-27 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b7c3e1f9a2d4"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        columns = inspector.get_columns(table_name)
    except (sa.exc.NoSuchTableError, sa.exc.DatabaseError):
        return False
    return any(column.get("name") == column_name for column in columns)


def upgrade():
    if _column_exists("tts_minimax_cloned_voices", "first_synthesized_at"):
        return

    with op.batch_alter_table("tts_minimax_cloned_voices", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "first_synthesized_at",
                sa.DateTime(),
                nullable=True,
                comment="Timestamp of the first real t2a synthesis that "
                "activated and charged the cloned voice",
            )
        )


def downgrade():
    if not _column_exists("tts_minimax_cloned_voices", "first_synthesized_at"):
        return

    with op.batch_alter_table("tts_minimax_cloned_voices", schema=None) as batch_op:
        batch_op.drop_column("first_synthesized_at")
