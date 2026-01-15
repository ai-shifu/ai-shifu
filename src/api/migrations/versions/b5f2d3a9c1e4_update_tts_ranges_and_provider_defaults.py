"""update tts ranges and normalize provider defaults

Revision ID: b5f2d3a9c1e4
Revises: f45bc12a8e91
Create Date: 2026-01-08 10:30:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b5f2d3a9c1e4"
down_revision = "f45bc12a8e91"
branch_labels = None
depends_on = None


def upgrade():
    # Normalize legacy default provider values
    op.execute(
        "UPDATE shifu_draft_shifus SET tts_provider='' WHERE tts_provider='default'"
    )
    op.execute(
        "UPDATE shifu_published_shifus SET tts_provider='' WHERE tts_provider='default'"
    )

    # Update shifu_draft_shifus
    with op.batch_alter_table("shifu_draft_shifus", schema=None) as batch_op:
        batch_op.alter_column(
            "tts_provider",
            existing_type=sa.String(length=32),
            existing_nullable=False,
            comment=(
                "TTS provider: minimax, volcengine, baidu, aliyun "
                "(empty=use system default)"
            ),
        )
        batch_op.alter_column(
            "tts_speed",
            existing_type=sa.DECIMAL(precision=3, scale=2),
            type_=sa.DECIMAL(precision=6, scale=2),
            existing_nullable=False,
            comment="TTS speech speed (provider-specific range)",
        )
        batch_op.alter_column(
            "tts_pitch",
            existing_type=sa.SmallInteger(),
            existing_nullable=False,
            comment="TTS pitch adjustment (provider-specific range)",
        )

    # Update shifu_published_shifus
    with op.batch_alter_table("shifu_published_shifus", schema=None) as batch_op:
        batch_op.alter_column(
            "tts_provider",
            existing_type=sa.String(length=32),
            existing_nullable=False,
            comment=(
                "TTS provider: minimax, volcengine, baidu, aliyun "
                "(empty=use system default)"
            ),
        )
        batch_op.alter_column(
            "tts_speed",
            existing_type=sa.DECIMAL(precision=3, scale=2),
            type_=sa.DECIMAL(precision=6, scale=2),
            existing_nullable=False,
            comment="TTS speech speed (provider-specific range)",
        )
        batch_op.alter_column(
            "tts_pitch",
            existing_type=sa.SmallInteger(),
            existing_nullable=False,
            comment="TTS pitch adjustment (provider-specific range)",
        )


def downgrade():
    # Revert shifu_published_shifus
    with op.batch_alter_table("shifu_published_shifus", schema=None) as batch_op:
        batch_op.alter_column(
            "tts_provider",
            existing_type=sa.String(length=32),
            existing_nullable=False,
            comment="TTS provider: minimax, volcengine (empty=use system default)",
        )
        batch_op.alter_column(
            "tts_speed",
            existing_type=sa.DECIMAL(precision=6, scale=2),
            type_=sa.DECIMAL(precision=3, scale=2),
            existing_nullable=False,
            comment="TTS speech speed (0.5-2.0)",
        )
        batch_op.alter_column(
            "tts_pitch",
            existing_type=sa.SmallInteger(),
            existing_nullable=False,
            comment="TTS pitch adjustment (-12 to 12)",
        )

    # Revert shifu_draft_shifus
    with op.batch_alter_table("shifu_draft_shifus", schema=None) as batch_op:
        batch_op.alter_column(
            "tts_provider",
            existing_type=sa.String(length=32),
            existing_nullable=False,
            comment="TTS provider: minimax, volcengine (empty=use system default)",
        )
        batch_op.alter_column(
            "tts_speed",
            existing_type=sa.DECIMAL(precision=6, scale=2),
            type_=sa.DECIMAL(precision=3, scale=2),
            existing_nullable=False,
            comment="TTS speech speed (0.5-2.0)",
        )
        batch_op.alter_column(
            "tts_pitch",
            existing_type=sa.SmallInteger(),
            existing_nullable=False,
            comment="TTS pitch adjustment (-12 to 12)",
        )
