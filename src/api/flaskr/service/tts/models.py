"""
TTS Database Models.

This module defines the database models for storing TTS audio records.
"""

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    SmallInteger,
    JSON,
    Numeric,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from flaskr.util.datetime import now_utc, to_utc_iso

from flaskr.dao import db


# Audio status constants
AUDIO_STATUS_PENDING = 0
AUDIO_STATUS_PROCESSING = 1
AUDIO_STATUS_COMPLETED = 2
AUDIO_STATUS_FAILED = 3

TTS_MINIMAX_CLONE_STATUS_QUEUED = "queued"
TTS_MINIMAX_CLONE_STATUS_PROCESSING = "processing"
TTS_MINIMAX_CLONE_STATUS_BILLING_PENDING = "billing_pending"
TTS_MINIMAX_CLONE_STATUS_FAILED = "failed"
TTS_MINIMAX_CLONE_STATUS_READY = "ready"

TTS_MINIMAX_CLONE_BILLING_NOT_REQUIRED = "not_required"
TTS_MINIMAX_CLONE_BILLING_RESERVED = "reserved"
TTS_MINIMAX_CLONE_BILLING_CHARGED = "charged"
TTS_MINIMAX_CLONE_BILLING_RELEASED = "released"
TTS_MINIMAX_CLONE_BILLING_FAILED = "failed"

TTS_CREDIT_NUMERIC = Numeric(20, 10)


class LearnGeneratedAudio(db.Model):
    """
    TTS audio record for generated content blocks.

    This model stores the synthesized audio for AI-generated content,
    including both streaming segments and final concatenated audio.
    """

    __tablename__ = "learn_generated_audios"
    __table_args__ = {"comment": "TTS audio for generated content blocks"}

    id = Column(BIGINT, primary_key=True, autoincrement=True)

    audio_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Audio business identifier",
    )

    generated_block_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Generated block business identifier",
    )

    position = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Audio segment position within a generated block (0-based)",
    )

    progress_record_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Learn progress record business identifier",
    )

    user_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="User business identifier",
    )

    shifu_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Shifu business identifier",
    )

    # Audio storage
    oss_url = Column(
        String(512),
        nullable=False,
        default="",
        comment="Final audio OSS URL",
    )

    oss_bucket = Column(
        String(255),
        nullable=False,
        default="",
        comment="OSS bucket name",
    )

    oss_object_key = Column(
        String(512),
        nullable=False,
        default="",
        comment="OSS object key",
    )

    # Audio metadata
    duration_ms = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Audio duration in milliseconds",
    )

    file_size = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Audio file size in bytes",
    )

    audio_format = Column(
        String(16),
        nullable=False,
        default="mp3",
        comment="Audio format (mp3, wav, etc.)",
    )

    sample_rate = Column(
        Integer,
        nullable=False,
        default=24000,
        comment="Audio sample rate",
    )

    # TTS settings used
    voice_id = Column(
        String(64),
        nullable=False,
        default="",
        comment="Voice ID used for synthesis",
    )

    voice_settings = Column(
        JSON,
        nullable=True,
        comment="Full voice settings JSON (speed, pitch, emotion, etc.)",
    )

    model = Column(
        String(64),
        nullable=False,
        default="",
        comment="TTS model name",
    )

    # Content info
    text_length = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Original text length in characters",
    )

    segment_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of segments synthesized",
    )

    subtitle_cues = Column(
        JSON,
        nullable=True,
        comment="Subtitle cues aligned with synthesized TTS segments",
    )

    # Status
    status = Column(
        SmallInteger,
        nullable=False,
        default=AUDIO_STATUS_PENDING,
        index=True,
        comment="Status: 0=pending, 1=processing, 2=completed, 3=failed",
    )

    error_message = Column(
        Text,
        nullable=True,
        comment="Error message if synthesis failed",
    )

    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        index=True,
        comment="Deletion flag: 0=active, 1=deleted",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=now_utc,
        server_default=func.now(),
        comment="Creation timestamp",
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=now_utc,
        server_default=func.now(),
        onupdate=now_utc,
        comment="Last update timestamp",
    )


class TTSMiniMaxClonedVoice(db.Model):
    """MiniMax cloned voice asset owned by a creator/Shifu."""

    __tablename__ = "tts_minimax_cloned_voices"
    __table_args__ = (
        UniqueConstraint(
            "voice_bid",
            name="uq_tts_minimax_cloned_voices_voice_bid",
        ),
        Index(
            "ix_tts_minimax_cloned_voices_owner_status",
            "owner_user_bid",
            "status",
        ),
        Index(
            "ix_tts_minimax_cloned_voices_shifu_status",
            "shifu_bid",
            "status",
        ),
        {"comment": "MiniMax cloned TTS voices"},
    )

    id = Column(BIGINT, primary_key=True, autoincrement=True)

    voice_bid = Column(String(36), nullable=False, default="", index=True)
    owner_user_bid = Column(String(36), nullable=False, default="", index=True)
    shifu_bid = Column(String(36), nullable=False, default="", index=True)
    display_name = Column(String(128), nullable=False, default="")
    voice_id = Column(String(64), nullable=False, default="", index=True)

    status = Column(
        String(32),
        nullable=False,
        default=TTS_MINIMAX_CLONE_STATUS_QUEUED,
        index=True,
    )
    status_msg = Column(Text, nullable=False, default="")
    failure_reason = Column(String(64), nullable=False, default="")
    retry_count = Column(Integer, nullable=False, default=0)

    source_capture_method = Column(String(32), nullable=False, default="")
    source_audio_resource_bid = Column(String(36), nullable=False, default="")
    source_audio_url = Column(String(512), nullable=False, default="")
    source_audio_filename = Column(String(255), nullable=False, default="")
    source_audio_content_type = Column(String(128), nullable=False, default="")
    source_audio_duration_ms = Column(Integer, nullable=False, default=0)

    normalized_audio_resource_bid = Column(String(36), nullable=False, default="")
    normalized_audio_url = Column(String(512), nullable=False, default="")
    normalized_audio_object_key = Column(String(512), nullable=False, default="")
    normalized_audio_duration_ms = Column(Integer, nullable=False, default=0)

    prompt_audio_resource_bid = Column(String(36), nullable=False, default="")
    prompt_audio_url = Column(String(512), nullable=False, default="")
    prompt_audio_filename = Column(String(255), nullable=False, default="")
    prompt_audio_content_type = Column(String(128), nullable=False, default="")
    prompt_audio_duration_ms = Column(Integer, nullable=False, default=0)

    minimax_source_file_id = Column(String(128), nullable=False, default="")
    minimax_prompt_file_id = Column(String(128), nullable=False, default="")
    minimax_demo_audio_url = Column(String(512), nullable=False, default="")
    minimax_trace_id = Column(String(128), nullable=False, default="")
    minimax_status_code = Column(Integer, nullable=False, default=0)
    minimax_status_msg = Column(String(255), nullable=False, default="")
    minimax_extra = Column(JSON, nullable=True)

    billing_status = Column(
        String(32),
        nullable=False,
        default=TTS_MINIMAX_CLONE_BILLING_NOT_REQUIRED,
        index=True,
    )
    estimated_credits = Column(TTS_CREDIT_NUMERIC, nullable=False, default=0)
    charged_credits = Column(TTS_CREDIT_NUMERIC, nullable=False, default=0)
    billing_reservation_bid = Column(String(36), nullable=False, default="")
    billing_ledger_bid = Column(String(36), nullable=False, default="")
    clone_usage_bid = Column(String(36), nullable=False, default="")

    deleted = Column(SmallInteger, nullable=False, default=0, index=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )
    ready_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "audio_bid": self.audio_bid,
            "generated_block_bid": self.generated_block_bid,
            "oss_url": self.oss_url,
            "duration_ms": self.duration_ms,
            "file_size": self.file_size,
            "audio_format": self.audio_format,
            "voice_id": self.voice_id,
            "subtitle_cues": self.subtitle_cues or [],
            "status": self.status,
            "created_at": to_utc_iso(self.created_at),
        }
