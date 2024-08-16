from sqlalchemy import Column, String, Integer, TIMESTAMP, Text, Numeric, text, ForeignKey,DECIMAL
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from ...dao import db

class AICourse(db.Model):
    __tablename__ = 'ai_course'
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    course_id = Column(String(36), nullable=False, default='', comment='Course UUID')
    course_name = Column(String(255), nullable=False, default='', comment='Course name')
    course_desc = Column(Text, nullable=False, comment='Course description')
    course_price = Column(Numeric(10, 2), nullable=False, default='0.00', comment='Course price')
    course_status = Column(Integer, nullable=False, default=0, comment='Course status')
    course_feishu_id = Column(String(255), nullable=False, default='', comment='Course feishu ID')
    created = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Creation time')
    updated = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now(), comment='Update time')
    status = Column(Integer, nullable=False, default=0, comment='Status of the course')

class AILesson(db.Model):
    __tablename__ = 'ai_lesson'
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    lesson_id = Column(String(36), nullable=False, default='', comment='Lesson UUID')
    course_id = Column(String(36), ForeignKey('ai_course.course_id'), nullable=False, default='', comment='Course UUID')
    lesson_name = Column(String(255), nullable=False, default='', comment='Lesson name')
    lesson_desc = Column(Text, nullable=False, comment='Lesson description')
    lesson_no = Column(String(32), nullable=True, default='0', comment='Lesson number')
    lesson_index = Column(Integer, nullable=False, default=0, comment='Lesson index')
    lesson_feishu_id = Column(String(255), nullable=False, default='', comment='Lesson feishu ID')
    lesson_status = Column(Integer, nullable=False, default=0, comment='Lesson status')
    lesson_type = Column(Integer, nullable=False, default=0, comment='Lesson type')
    pre_lesson_no = Column(String(255), nullable=False, default='', comment='pre_lesson_no')
    created = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Creation time')
    updated = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now(), comment='Update time')
    status = Column(Integer, nullable=False, default=0, comment='Status of the lesson')
    def is_final(self):
        return len(self.lesson_no)>2 

    
class AILessonScript(db.Model):
    __tablename__ = 'ai_lesson_script'

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment='Unique ID')
    script_id = Column(String(36), nullable=False, default='', comment='Script UUID')
    lesson_id = Column(String(36), ForeignKey('ai_lesson.lesson_id'), nullable=False, default='', comment='Lesson UUID')
    script_name = Column(String(255), nullable=False, default='', comment='Script name')
    script_desc = Column(Text, nullable=False, comment='Script description')
    script_index = Column(Integer, nullable=False, default=0, comment='Script index')
    script_feishu_id = Column(String(255), nullable=False, default='', comment='Script feishu ID')
    script_version = Column(Integer, nullable=False, default=0, comment='Script version')
    script_no = Column(Integer, nullable=False, default=0, comment='Script number')
    script_type = Column(Integer, nullable=False, default=0, comment='Script type')
    script_content_type = Column(Integer, nullable=False, default=0, comment='Script content type')
    script_prompt = Column(Text, nullable=False, comment='Script prompt')
    script_model = Column(String(36), nullable=False, default='', comment='Script model')
    script_temprature = Column(DECIMAL(10,2), nullable=False,default='0.8', comment='Script Temprature')
    script_profile = Column(Text, nullable=False, comment='Script profile')
    script_media_url = Column(Text, nullable=False, comment='Script media URL')
    script_ui_type = Column(Integer, nullable=False, default=0, comment='Script UI type')
    script_ui_content = Column(Text, nullable=False, comment='Script UI content')
    script_check_prompt = Column(Text, nullable=False, comment='Script check prompt')
    script_check_flag = Column(Text, nullable=False, default='', comment='Script check flag')
    script_ui_profile = Column(Text, nullable=False, comment='Script UI profile')
    script_end_action = Column(Text, nullable=False, comment='Script end action')
    script_other_conf = Column(Text, nullable=False, comment='Other configurations of the script')
    created = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Creation time')
    updated = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now(), comment='Update time')
    status = Column(Integer, nullable=False, default=0, comment='Status of the script')
