"""
Billing usage metering models.

This module stores per-invocation usage data for LLM and TTS calls.
"""

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    SmallInteger,
    JSON,
    Index,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func

from flaskr.dao import db


class BillUsageRecord(db.Model):
    """
    Usage metering record for LLM/TTS billing.
    """

    __tablename__ = "bill_usage"
    __table_args__ = (
        Index("idx_bill_usage_user_created", "user_bid", "created_at"),
        Index("idx_bill_usage_shifu_created", "shifu_bid", "created_at"),
        Index("idx_bill_usage_type_created", "usage_type", "created_at"),
        {"comment": "Bill usage records for LLM/TTS billing"},
    )

    # 1. Primary key
    id = Column(BIGINT, primary_key=True, autoincrement=True)

    # 2. Business identifier
    usage_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Usage business identifier",
    )

    # 3. Parent identifier (for segment records)
    parent_usage_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Parent usage business identifier",
    )

    # 4. Context identifiers
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

    outline_item_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Outline item business identifier",
    )

    progress_record_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Progress record business identifier",
    )

    generated_block_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Generated block business identifier",
    )

    audio_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Audio business identifier",
    )

    request_id = Column(
        String(64),
        nullable=False,
        default="",
        index=True,
        comment="Request identifier (X-Request-ID)",
    )

    trace_id = Column(
        String(64),
        nullable=False,
        default="",
        comment="Trace identifier (Langfuse)",
    )

    # 5. Usage classification
    usage_type = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Usage type: 1101=LLM, 1102=TTS",
    )

    record_level = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Record level: 0=request, 1=segment",
    )

    usage_scene = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Usage scene: 1201=debug, 1202=preview, 1203=production",
    )

    # 6. Provider metadata
    provider = Column(
        String(32),
        nullable=False,
        default="",
        comment="Provider name",
    )

    model = Column(
        String(100),
        nullable=False,
        default="",
        comment="Provider model",
    )

    is_stream = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Is stream: 0=no, 1=yes",
    )

    # 7. Usage metrics (input/output/total)
    input = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Input usage (tokens for LLM, chars for TTS)",
    )

    output = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Output usage (tokens for LLM, chars for TTS)",
    )

    total = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Total usage (tokens for LLM, chars for TTS)",
    )

    word_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="TTS provider word count",
    )

    duration_ms = Column(
        Integer,
        nullable=False,
        default=0,
        comment="TTS duration in milliseconds",
    )

    latency_ms = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Latency in milliseconds",
    )

    segment_index = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Segment index for segment records",
    )

    segment_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of segments",
    )

    # 8. Status
    billable = Column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="Billable: 0=no, 1=yes",
    )

    status = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Status: 0=success, 1=failed",
    )

    error_message = Column(
        Text,
        nullable=True,
        comment="Error message",
    )

    extra = Column(
        JSON,
        nullable=True,
        comment="Extra metadata",
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
