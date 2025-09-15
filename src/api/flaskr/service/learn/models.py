from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    SmallInteger,
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
