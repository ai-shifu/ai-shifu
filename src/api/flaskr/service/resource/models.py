from sqlalchemy import Column, String, Integer, TIMESTAMP
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db


class Resource(db.Model):
    __tablename__ = "resource"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    resource_id = Column(String(36), nullable=False, comment="Resource UUID")
    name = Column(String(255), nullable=False, comment="Resource name")
    type = Column(Integer, nullable=False, comment="Resource type")
    oss_bucket = Column(String(255), nullable=False, comment="OSS bucket")
    oss_name = Column(String(255), nullable=False, comment="OSS name")
    url = Column(String(255), nullable=False, comment="Resource URL")
    status = Column(Integer, nullable=False, comment="Resource status")
    is_deleted = Column(Integer, nullable=False, comment="Is deleted")
    created_by = Column(String(36), nullable=False, comment="Created by")
    updated_by = Column(String(36), nullable=False, comment="Updated by")
    created_at = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated_at = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Update time"
    )


class ResourceUsage(db.Model):
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
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated_at = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Update time"
    )
