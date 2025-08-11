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


class ShifuUserComsumptionRecordLog(db.Model):
    """
    Shifu User Comsumption Record Log
    """

    __tablename__ = "shifu_user_comsumption_record_logs"

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    log_id = Column(
        String(36), nullable=False, index=True, default="", comment="Log UUID"
    )
    comsumption_record_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Comsumption Record Business ID",
        index=True,
    )
    block_bid = Column(
        String(36), nullable=False, default="", comment="Script UUID", index=True
    )
    outline_bid = Column(
        String(36), nullable=False, default="", comment="Outline UUID", index=True
    )
    shifu_bid = Column(
        String(36), nullable=False, default="", comment="Course UUID", index=True
    )
    block_content_type = Column(
        Integer, nullable=False, default=0, comment="Block Content Type"
    )
    block_content_conf = Column(
        Text, nullable=False, default="", comment="Block Content Config"
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
    status = Column(Integer, nullable=False, default=0, comment="Status of the record")
    created = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )
