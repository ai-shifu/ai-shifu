"""add tts model field to shifu tables

Revision ID: f45bc12a8e91
Revises: e34eeaec3402
Create Date: 2026-01-05 14:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f45bc12a8e91"
down_revision = "e34eeaec3402"
branch_labels = None
depends_on = None


def upgrade():
    # Add tts_model field to shifu_draft_shifus
    with op.batch_alter_table("shifu_draft_shifus", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "tts_model",
                sa.String(length=64),
                nullable=False,
                server_default="",
                comment="TTS model/resource ID (empty=use provider default)",
            )
        )

    # Add tts_model field to shifu_published_shifus
    with op.batch_alter_table("shifu_published_shifus", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "tts_model",
                sa.String(length=64),
                nullable=False,
                server_default="",
                comment="TTS model/resource ID (empty=use provider default)",
            )
        )


def downgrade():
    # Remove tts_model field from shifu_published_shifus
    with op.batch_alter_table("shifu_published_shifus", schema=None) as batch_op:
        batch_op.drop_column("tts_model")

    # Remove tts_model field from shifu_draft_shifus
    with op.batch_alter_table("shifu_draft_shifus", schema=None) as batch_op:
        batch_op.drop_column("tts_model")
