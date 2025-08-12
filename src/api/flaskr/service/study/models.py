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

from order.consts import LEARN_STATUS_LOCKED


class LearnOutlineItemProgress(db.Model):
    """
    Learn outline item progress
    """

    __tablename__ = "learn_outlineitems_progress"

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    learn_outline_item_bid = Column(
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
    outline_bid = Column(
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
    outline_updated = Column(
        Integer, nullable=False, default=0, comment="Outline is updated"
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=LEARN_STATUS_LOCKED,
        comment="Status: 601=not started, 602=in progress, 603=completed, 604=refund, 605=locked, 606=unavailable, 607=branch, 608=reset",
        index=True,
    )
    block_position_index = Column(
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


class LearnBlockLog(db.Model):
    """
    Learn Block Log
    """

    __tablename__ = "learn_blocks_logs"

    id = Column(BIGINT, primary_key=True, autoincrement=True)

    learn_block_log_bid = Column(
        String(36),
        nullable=False,
        index=True,
        default="",
        comment="Learn block log business identifier",
    )
    learn_outline_item_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Learn outline item business identifier",
        index=True,
    )
    block_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Block business identifier",
        index=True,
    )
    outline_bid = Column(
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
    block_content_type = Column(
        Integer, nullable=False, default=0, comment="Block content type"
    )
    block_content_conf = Column(
        Text,
        nullable=False,
        default="",
        comment="Block content config(used for re-generate)",
    )
    user_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="User business identifier",
        index=True,
    )
    interaction_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Interaction type: 0=no interaction, 1=like, 2=dislike",
    )
    block_position_index = Column(
        Integer, nullable=False, default=0, comment="Block position index"
    )
    block_log_role = Column(Integer, nullable=False, default=0, comment="Block role")
    block_generate_content = Column(
        Text, nullable=False, comment="Block generate content"
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
