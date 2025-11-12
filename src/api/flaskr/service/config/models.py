from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    SmallInteger,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db


class Config(db.Model):
    """
    Config
    """

    __tablename__ = "sys_configs"
    __table_args__ = {"comment": "System configs"}

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    config_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Config business identifier",
        index=True,
    )
    key = Column(
        String(255),
        nullable=False,
        default="",
        comment="Config key",
        index=True,
    )
    value = Column(
        Text,
        nullable=False,
        default="",
        comment="Config value",
    )
    is_encrypted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Is encrypted: 0=no, 1=yes",
    )
    remark = Column(
        Text,
        nullable=False,
        default="",
        comment="Config remark",
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    updated_by = Column(
        String(36),
        nullable=False,
        default="",
        comment="Updated by",
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
