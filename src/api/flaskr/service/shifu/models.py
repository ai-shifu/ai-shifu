from sqlalchemy import Column, String, Integer, TIMESTAMP
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db


class ResourceType:
    CHAPTER = 9001
    SECTION = 9002
    BLOCK = 9003


class FavoriteScenario(db.Model):
    __tablename__ = "scenario_favorite"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    scenario_id = Column(
        String(36), nullable=False, default="", comment="Scenario UUID"
    )
    user_id = Column(String(36), nullable=False, default="", comment="User UUID")
    status = Column(Integer, nullable=False, default=0, comment="Status")
    created_at = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )


class ScenarioResource(db.Model):
    __tablename__ = "scenario_resource"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    resource_resource_id = Column(
        String(36), nullable=False, default="", comment="Resource UUID", index=True
    )
    scenario_id = Column(
        String(36), nullable=False, default="", comment="Scenario UUID", index=True
    )
    chapter_id = Column(
        String(36), nullable=False, default="", comment="Chapter UUID", index=True
    )
    resource_type = Column(Integer, nullable=False, default=0, comment="Resource type")
    resource_id = Column(
        String(36), nullable=False, default="", comment="Resource UUID", index=True
    )
    is_deleted = Column(Integer, nullable=False, default=0, comment="Is deleted")
    created_at = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )


class AiCourseAuth(db.Model):
    __tablename__ = "ai_course_auth"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    course_auth_id = Column(
        String(36),
        nullable=False,
        default="",
        comment="course_auth_id UUID",
        index=True,
    )
    course_id = Column(String(36), nullable=False, default="", comment="course_id UUID")
    user_id = Column(String(36), nullable=False, default="", comment="User UUID")
    # 1 read 2 write 3 delete 4 publish
    auth_type = Column(String(255), nullable=False, default="[]", comment="auth_info")
    status = Column(Integer, nullable=False, default=0, comment="Status")
    created_at = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )
