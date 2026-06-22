"""drop minimax cloned voice_id unique constraint

Revision ID: 8c2d4e6f1a9b
Revises: 2f8c9a1d7e6b
Create Date: 2026-06-22 16:30:00.000000

"""

from alembic import op


revision = "8c2d4e6f1a9b"
down_revision = "2f8c9a1d7e6b"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "uq_tts_minimax_cloned_voices_voice_id",
        "tts_minimax_cloned_voices",
        type_="unique",
    )


def downgrade():
    op.create_unique_constraint(
        "uq_tts_minimax_cloned_voices_voice_id",
        "tts_minimax_cloned_voices",
        ["voice_id"],
    )
