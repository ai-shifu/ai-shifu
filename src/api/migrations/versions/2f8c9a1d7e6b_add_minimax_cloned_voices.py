"""add minimax cloned voices

Revision ID: 2f8c9a1d7e6b
Revises: 5a6b7c8d9e10
Create Date: 2026-06-18 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "2f8c9a1d7e6b"
down_revision = "5a6b7c8d9e10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tts_minimax_cloned_voices",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("voice_bid", sa.String(length=36), nullable=False),
        sa.Column("owner_user_bid", sa.String(length=36), nullable=False),
        sa.Column("shifu_bid", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("voice_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("status_msg", sa.Text(), nullable=False),
        sa.Column("failure_reason", sa.String(length=64), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("source_capture_method", sa.String(length=32), nullable=False),
        sa.Column("source_audio_resource_bid", sa.String(length=36), nullable=False),
        sa.Column("source_audio_url", sa.String(length=512), nullable=False),
        sa.Column("source_audio_filename", sa.String(length=255), nullable=False),
        sa.Column("source_audio_content_type", sa.String(length=128), nullable=False),
        sa.Column("source_audio_duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "normalized_audio_resource_bid", sa.String(length=36), nullable=False
        ),
        sa.Column("normalized_audio_url", sa.String(length=512), nullable=False),
        sa.Column("normalized_audio_object_key", sa.String(length=512), nullable=False),
        sa.Column("normalized_audio_duration_ms", sa.Integer(), nullable=False),
        sa.Column("prompt_audio_resource_bid", sa.String(length=36), nullable=False),
        sa.Column("prompt_audio_url", sa.String(length=512), nullable=False),
        sa.Column("prompt_audio_filename", sa.String(length=255), nullable=False),
        sa.Column("prompt_audio_content_type", sa.String(length=128), nullable=False),
        sa.Column("prompt_audio_duration_ms", sa.Integer(), nullable=False),
        sa.Column("minimax_source_file_id", sa.String(length=128), nullable=False),
        sa.Column("minimax_prompt_file_id", sa.String(length=128), nullable=False),
        sa.Column("minimax_demo_audio_url", sa.String(length=512), nullable=False),
        sa.Column("minimax_trace_id", sa.String(length=128), nullable=False),
        sa.Column("minimax_status_code", sa.Integer(), nullable=False),
        sa.Column("minimax_status_msg", sa.String(length=255), nullable=False),
        sa.Column("minimax_extra", sa.JSON(), nullable=True),
        sa.Column("billing_status", sa.String(length=32), nullable=False),
        sa.Column(
            "estimated_credits",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
        ),
        sa.Column(
            "charged_credits",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
        ),
        sa.Column("billing_reservation_bid", sa.String(length=36), nullable=False),
        sa.Column("billing_ledger_bid", sa.String(length=36), nullable=False),
        sa.Column("clone_usage_bid", sa.String(length=36), nullable=False),
        sa.Column("deleted", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("ready_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("voice_bid", name="uq_tts_minimax_cloned_voices_voice_bid"),
        sa.UniqueConstraint("voice_id", name="uq_tts_minimax_cloned_voices_voice_id"),
    )
    op.create_index(
        "ix_tts_minimax_cloned_voices_owner_status",
        "tts_minimax_cloned_voices",
        ["owner_user_bid", "status"],
        unique=False,
    )
    op.create_index(
        "ix_tts_minimax_cloned_voices_shifu_status",
        "tts_minimax_cloned_voices",
        ["shifu_bid", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tts_minimax_cloned_voices_voice_bid"),
        "tts_minimax_cloned_voices",
        ["voice_bid"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tts_minimax_cloned_voices_voice_id"),
        "tts_minimax_cloned_voices",
        ["voice_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_tts_minimax_cloned_voices_voice_id"),
        table_name="tts_minimax_cloned_voices",
    )
    op.drop_index(
        op.f("ix_tts_minimax_cloned_voices_voice_bid"),
        table_name="tts_minimax_cloned_voices",
    )
    op.drop_index(
        "ix_tts_minimax_cloned_voices_shifu_status",
        table_name="tts_minimax_cloned_voices",
    )
    op.drop_index(
        "ix_tts_minimax_cloned_voices_owner_status",
        table_name="tts_minimax_cloned_voices",
    )
    op.drop_table("tts_minimax_cloned_voices")
