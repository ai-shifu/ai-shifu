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
    attend_id = Column(String(36), nullable=False, default="", comment="Attend UUID")
    script_id = Column(String(36), nullable=False, default="", comment="Script UUID")
    lesson_id = Column(String(36), nullable=False, default="", comment="Lesson UUID")
    course_id = Column(String(36), nullable=False, default="", comment="Course UUID")
    user_id = Column(String(36), nullable=False, default="", comment="User UUID")
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


class AICourseStudyProgress(db.Model):
    __tablename__ = "ai_course_study_progress"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    progress_id = Column(
        String(36), nullable=False, default="", comment="Progress UUID", index=True
    )
    user_id = Column(
        String(36), nullable=False, default="", comment="User UUID", index=True
    )
    course_id = Column(
        String(36), nullable=False, default="", comment="Course UUID", index=True
    )
    chapter_count = Column(Integer, nullable=False, default=0, comment="Chapter Count")
    chapter_completed_count = Column(
        Integer, nullable=False, default=0, comment="Chapter Completed Count"
    )
    chapter_reset_count = Column(
        Integer, nullable=False, default=0, comment="Chapter Reset Count"
    )
    is_paid = Column(Integer, nullable=False, default=0, comment="Is Paid", index=True)
    is_completed = Column(
        Integer, nullable=False, default=0, comment="Is Completed", index=True
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


class AILessonStudyProgress(db.Model):
    __tablename__ = "ai_lesson_study_progress"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    progress_id = Column(
        String(36), nullable=False, default="", index=True, comment="Progress UUID"
    )
    lesson_id = Column(String(36), nullable=False, default="", comment="Lesson UUID")
    begin_time = Column(TIMESTAMP, nullable=True, comment="Begin Time")
    end_time = Column(TIMESTAMP, nullable=True, comment="End Time")
    sublesson_count = Column(
        Integer, nullable=False, default=0, comment="Sublesson Count"
    )
    sublesson_completed_count = Column(
        Integer, nullable=False, default=0, comment="Sublesson Completed Count"
    )
    script_index = Column(Integer, nullable=False, default=0, comment="Script Index")
    script_count = Column(Integer, nullable=False, default=0, comment="Script Count")
    reset_count = Column(Integer, nullable=False, default=0, comment="Reset Count")
    lesson_is_updated = Column(
        Integer, nullable=False, default=0, comment="Lesson Is Updated"
    )
    is_completed = Column(Integer, nullable=False, default=0, comment="Is Completed")
    completed_time = Column(TIMESTAMP, nullable=True, comment="Completed Time")
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
