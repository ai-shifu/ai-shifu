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


class AICourseLessonAttendScript(db.Model):
    __tablename__ = "ai_course_lesson_attendscript"

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    log_id = Column(
        String(36), nullable=False, index=True, default="", comment="Log UUID"
    )
    attend_id = Column(
        String(36), nullable=False, default="", comment="Attend UUID", index=True
    )
    script_id = Column(
        String(36), nullable=False, default="", comment="Script UUID", index=True
    )
    lesson_id = Column(
        String(36), nullable=False, default="", comment="Lesson UUID", index=True
    )
    course_id = Column(
        String(36), nullable=False, default="", comment="Course UUID", index=True
    )
    script_ui_type = Column(
        Integer, nullable=False, default=0, comment="Script UI type"
    )
    script_ui_conf = Column(
        Text, nullable=False, default="", comment="Script UI Config"
    )
    user_id = Column(
        String(36), nullable=False, default="", comment="User UUID", index=True
    )
    interaction_type = Column(
        Integer, nullable=False, default=0, comment="Interaction type: 0-no interaction, 1-like, 2-dislike"
    )
    script_index = Column(Integer, nullable=False, default=0, comment="Script index")
    script_role = Column(Integer, nullable=False, default=0, comment="Script role")
    script_content = Column(Text, nullable=False, comment="Script content")
    status = Column(Integer, nullable=False, default=0, comment="Status of the attend")
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


class AICourseAttendAsssotion(db.Model):
    __tablename__ = "ai_course_lesson_attend_association"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    association_id = Column(
        String(36), nullable=False, default="", comment="Attend UUID"
    )
    from_attend_id = Column(
        String(36), nullable=False, default="", comment="Attend UUID"
    )
    to_attend_id = Column(String(36), nullable=False, default="", comment="Attend UUID")
    user_id = Column(String(36), nullable=False, default="", comment="Attend UUID")
    association_status = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Status of the attend: 0-not started, 1-in progress, 2-completed",
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
