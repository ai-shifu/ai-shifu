"""add tts audio records and shifu tts config

Revision ID: b5f2d3a9c1e4
Revises: c9c92880fc67
Create Date: 2026-01-08 10:30:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "b5f2d3a9c1e4"
down_revision = "c9c92880fc67"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learn_generated_audios",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column(
            "audio_bid",
            sa.String(length=36),
            nullable=False,
            comment="Audio business identifier",
        ),
        sa.Column(
            "generated_block_bid",
            sa.String(length=36),
            nullable=False,
            comment="Generated block business identifier",
        ),
        sa.Column(
            "progress_record_bid",
            sa.String(length=36),
            nullable=False,
            comment="Learn progress record business identifier",
        ),
        sa.Column(
            "user_bid",
            sa.String(length=36),
            nullable=False,
            comment="User business identifier",
        ),
        sa.Column(
            "shifu_bid",
            sa.String(length=36),
            nullable=False,
            comment="Shifu business identifier",
        ),
        sa.Column(
            "oss_url",
            sa.String(length=512),
            nullable=False,
            comment="Final audio OSS URL",
        ),
        sa.Column(
            "oss_bucket",
            sa.String(length=255),
            nullable=False,
            comment="OSS bucket name",
        ),
        sa.Column(
            "oss_object_key",
            sa.String(length=512),
            nullable=False,
            comment="OSS object key",
        ),
        sa.Column(
            "duration_ms",
            sa.Integer(),
            nullable=False,
            comment="Audio duration in milliseconds",
        ),
        sa.Column(
            "file_size",
            sa.Integer(),
            nullable=False,
            comment="Audio file size in bytes",
        ),
        sa.Column(
            "audio_format",
            sa.String(length=16),
            nullable=False,
            comment="Audio format (mp3, wav, etc.)",
        ),
        sa.Column(
            "sample_rate",
            sa.Integer(),
            nullable=False,
            comment="Audio sample rate",
        ),
        sa.Column(
            "voice_id",
            sa.String(length=64),
            nullable=False,
            comment="Voice ID used for synthesis",
        ),
        sa.Column(
            "voice_settings",
            sa.JSON(),
            nullable=True,
            comment="Full voice settings JSON (speed, pitch, emotion, etc.)",
        ),
        sa.Column(
            "model", sa.String(length=64), nullable=False, comment="TTS model name"
        ),
        sa.Column(
            "text_length",
            sa.Integer(),
            nullable=False,
            comment="Original text length in characters",
        ),
        sa.Column(
            "segment_count",
            sa.Integer(),
            nullable=False,
            comment="Number of segments synthesized",
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Status: 0=pending, 1=processing, 2=completed, 3=failed",
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="Error message if synthesis failed",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="TTS audio for generated content blocks",
    )

    with op.batch_alter_table("learn_generated_audios", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_learn_generated_audios_audio_bid"),
            ["audio_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_learn_generated_audios_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_learn_generated_audios_generated_block_bid"),
            ["generated_block_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_learn_generated_audios_progress_record_bid"),
            ["progress_record_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_learn_generated_audios_shifu_bid"),
            ["shifu_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_learn_generated_audios_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_learn_generated_audios_user_bid"),
            ["user_bid"],
            unique=False,
        )

    with op.batch_alter_table("shifu_draft_shifus", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "tts_enabled",
                sa.SmallInteger(),
                nullable=False,
                server_default=sa.text("0"),
                comment="TTS enabled: 0=disabled, 1=enabled",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_provider",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("''"),
                comment=(
                    "TTS provider: minimax, volcengine, baidu, aliyun "
                    "(empty=use system default)"
                ),
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_model",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("''"),
                comment="TTS model/resource id (provider-specific)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_voice_id",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("''"),
                comment="TTS voice ID",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_speed",
                sa.DECIMAL(precision=6, scale=2),
                nullable=False,
                server_default=sa.text("1.0"),
                comment="TTS speech speed (provider-specific range)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_pitch",
                sa.SmallInteger(),
                nullable=False,
                server_default=sa.text("0"),
                comment="TTS pitch adjustment (provider-specific range)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_emotion",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("''"),
                comment="TTS emotion setting",
            )
        )

    with op.batch_alter_table("shifu_published_shifus", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "tts_enabled",
                sa.SmallInteger(),
                nullable=False,
                server_default=sa.text("0"),
                comment="TTS enabled: 0=disabled, 1=enabled",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_provider",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("''"),
                comment=(
                    "TTS provider: minimax, volcengine, baidu, aliyun "
                    "(empty=use system default)"
                ),
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_model",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("''"),
                comment="TTS model/resource id (provider-specific)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_voice_id",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("''"),
                comment="TTS voice ID",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_speed",
                sa.DECIMAL(precision=6, scale=2),
                nullable=False,
                server_default=sa.text("1.0"),
                comment="TTS speech speed (provider-specific range)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_pitch",
                sa.SmallInteger(),
                nullable=False,
                server_default=sa.text("0"),
                comment="TTS pitch adjustment (provider-specific range)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "tts_emotion",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("''"),
                comment="TTS emotion setting",
            )
        )

    op.execute(
        "UPDATE shifu_draft_shifus SET tts_provider='' WHERE tts_provider='default'"
    )
    op.execute(
        "UPDATE shifu_published_shifus SET tts_provider='' WHERE tts_provider='default'"
    )


def downgrade():
    with op.batch_alter_table("shifu_published_shifus", schema=None) as batch_op:
        batch_op.drop_column("tts_emotion")
        batch_op.drop_column("tts_pitch")
        batch_op.drop_column("tts_speed")
        batch_op.drop_column("tts_voice_id")
        batch_op.drop_column("tts_model")
        batch_op.drop_column("tts_provider")
        batch_op.drop_column("tts_enabled")

    with op.batch_alter_table("shifu_draft_shifus", schema=None) as batch_op:
        batch_op.drop_column("tts_emotion")
        batch_op.drop_column("tts_pitch")
        batch_op.drop_column("tts_speed")
        batch_op.drop_column("tts_voice_id")
        batch_op.drop_column("tts_model")
        batch_op.drop_column("tts_provider")
        batch_op.drop_column("tts_enabled")

    with op.batch_alter_table("learn_generated_audios", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_learn_generated_audios_user_bid"))
        batch_op.drop_index(batch_op.f("ix_learn_generated_audios_status"))
        batch_op.drop_index(batch_op.f("ix_learn_generated_audios_shifu_bid"))
        batch_op.drop_index(batch_op.f("ix_learn_generated_audios_progress_record_bid"))
        batch_op.drop_index(batch_op.f("ix_learn_generated_audios_generated_block_bid"))
        batch_op.drop_index(batch_op.f("ix_learn_generated_audios_deleted"))
        batch_op.drop_index(batch_op.f("ix_learn_generated_audios_audio_bid"))

    op.drop_table("learn_generated_audios")
