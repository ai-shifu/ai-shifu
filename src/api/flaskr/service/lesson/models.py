from sqlalchemy import Column, String, Integer, TIMESTAMP, Text, Numeric, DECIMAL
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db
from .const import ASK_MODE_DEFAULT, LESSON_TYPE_TRIAL


class AICourse(db.Model):
    __tablename__ = "ai_course"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    course_id = Column(
        String(36), nullable=False, default="", comment="Course UUID", index=True
    )
    course_name = Column(String(255), nullable=False, default="", comment="Course name")
    course_desc = Column(Text, nullable=False, comment="Course description", default="")
    course_keywords = Column(
        Text, nullable=False, comment="Course keywords", default=""
    )
    course_price = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Course price"
    )
    course_status = Column(Integer, nullable=False, default=0, comment="Course status")
    course_feishu_id = Column(
        String(255), nullable=False, default="", comment="Course feishu ID"
    )
    course_teacher_avator = Column(
        String(255), nullable=False, default="", comment="Course teacher avatar"
    )
    course_default_model = Column(
        String(255), nullable=False, default="", comment="Course default model"
    )
    course_default_temprature = Column(
        DECIMAL(10, 2),
        nullable=False,
        default="0.3",
        comment="Course default temprature",
    )
    course_language = Column(
        String(255), nullable=False, default="", comment="Course language"
    )
    course_name_multi_language = Column(
        Text, nullable=False, default=0, comment="Course multi language"
    )

    ask_count_limit = Column(
        Integer, nullable=False, default=5, comment="Ask count limit"
    )
    ask_model = Column(
        String(255), nullable=False, default="", comment="Ask count model"
    )
    ask_prompt = Column(Text, nullable=False, default="", comment="Ask Prompt")
    ask_with_history = Column(
        Integer, nullable=False, default=3, comment="Ask with history Count"
    )
    ask_mode = Column(
        Integer, nullable=False, default=ASK_MODE_DEFAULT, comment="Ask mode"
    )
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
    status = Column(Integer, nullable=False, default=0, comment="Status of the course")


class AILesson(db.Model):
    __tablename__ = "ai_lesson"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    lesson_id = Column(
        String(36), nullable=False, default="", comment="Lesson UUID", index=True
    )
    course_id = Column(
        String(36), nullable=False, default="", comment="Course UUID", index=True
    )
    parent_id = Column(
        String(36), nullable=False, default="", comment="Parent lesson UUID", index=True
    )
    lesson_name = Column(String(255), nullable=False, default="", comment="Lesson name")
    lesson_desc = Column(Text, nullable=False, comment="Lesson description", default="")
    lesson_no = Column(String(32), nullable=True, default="0", comment="Lesson number")
    lesson_index = Column(Integer, nullable=False, default=0, comment="Lesson index")
    lesson_feishu_id = Column(
        String(255), nullable=False, default="", comment="Lesson feishu ID"
    )
    lesson_status = Column(Integer, nullable=False, default=0, comment="Lesson status")
    lesson_type = Column(
        Integer, nullable=False, default=LESSON_TYPE_TRIAL, comment="Lesson type"
    )
    lesson_summary = Column(Text, nullable=False, default="", comment="Lesson summary")
    lesson_language = Column(
        String(255), nullable=False, default="", comment="Lesson language"
    )
    lesson_default_model = Column(
        String(255), nullable=False, default="", comment="Lesson default model"
    )
    lesson_default_temprature = Column(
        DECIMAL(10, 2),
        nullable=False,
        default="0.3",
        comment="Lesson default temprature",
    )
    lesson_name_multi_language = Column(
        Text, nullable=False, default="", comment="Lesson multi language"
    )
    ask_count_limit = Column(
        Integer, nullable=False, default=5, comment="Ask count limit"
    )
    ask_model = Column(
        String(255), nullable=False, default="", comment="Ask count model"
    )
    ask_prompt = Column(Text, nullable=False, default="", comment="Ask Prompt")
    ask_with_history = Column(
        Integer, nullable=False, default=3, comment="Ask with history Count"
    )
    ask_mode = Column(
        Integer, nullable=False, default=ASK_MODE_DEFAULT, comment="Ask mode"
    )
    pre_lesson_no = Column(
        String(255), nullable=False, default="", comment="pre_lesson_no"
    )
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
    status = Column(Integer, nullable=False, default=0, comment="Status of the lesson")
    parent_id = Column(
        String(36), nullable=False, default="", comment="Parent lesson UUID", index=True
    )

    def is_final(self):
        return len(self.lesson_no) > 2


class AILessonScript(db.Model):
    __tablename__ = "ai_lesson_script"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    script_id = Column(String(36), nullable=False, default="", comment="Script UUID")
    lesson_id = Column(String(36), nullable=False, default="", comment="Lesson UUID")
    script_name = Column(String(255), nullable=False, default="", comment="Script name")
    script_desc = Column(Text, nullable=False, default="", comment="Script description")
    script_index = Column(Integer, nullable=False, default=0, comment="Script index")
    script_feishu_id = Column(
        String(255), nullable=False, default="", comment="Script feishu ID"
    )
    script_version = Column(
        Integer, nullable=False, default=0, comment="Script version"
    )
    script_no = Column(Integer, nullable=False, default=0, comment="Script number")
    script_type = Column(Integer, nullable=False, default=0, comment="Script type")
    script_content_type = Column(
        Integer, nullable=False, default=0, comment="Script content type"
    )
    script_prompt = Column(Text, nullable=False, default="", comment="Script prompt")
    script_model = Column(
        String(36), nullable=False, default="", comment="Script model"
    )
    script_temprature = Column(
        DECIMAL(10, 2), nullable=False, default="0.8", comment="Script Temprature"
    )
    script_profile = Column(Text, nullable=False, default="", comment="Script profile")
    script_media_url = Column(
        Text, nullable=False, default="", comment="Script media URL"
    )
    script_ui_type = Column(
        Integer, nullable=False, default=0, comment="Script UI type"
    )
    script_ui_content = Column(
        Text, nullable=False, default="", comment="Script UI content"
    )
    script_check_prompt = Column(
        Text, nullable=False, default="", comment="Script check prompt"
    )
    script_check_flag = Column(
        Text, nullable=False, default="", comment="Script check flag"
    )
    script_ui_profile = Column(
        Text, nullable=False, default="", comment="Script UI profile"
    )
    script_ui_profile_id = Column(
        String(36),
        nullable=False,
        default="",
        comment="Script UI profile id",
        index=True,
    )
    script_end_action = Column(
        Text, nullable=False, default="", comment="Script end action"
    )
    script_other_conf = Column(
        Text, nullable=False, default="{}", comment="Other configurations of the script"
    )
    ask_count_limit = Column(
        Integer, nullable=False, default=5, comment="Ask count limit"
    )
    ask_model = Column(
        String(255), nullable=False, default=ASK_MODE_DEFAULT, comment="Ask count model"
    )
    ask_prompt = Column(Text, nullable=False, default="", comment="Ask count history")
    ask_with_history = Column(
        Integer, nullable=False, default=3, comment="Ask with history Count"
    )
    ask_mode = Column(Integer, nullable=False, default=0, comment="Ask mode")
    script_ui_profile_id = Column(
        String(36),
        nullable=False,
        default="",
        comment="Script UI profile id",
        index=True,
    )
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
    status = Column(Integer, nullable=False, default=0, comment="Status of the script")
