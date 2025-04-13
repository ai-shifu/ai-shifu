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
    status = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Status of the lesson: 0-delete ,1-publish,2-draft",
    )
    parent_id = Column(
        String(36), nullable=False, default="", comment="Parent lesson UUID", index=True
    )

    def is_final(self):
        return len(self.lesson_no) > 2

    def clone(self):
        return AILesson(
            lesson_id=self.lesson_id,
            lesson_name=self.lesson_name,
            lesson_desc=self.lesson_desc,
            lesson_no=self.lesson_no,
            lesson_index=self.lesson_index,
            lesson_feishu_id=self.lesson_feishu_id,
            lesson_status=self.lesson_status,
            lesson_type=self.lesson_type,
            lesson_summary=self.lesson_summary,
            lesson_language=self.lesson_language,
            lesson_default_model=self.lesson_default_model,
            lesson_default_temprature=self.lesson_default_temprature,
            lesson_name_multi_language=self.lesson_name_multi_language,
            ask_count_limit=self.ask_count_limit,
            ask_model=self.ask_model,
            ask_prompt=self.ask_prompt,
            ask_with_history=self.ask_with_history,
            ask_mode=self.ask_mode,
            pre_lesson_no=self.pre_lesson_no,
            created_user_id=self.created_user_id,
            updated_user_id=self.updated_user_id,
            created=self.created,
            updated=self.updated,
            status=self.status,
        )

    def eq(self, other):
        return (
            self.lesson_id == other.lesson_id
            and self.lesson_name == other.lesson_name
            and self.lesson_desc == other.lesson_desc
            and self.lesson_no == other.lesson_no
            and self.lesson_index == other.lesson_index
        )


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

    def clone(self):
        return AILessonScript(
            script_id=self.script_id,
            lesson_id=self.lesson_id,
            script_name=self.script_name,
            script_desc=self.script_desc,
            script_index=self.script_index,
            script_feishu_id=self.script_feishu_id,
            script_version=self.script_version,
            script_no=self.script_no,
            script_type=self.script_type,
            script_content_type=self.script_content_type,
            script_prompt=self.script_prompt,
            script_model=self.script_model,
            script_temprature=self.script_temprature,
            script_profile=self.script_profile,
            script_media_url=self.script_media_url,
            script_ui_type=self.script_ui_type,
            script_ui_content=self.script_ui_content,
            script_check_prompt=self.script_check_prompt,
            script_check_flag=self.script_check_flag,
            script_ui_profile=self.script_ui_profile,
            script_ui_profile_id=self.script_ui_profile_id,
            script_end_action=self.script_end_action,
            script_other_conf=self.script_other_conf,
            ask_count_limit=self.ask_count_limit,
            ask_model=self.ask_model,
            ask_prompt=self.ask_prompt,
            ask_with_history=self.ask_with_history,
            ask_mode=self.ask_mode,
            created_user_id=self.created_user_id,
            updated_user_id=self.updated_user_id,
            created=self.created,
            updated=self.updated,
            status=self.status,
        )

    def eq(self, other):
        return (
            self.script_id == other.script_id
            and self.lesson_id == other.lesson_id
            and self.script_name == other.script_name
            and self.script_desc == other.script_desc
            and self.script_index == other.script_index
            and self.script_feishu_id == other.script_feishu_id
            and self.script_version == other.script_version
            and self.script_no == other.script_no
            and self.script_type == other.script_type
            and self.script_content_type == other.script_content_type
            and self.script_prompt == other.script_prompt
            and self.script_model == other.script_model
            and self.script_temprature == other.script_temprature
            and self.script_profile == other.script_profile
            and self.script_media_url == other.script_media_url
            and self.script_ui_type == other.script_ui_type
            and self.script_ui_content == other.script_ui_content
            and self.script_check_prompt == other.script_check_prompt
            and self.script_check_flag == other.script_check_flag
            and self.script_ui_profile == other.script_ui_profile
            and self.script_ui_profile_id == other.script_ui_profile_id
            and self.script_end_action == other.script_end_action
            and self.script_other_conf == other.script_other_conf
            and self.ask_count_limit == other.ask_count_limit
            and self.ask_model == other.ask_model
            and self.ask_prompt == other.ask_prompt
            and self.ask_with_history == other.ask_with_history
            and self.ask_mode == other.ask_mode
            and self.created_user_id == other.created_user_id
            and self.updated_user_id == other.updated_user_id
        )
