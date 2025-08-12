from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db

from order.consts import ATTEND_STATUS_LOCKED


class LearnOutlineItemProgress(db.Model):
    """
    Shifu User Comsumption
    """

    __tablename__ = "learn_outlineitems_progress"

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    learn_outline_item_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Learn Outline Item Business ID",
        index=True,
    )

    shifu_bid = Column(
        String(36), nullable=False, default="", comment="Shifu Business ID", index=True
    )
    outline_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Outline Business ID",
        index=True,
    )
    user_bid = Column(
        String(36), nullable=False, default="", comment="User Business ID", index=True
    )
    outline_updated = Column(
        Integer, nullable=False, default=0, comment="Usage is updated"
    )
    status = Column(
        Integer,
        nullable=False,
        default=ATTEND_STATUS_LOCKED,
        comment="Status of the comsumption: 601-not started, 602-in progress, 603-completed, 604-refund, 605-locked, 606-unavailable, 607-branch, 608-reset",
        index=True,
    )
    block_position_index = Column(
        Integer,
        nullable=False,
        default=0,
        comment="block position index of the comsumption",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Creation timestamp",
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last update timestamp",
        onupdate=func.now(),
    )


class LearnBlockLog(db.Model):
    """
    Learn Block Log
    """

    __tablename__ = "learn_blocks_logs"

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    learn_block_log_bid = Column(
        String(36),
        nullable=False,
        index=True,
        default="",
        comment="Learn Block Log Business ID",
    )
    learn_outline_item_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Learn Outline Item Business ID",
        index=True,
    )
    block_bid = Column(
        String(36), nullable=False, default="", comment="Block Business ID", index=True
    )
    outline_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Outline Business ID",
        index=True,
    )
    shifu_bid = Column(
        String(36), nullable=False, default="", comment="Shifu Business ID", index=True
    )
    block_content_type = Column(
        Integer, nullable=False, default=0, comment="Block Content Type"
    )
    block_content_conf = Column(
        Text,
        nullable=False,
        default="",
        comment="Block Content Config(used for re-generate)",
    )
    user_bid = Column(
        String(36), nullable=False, default="", comment="User Business ID", index=True
    )
    interaction_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Interaction type: 0-no interaction, 1-like, 2-dislike",
    )
    block_position_index = Column(
        Integer, nullable=False, default=0, comment="Block Position Index"
    )
    block_log_role = Column(Integer, nullable=False, default=0, comment="Block Role")
    block_generate_content = Column(
        Text, nullable=False, comment="Block Generate Content"
    )
    status = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Status of the record: 1-active, 0-history",
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
