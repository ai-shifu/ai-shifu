from sqlalchemy import Column, String, Integer, TIMESTAMP, Text, Numeric, text, ForeignKey
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from ...dao import db
from .consts import *

### AI Course
### Todo
### 加入购买渠道
class AICourseBuyRecord(db.Model):
    __tablename__ = 'ai_course_buy_record'

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment='Unique ID')
    record_id = Column(String(36), nullable=False, default='', comment='Record UUID')
    course_id = Column(String(36), nullable=False, default='', comment='Course UUID')
    user_id = Column(String(36), nullable=False, default='', comment='User UUID')
    price = Column(Numeric(10, 2), nullable=False, default='0.00', comment='Price of the course')
    created = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Creation time')
    updated = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now(), comment='Update time')
    status = Column(Integer, nullable=False, default=0, comment='Status of the record')






class AICourseLessonAttend(db.Model):
    __tablename__ = 'ai_course_lesson_attend'

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment='Unique ID')
    attend_id = Column(String(36), nullable=False, default='', comment='Attend UUID')
    lesson_id = Column(String(36), nullable=False, default='', comment='Lesson UUID')
    course_id = Column(String(36), nullable=False, default='', comment='Course UUID')
    user_id = Column(String(36), nullable=False, default='', comment='User UUID')
    status = Column(Integer, nullable=False, default=0, comment='Status of the attend: 0-not started, 1-in progress, 2-completed')
    script_index = Column(Integer, nullable=False, default=0, comment='Status of the attend: 0-not started, 1-in progress, 2-completed')
    created = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Creation time')
    updated = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now(), comment='Update time')


