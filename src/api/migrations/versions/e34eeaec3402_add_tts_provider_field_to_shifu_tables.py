"""add tts provider field to shifu tables

Revision ID: e34eeaec3402
Revises: c61409972e4a
Create Date: 2026-01-05 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e34eeaec3402"
down_revision = "c61409972e4a"
branch_labels = None
depends_on = None


def upgrade():
    # Add tts_provider field to shifu_draft_shifus
    with op.batch_alter_table("shifu_draft_shifus", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "tts_provider",
                sa.String(length=32),
                nullable=False,
                server_default="",
                comment="TTS provider: minimax, volcengine (empty=use system default)",
            )
        )

    # Add tts_provider field to shifu_published_shifus
    with op.batch_alter_table("shifu_published_shifus", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "tts_provider",
                sa.String(length=32),
                nullable=False,
                server_default="",
                comment="TTS provider: minimax, volcengine (empty=use system default)",
            )
        )


def downgrade():
    # Remove tts_provider field from shifu_published_shifus
    with op.batch_alter_table("shifu_published_shifus", schema=None) as batch_op:
        batch_op.drop_column("tts_provider")

    # Remove tts_provider field from shifu_draft_shifus
    with op.batch_alter_table("shifu_draft_shifus", schema=None) as batch_op:
        batch_op.drop_column("tts_provider")
