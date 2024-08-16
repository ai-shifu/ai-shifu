import decimal
from typing import List

from flaskr.common.swagger import register_schema_to_swagger
from .models import *
from flask import Flask
from ...dao import db
from ..lesson.models import AILesson
from .models import AICourseLessonAttend
from ...util.uuid import generate_id as get_uuid
from ..lesson.const import *

@register_schema_to_swagger
class AICourseLessonAttendDTO:
    attend_id:str
    lesson_id:str
    course_id:str
    user_id:str
    status:int
    index:int

    def __init__(self, attend_id, lesson_id, course_id, user_id, status,index):
        self.attend_id = attend_id
        self.lesson_id = lesson_id
        self.course_id = course_id
        self.user_id = user_id
        self.status = status
        self.index = index

    def __json__(self):
        return {
            "attend_id": self.attend_id,
            "lesson_id": self.lesson_id,
            "course_id": self.course_id,
            "user_id": self.user_id,
            "status": self.status,
            "index": self.index
        }


@register_schema_to_swagger
class AICourseBuyRecordDTO:
    record_id:str
    user_id:str
    course_id:str
    price:str
    status:int

    def __init__(self, record_id, user_id, course_id, price, status):
        self.record_id = record_id
        self.user_id = user_id
        self.course_id = course_id
        self.price = str(price)
        self.status = status

    def __json__(self):
        return {
            "record_id": self.record_id,
            "user_id": self.user_id,
            "course_id": self.course_id,
            "price": self.price,
            "status": self.status
        }

def init_buy_record(app: Flask,user_id:str,course_id:str,price:decimal.Decimal):
    with app.app_context():
        app.logger.info('init buy record for user:{} course:{} price:{}'.format(user_id,course_id,price))
        origin_record = AICourseBuyRecord.query.filter(AICourseBuyRecord.user_id==user_id,AICourseBuyRecord.course_id==course_id,AICourseBuyRecord.status == BUY_STATUS_INIT).first()
        if origin_record:
            return origin_record
        buy_record = AICourseBuyRecord()
        buy_record.user_id = user_id
        buy_record.course_id = course_id
        buy_record.price = price
        buy_record.status = BUY_STATUS_INIT
        buy_record.record_id = str(get_uuid(app))
        db.session.add(buy_record)
        db.session.commit()
        return AICourseBuyRecordDTO(buy_record.record_id,buy_record.user_id,buy_record.course_id,buy_record.price,buy_record.status)


def success_buy_record(app: Flask,record_id:str):
    with app.app_context():
        # todo: 事务处理 & 并发锁
        app.logger.info('success buy record:"{}"'.format(record_id))
        buy_record = AICourseBuyRecord.query.filter(AICourseBuyRecord.record_id==record_id).first()
        if buy_record:
            buy_record.status = BUY_STATUS_SUCCESS
            lessons = AILesson.query.filter(AILesson.course_id==buy_record.course_id,AILesson.status==1,AILesson.lesson_type != LESSON_TYPE_TRIAL).all()
            for lesson in lessons:
                app.logger.info('init lesson attend for user:{} lesson:{}'.format(buy_record.user_id,lesson.lesson_id))
                attend = AICourseLessonAttend.query.filter(AICourseLessonAttend.user_id==buy_record.user_id,AICourseLessonAttend.lesson_id==lesson.lesson_id).first()
                if attend:
                    continue
                attend = AICourseLessonAttend()
                attend.attend_id = str(get_uuid(app))
                attend.course_id = buy_record.course_id
                attend.lesson_id = lesson.lesson_id
                attend.user_id = buy_record.user_id
                if lesson.lesson_no in ['01','0101']:
                    attend.status = ATTEND_STATUS_NOT_STARTED
                else:
                    attend.status = ATTEND_STATUS_LOCKED
                db.session.add(attend)
            db.session.commit()
            return AICourseBuyRecordDTO(buy_record.record_id,buy_record.user_id,buy_record.course_id,buy_record.price,buy_record.status)
        else:
            app.logger.error('record:{} not found'.format(record_id))
        return None


def init_trial_lesson(app:Flask ,user_id:str,course_id:str)->list[AICourseLessonAttendDTO]:
    app.logger.info('init trial lesson for user:{} course:{}'.format(user_id,course_id))
    response =[]
    lessons = AILesson.query.filter(AILesson.course_id==course_id,AILesson.lesson_type == LESSON_TYPE_TRIAL,AILesson.status==1).all()
    app.logger.info('init trial lesson:{}'.format(lessons))
    for lesson in lessons:
        app.logger.info('init trial lesson:{} ,is trail:{}'.format(lesson.lesson_id,lesson.is_final()))
        attend = AICourseLessonAttend.query.filter(AICourseLessonAttend.user_id==user_id,AICourseLessonAttend.lesson_id==lesson.lesson_id).first()
        if attend :
            if lesson.is_final():
                item =AICourseLessonAttendDTO(attend.attend_id,attend.lesson_id,attend.course_id,attend.user_id,attend.status,lesson.lesson_index)
                response.append(item)
            continue
        attend = AICourseLessonAttend()
        attend.attend_id = str(get_uuid(app))
        attend.course_id = course_id
        attend.lesson_id = lesson.lesson_id
        attend.user_id = user_id
        if lesson.lesson_no in ['00','0001']:
            attend.status = ATTEND_STATUS_NOT_STARTED
        else:
            attend.status = ATTEND_STATUS_LOCKED
        
        db.session.add(attend)
        if  lesson.is_final():
            response.append(AICourseLessonAttendDTO(attend.attend_id,attend.lesson_id,attend.course_id,attend.user_id,attend.status,lesson.lesson_index))
        db.session.commit()
    return response


def fix_attend_info(app:Flask,user_id:str,course_id:str):
     with app.app_context():
        # todo: 事务处理 & 并发锁
        app.logger.info('fix attend info for user:{} course:{}'.format(user_id,course_id))
        lessons = AILesson.query.filter(AILesson.course_id==course_id,AILesson.status==1,AILesson.lesson_type != LESSON_TYPE_TRIAL).all()
        fix_lessons = []
        for lesson in lessons:
            attend = AICourseLessonAttend.query.filter(AICourseLessonAttend.user_id==user_id,AICourseLessonAttend.lesson_id==lesson.lesson_id).first()
            if attend:
                continue
            attend = AICourseLessonAttend()
            attend.attend_id = str(get_uuid(app))
            attend.course_id = course_id
            attend.lesson_id = lesson.lesson_id
            attend.user_id = user_id
            if lesson.lesson_no in ['01','0101']:
                attend.status = ATTEND_STATUS_NOT_STARTED
            else:
                attend.status = ATTEND_STATUS_LOCKED
            fix_lessons.append(AICourseLessonAttendDTO(attend.attend_id,attend.lesson_id,attend.course_id,attend.user_id,attend.status,lesson.lesson_index))
            db.session.add(attend)
        db.session.commit()
        return fix_lessons