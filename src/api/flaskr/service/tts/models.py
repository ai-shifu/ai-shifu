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
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func

from flaskr.dao import db


# Audio status constants
AUDIO_STATUS_PENDING = 0
AUDIO_STATUS_PROCESSING = 1
AUDIO_STATUS_COMPLETED = 2
AUDIO_STATUS_FAILED = 3


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
        default=func.now(),
        server_default=func.now(),
        comment="Creation timestamp",
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update timestamp",
    )

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
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
