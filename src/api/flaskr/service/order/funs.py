from calendar import c
import decimal
import json
from typing import List

from numpy import char
from sympy import product

from flaskr.common.swagger import register_schema_to_swagger
from .models import *
from flask import Flask
from ...dao import db
from ..lesson.models import AICourse, AILesson
from .models import AICourseLessonAttend
from ...util.uuid import generate_id as get_uuid
from ..lesson.const import *
from .pingxx_order import create_pingxx_order

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
    order_id:str
    user_id:str
    course_id:str
    price:str
    status:int

    def __init__(self, record_id, user_id, course_id, price, status):
        self.order_id = record_id
        self.user_id = user_id
        self.course_id = course_id
        self.price = str(price)
        self.status = status

    def __json__(self):
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "course_id": self.course_id,
            "price": str(self.price),
            "status":  self.status
        }

def init_buy_record(app: Flask,user_id:str,course_id:str):
    with app.app_context():
        course_info = AICourse.query.filter(AICourse.course_id==course_id).first()
        if not course_info:
            app.logger.error('course:{} not found'.format(course_id))
            return None
        origin_record = AICourseBuyRecord.query.filter(AICourseBuyRecord.user_id==user_id,AICourseBuyRecord.course_id==course_id,AICourseBuyRecord.status == BUY_STATUS_INIT).first()
        if origin_record:
            return AICourseBuyRecordDTO(origin_record.record_id,origin_record.user_id,origin_record.course_id,origin_record.price,origin_record.status)
        buy_record = AICourseBuyRecord()
        buy_record.user_id = user_id
        buy_record.course_id = course_id
        buy_record.price =  course_info.course_price
        buy_record.status = BUY_STATUS_INIT
        buy_record.record_id = str(get_uuid(app))
        db.session.add(buy_record)
        db.session.commit()
        return AICourseBuyRecordDTO(buy_record.record_id,buy_record.user_id,buy_record.course_id,buy_record.price,buy_record.status)




@register_schema_to_swagger
class BuyRecordDTO:
    order_id:str # 订单id
    user_id:str # 用户id
    price:str # 价格
    channel :str # 支付渠道
    qr_url :str # 二维码地址
    def __init__(self, record_id, user_id, price,channel,qr_url):
        self.order_id = record_id
        self.user_id = user_id
        self.price = price
        self.channel = channel
        self.qr_url = qr_url
    def __json__(self):
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "price": str(self.price),
            "channel": self.channel,
            "qr_url": self.qr_url
        }

def generate_charge(app: Flask,record_id:str,channel:str,client_ip:str)->BuyRecordDTO:
    with app.app_context():
        app.logger.info('generate charge for record:{} channel:{}'.format(record_id,channel))
        buy_record = AICourseBuyRecord.query.filter(AICourseBuyRecord.record_id==record_id).first()
        course = AICourse.query.filter(AICourse.course_id==buy_record.course_id).first()
        if buy_record:
            app.logger.info('buy record found:{}'.format(buy_record))
            if buy_record.status != BUY_STATUS_INIT:
                app.logger.error('buy record:{} status is not init'.format(record_id))
                return None
            if not course:
                app.logger.error('course:{} not found'.format(buy_record.course_id))
                return None
            amount = int(buy_record.price*100)

            product_id = course.course_id
            subject = course.course_name
            body = course.course_name
            order_no = str(get_uuid(app))
            qr_url = None
            pingpp_id = app.config.get('PINGPP_APP_ID')
            if channel == 'wx_pub_qr':
                extra = dict({"product_id":product_id})
                charge =  create_pingxx_order(app, order_no, pingpp_id, channel, amount, client_ip, subject, body, extra)
                quit_url = charge['credential']['wx_pub_qr']
            elif channel == 'alipay_qr':
                extra = dict({})
                charge =  create_pingxx_order(app, order_no, pingpp_id, channel, amount, client_ip, subject, body, extra)
                qr_url = charge['credential']['alipay_qr']
            else:
                app.logger.error('channel:{} not support'.format(channel))
                return None
            app.logger.info('charge created:{}'.format(charge))

            pingxxOrder = PingxxOrder()
            pingxxOrder.order_id = order_no
            pingxxOrder.user_id = buy_record.user_id
            pingxxOrder.course_id = buy_record.course_id
            pingxxOrder.record_id = buy_record.record_id
            pingxxOrder.pingxx_transaction_no = charge['transaction_no']
            pingxxOrder.pingxx_app_id = charge['app']
            pingxxOrder.pingxx_channel = charge['channel']
            pingxxOrder.pingxx_id = charge['id']
            pingxxOrder.channel = charge['channel']
            pingxxOrder.amount = amount
            pingxxOrder.currency = charge['currency']
            pingxxOrder.subject = charge['subject']
            pingxxOrder.body = charge['body']
            pingxxOrder.order_no = charge['order_no']
            pingxxOrder.client_ip = charge['client_ip']
            pingxxOrder.extra = str(charge['extra'])
            pingxxOrder.charge_id = charge['id']
            pingxxOrder.status = 0
            pingxxOrder.charge_object = str(charge)
            db.session.add(pingxxOrder)
            db.session.commit()
            return BuyRecordDTO(buy_record.record_id,buy_record.user_id,buy_record.price,channel,qr_url)



def success_buy_record_from_pingxx(app: Flask,charge_id:str):
    with app.app_context():
        app.logger.info('success buy record from pingxx charge:"{}"'.format(charge_id))
        pingxx_order = PingxxOrder.query.filter(PingxxOrder.charge_id==charge_id).first()
        if pingxx_order:
            buy_record = AICourseBuyRecord.query.filter(AICourseBuyRecord.record_id==pingxx_order.record_id).first()
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
                db.session.commit()
                return AICourseBuyRecordDTO(buy_record.record_id,buy_record.user_id,buy_record.course_id,buy_record.price,buy_record.status)
            else:
                app.logger.error('record:{} not found'.format(pingxx_order.record_id))
        else:
            app.logger.error('charge:{} not found'.format(charge_id))
        return None


        
            
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



def query_buy_record(app: Flask,record_id:str)->AICourseBuyRecordDTO:
    with app.app_context():
        app.logger.info('query buy record:"{}"'.format(record_id))
        buy_record = AICourseBuyRecord.query.filter(AICourseBuyRecord.record_id==record_id).first()
        if buy_record:
            return AICourseBuyRecordDTO(buy_record.record_id,buy_record.user_id,buy_record.course_id,buy_record.price,buy_record.status)
        else:
            app.logger.error('record:{} not found'.format(record_id))
        return None

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