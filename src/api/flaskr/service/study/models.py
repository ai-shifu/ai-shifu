from sqlalchemy import Column, String, Integer, TIMESTAMP, Text, Numeric, text, ForeignKey
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from ...dao import db

class AICourseLessonAttendScript(db.Model):
    __tablename__ = 'ai_course_lesson_attendscript'

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment='Unique ID')
    attend_id = Column(String(36), nullable=False, default='', comment='Attend UUID')
    script_id = Column(String(36), nullable=False, default='', comment='Script UUID')
    lesson_id = Column(String(36), nullable=False, default='', comment='Lesson UUID')
    course_id = Column(String(36),  nullable=False, default='', comment='Course UUID')
    user_id = Column(String(36), nullable=False, default='', comment='User UUID')
    script_index = Column(Integer, nullable=False, default=0, comment='Script index')
    script_role = Column(Integer, nullable=False, default=0, comment='Script role')
    script_content = Column(Text, nullable=False, comment='Script content') 
    status = Column(Integer, nullable=False, default=0, comment='Status of the attend')
    created = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Creation time')
    updated = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now(), comment='Update time')



class AICourseAttendAsssotion(db.Model):
    __tablename__ = 'ai_course_lesson_attend_association'
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment='Unique ID')
    association_id = Column(String(36), nullable=False, default='', comment='Attend UUID')
    from_attend_id = Column(String(36), nullable=False, default='', comment='Attend UUID')
    to_attend_id = Column(String(36), nullable=False, default='', comment='Attend UUID')
    user_id = Column(String(36), nullable=False, default='', comment='Attend UUID')
    association_status = Column(Integer, nullable=False, default=0, comment='Status of the attend: 0-not started, 1-in progress, 2-completed')
    created = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Creation time')
    updated = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now(), comment='Update time')
  



