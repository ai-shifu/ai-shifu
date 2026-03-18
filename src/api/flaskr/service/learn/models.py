from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    SmallInteger,
    Index,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db

from flaskr.service.order.consts import LEARN_STATUS_LOCKED


class LearnProgressRecord(db.Model):
    """
    Learn progress record
    """

    __tablename__ = "learn_progress_records"
    __table_args__ = {"comment": "Learn progress records"}

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    progress_record_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Learn outline item business identifier",
        index=True,
    )
    shifu_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Shifu business identifier",
        index=True,
    )
    outline_item_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Outline business identifier",
        index=True,
    )
    user_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="User business identifier",
        index=True,
    )
    outline_item_updated = Column(
        Integer, nullable=False, default=0, comment="Outline is updated"
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=LEARN_STATUS_LOCKED,
        comment="Status: 601=not started, 602=in progress, 603=completed, 604=refund, 605=locked, 606=unavailable, 607=branch, 608=reset",
        index=True,
    )
    block_position = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Block position index of the outlineitem",
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Creation time",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Update time",
        onupdate=func.now(),
    )


class LearnGeneratedBlock(db.Model):
    """
    Learn generated block
    """

    __tablename__ = "learn_generated_blocks"
    __table_args__ = {"comment": "Learn generated blocks"}
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    generated_block_bid = Column(
        String(36),
        nullable=False,
        index=True,
        default="",
        comment="Learn block log business identifier",
    )
    progress_record_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Learn outline item business identifier",
        index=True,
    )
    user_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="User business identifier",
        index=True,
    )
    block_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Block business identifier",
        index=True,
    )
    outline_item_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Outline business identifier",
        index=True,
    )
    shifu_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Shifu business identifier",
        index=True,
    )
    type = Column(Integer, nullable=False, default=0, comment="Block content type")
    role = Column(Integer, nullable=False, default=0, comment="Block role")
    generated_content = Column(
        Text, nullable=False, default="", comment="Block generate content"
    )
    position = Column(
        Integer, nullable=False, default=0, comment="Block position index"
    )
    block_content_conf = Column(
        Text,
        nullable=False,
        default="",
        comment="Block content config(used for re-generate)",
    )
    liked = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Interaction type: -1=disliked, 0=not available, 1=liked",
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    status = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Status of the record: 1=active, 0=history",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation time"
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )


class LearnGeneratedElement(db.Model):
    """Listen-mode generated element snapshots and events."""

    __tablename__ = "learn_generated_elements"
    __table_args__ = {"comment": "Listen-mode generated elements"}

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    element_bid = Column(
        String(64),
        nullable=False,
        default="",
        index=True,
        comment="Element business identifier",
    )
    progress_record_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Learn progress record business identifier",
        index=True,
    )
    user_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="User business identifier",
        index=True,
    )
    generated_block_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Source generated block business identifier",
        index=True,
    )
    outline_item_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Outline business identifier",
        index=True,
    )
    shifu_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Shifu business identifier",
        index=True,
    )
    run_session_bid = Column(
        String(64),
        nullable=False,
        default="",
        comment="Run session business identifier",
        index=True,
    )
    run_event_seq = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Run event sequence within the session",
        index=True,
    )
    event_type = Column(
        String(32),
        nullable=False,
        default="element",
        comment="Event type: element/break/done/error/audio_segment/audio_complete/variable_update/outline_item_update",
        index=True,
    )
    role = Column(
        String(16),
        nullable=False,
        default="teacher",
        comment="Element role: teacher/student/ui",
    )
    element_index = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Listen-mode navigation index",
        index=True,
    )
    element_type = Column(
        String(32),
        nullable=False,
        default="",
        comment="Element type: html/svg/diff/img/interaction/tables/code/latex/md_img/mermaid/title/text",
        index=True,
    )
    element_type_code = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Element type numeric code",
    )
    change_type = Column(
        String(16),
        nullable=False,
        default="",
        comment="Change type: render/diff",
    )
    target_element_bid = Column(
        String(64),
        nullable=False,
        default="",
        comment="Diff target element business identifier",
        index=True,
    )
    is_renderable = Column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="Renderable flag: 1=renderable, 0=non-renderable",
        index=True,
    )
    is_new = Column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="New element flag: 1=creates new element, 0=patches existing via target_element_bid",
        index=True,
    )
    is_marker = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Marker flag: 1=forward/backward navigation anchor, 0=normal",
        index=True,
    )
    sequence_number = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Element generation sequence within the run session (strictly increasing)",
        index=True,
    )
    is_speakable = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Speakable flag: 1=needs TTS synthesis, 0=silent",
        index=True,
    )
    audio_url = Column(
        String(512),
        nullable=False,
        default="",
        comment="Complete audio URL; empty until audio is finalized",
    )
    audio_segments = Column(
        Text,
        nullable=False,
        default="[]",
        comment="Audio segment trail as JSON array",
    )
    is_navigable = Column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="Navigation flag: 1=navigable, 0=non-navigable",
        index=True,
    )
    is_final = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Final snapshot flag: 1=final, 0=partial",
        index=True,
    )
    content_text = Column(
        Text,
        nullable=False,
        default="",
        comment="Element textual content snapshot",
    )
    payload = Column(
        Text,
        nullable=False,
        default="",
        comment="Element payload JSON",
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
        index=True,
    )
    status = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Record status: 1=active, 0=history",
        index=True,
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


class LearnLessonFeedback(db.Model):
    """Lesson feedback record (one effective record per user + lesson)."""

    __tablename__ = "learn_lesson_feedbacks"
    __table_args__ = (
        Index(
            "idx_learn_lesson_feedback_unique_active",
            "shifu_bid",
            "outline_item_bid",
            "user_bid",
            "deleted",
            unique=True,
        ),
        {"comment": "Learn lesson feedback records"},
    )

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Lesson feedback business identifier",
        index=True,
    )
    lesson_feedback_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Lesson feedback business identifier",
        index=True,
    )
    shifu_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Shifu business identifier",
        index=True,
    )
    outline_item_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Outline item business identifier",
        index=True,
    )
    progress_record_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Learn progress record business identifier",
        index=True,
    )
    user_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="User business identifier",
        index=True,
    )
    score = Column(
        SmallInteger,
        nullable=False,
        comment="Lesson score: 1-5",
    )
    comment = Column(
        Text,
        nullable=False,
        default="",
        comment="Optional feedback comment",
    )
    mode = Column(
        String(16),
        nullable=False,
        default="read",
        comment="Submit mode: read or listen",
        index=True,
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
        index=True,
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
