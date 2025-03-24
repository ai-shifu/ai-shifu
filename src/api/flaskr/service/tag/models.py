from sqlalchemy import Column, String, TIMESTAMP, Text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func

from ...dao import db


class Tag(db.Model):
    __tablename__ = "tag"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    tag_id = Column(
        String(36),
        nullable=False,
        default="",
        comment="Tag ID",
        index=True,
    )
    tag_domain = Column(String(64), nullable=False, default="", comment="Tag domain")
    tag_type = Column(String(64), nullable=False, default="", comment="Tag type")
    tag_name = Column(String(255), nullable=False, default="", comment="Tag name")
    meta_data = Column(Text, nullable=True, comment="Meta Data", default="{}")
    extra_data = Column(Text, nullable=True, comment="Extra Data", default="{}")
    created_user_id = Column(
        String(36), nullable=True, default="", comment="created user ID"
    )
    updated_user_id = Column(
        String(36), nullable=True, default="", comment="updated user ID"
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
