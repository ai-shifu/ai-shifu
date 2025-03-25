from sqlalchemy import (
    Column,
    String,
    Integer,
    TIMESTAMP,
    Text,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db


class UserProfile(db.Model):
    __tablename__ = "user_profile"

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    user_id = Column(String(36), nullable=False, default="", comment="User UUID")
    profile_id = Column(
        String(36), nullable=False, comment="Profile ID", index=True, default=""
    )
    profile_key = Column(String(255), nullable=False, default="", comment="Profile key")
    profile_value = Column(Text, nullable=False, comment="Profile value")
    profile_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment="0 default, 1 system configuration, 2 user configuration, 3 course configuration",
    )
    created = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )
    status = Column(
        Integer, nullable=False, default=0, comment="0 for deleted, 1 for active"
    )
