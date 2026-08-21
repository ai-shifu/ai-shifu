"""Define persistence models for resources."""

from flaskr.dao import db
from flaskr.util.datetime import now_utc
from sqlalchemy import TIMESTAMP, Column, Integer, String
from sqlalchemy.dialects.mysql import BIGINT


class Resource(db.Model):
    """Persist resource records."""

    __tablename__ = "resource"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    resource_id = Column(String(36), nullable=False, comment="Resource UUID")
    name = Column(String(255), nullable=False, comment="Resource name")
    type = Column(Integer, nullable=False, comment="Resource type")
    oss_bucket = Column(String(255), nullable=False, comment="OSS bucket")
    oss_name = Column(String(255), nullable=False, comment="OSS object key")
    url = Column(String(255), nullable=False, comment="Resource URL")
    status = Column(Integer, nullable=False, comment="Resource status")
    is_deleted = Column(Integer, nullable=False, comment="Is deleted")
    created_by = Column(String(36), nullable=False, comment="Created by")
    updated_by = Column(String(36), nullable=False, comment="Updated by")
    created_at = Column(
        TIMESTAMP, nullable=False, default=now_utc, comment="Creation time"
    )
    updated_at = Column(
        TIMESTAMP, nullable=False, default=now_utc, comment="Update time"
    )


class ResourceUsage(db.Model):
    """Persist resource usage records."""

    __tablename__ = "resource_usage"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    usage_id = Column(String(36), nullable=False, comment="Usage UUID")
    resource_id = Column(String(36), nullable=False, comment="Resource UUID")
    usage_type = Column(Integer, nullable=False, comment="Usage type")
    usage_value = Column(Integer, nullable=False, comment="Usage value")
    is_deleted = Column(Integer, nullable=False, comment="Is deleted")
    created_by = Column(String(36), nullable=False, comment="Created by")
    updated_by = Column(String(36), nullable=False, comment="Updated by")
    created_at = Column(
        TIMESTAMP, nullable=False, default=now_utc, comment="Creation time"
    )
    updated_at = Column(
        TIMESTAMP, nullable=False, default=now_utc, comment="Update time"
    )
