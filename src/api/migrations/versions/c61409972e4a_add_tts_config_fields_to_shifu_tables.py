"""add tts config fields to shifu tables

Revision ID: c61409972e4a
Revises: e2da58b20960
Create Date: 2026-01-04 09:48:27.116738

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c61409972e4a"
down_revision = "e2da58b20960"
branch_labels = None
depends_on = None


def upgrade():
    # Add TTS configuration fields to shifu_draft_shifus
    with op.batch_alter_table("shifu_draft_shifus", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "tts_enabled",
                sa.SmallInteger(),
                nullable=False,
                comment="TTS enabled: 0=disabled, 1=enabled",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_voice_id",
                sa.String(length=64),
                nullable=False,
                comment="TTS voice ID",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_speed",
                sa.DECIMAL(precision=3, scale=2),
                nullable=False,
                comment="TTS speech speed (0.5-2.0)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_pitch",
                sa.SmallInteger(),
                nullable=False,
                comment="TTS pitch adjustment (-12 to 12)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_emotion",
                sa.String(length=32),
                nullable=False,
                comment="TTS emotion setting",
            )
        )

    # Add TTS configuration fields to shifu_published_shifus
    with op.batch_alter_table("shifu_published_shifus", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "tts_enabled",
                sa.SmallInteger(),
                nullable=False,
                comment="TTS enabled: 0=disabled, 1=enabled",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_voice_id",
                sa.String(length=64),
                nullable=False,
                comment="TTS voice ID",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_speed",
                sa.DECIMAL(precision=3, scale=2),
                nullable=False,
                comment="TTS speech speed (0.5-2.0)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_pitch",
                sa.SmallInteger(),
                nullable=False,
                comment="TTS pitch adjustment (-12 to 12)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_emotion",
                sa.String(length=32),
                nullable=False,
                comment="TTS emotion setting",
            )
        )


def downgrade():
    # Remove TTS configuration fields from shifu_published_shifus
    with op.batch_alter_table("shifu_published_shifus", schema=None) as batch_op:
        batch_op.drop_column("tts_emotion")
        batch_op.drop_column("tts_pitch")
        batch_op.drop_column("tts_speed")
        batch_op.drop_column("tts_voice_id")
        batch_op.drop_column("tts_enabled")

    # Remove TTS configuration fields from shifu_draft_shifus
    with op.batch_alter_table("shifu_draft_shifus", schema=None) as batch_op:
        batch_op.drop_column("tts_emotion")
        batch_op.drop_column("tts_pitch")
        batch_op.drop_column("tts_speed")
        batch_op.drop_column("tts_voice_id")
        batch_op.drop_column("tts_enabled")
