


# 优惠券&折扣码的逻辑



# 支持一码多用
# 支持一码一用，批量生成


from  datetime import datetime
from operator import ge
import random
import string

from ...service.order.funs import AICourseBuyRecordDTO, BuyRecordDTO, success_buy_record

from .models import AICourseBuyRecord, Discount, DiscountRecord
from ...dao import db
from .consts import * 
from flask import Flask
from ...util import generate_id 




# 生成折扣码
def generate_discount_strcode(app:Flask):
    with app.app_context():
        characters = string.ascii_uppercase + string.digits
        discount_code  = ''.join(random.choices(characters, k=12))
        return discount_code


def generate_discount_code(app:Flask , discount_value, course_id,discout_start, discount_end,discount_channel,discount_type,discount_apply_type):
    with app.app_context():
        discount_code  =generate_discount_strcode(app)
        discount = Discount()
        discount.discount_id = generate_id(app) 
        discount.course_id = course_id
        discount.discount_code = discount_code
        discount.discount_type = discount_type
        discount.discount_apply_type = discount_apply_type
        discount.discount_value = discount_value
        discount.discount_limit = 0
        discount.discount_start = discout_start
        discount.discount_end = discount_end
        discount.discount_channel = discount_channel
        discount.discount_filter = '{' + '"course_id":{}'.format(course_id) + '}'
        db.session.add(discount)
        db.session.commit()
        return discount.discount_id


# 用折扣码规则生成折扣码

def generate_discount_code_by_rule(app:Flask, discount_id):
    with app.app_context(): 
        discount_info = Discount.query.filter(Discount.discount_id == discount_id).first()
        if not discount_info:
            return None
        if discount_info.discount_apply_type == DISCOUNT_APPLY_TYPE_ALL:
            return None
        discount_code  = generate_discount_strcode(app) 
        discountRecord = DiscountRecord()
        discountRecord.record_id = generate_id(app)
        discountRecord.discount_id = discount_id
        discountRecord.discount_code = discount_code
        discountRecord.discount_type = discount_info.discount_type
        discountRecord.discount_value = discount_info.discount_value
        discountRecord.status = DISCOUNT_STATUS_ACTIVE
        discount_info .discount_count = discount_info.discount_count + 1
        db.session.add(discountRecord)
        db.session.commit()


# 使用折扣码
def use_discount_code(app:Flask, user_id, discount_code, order_id):
    with app.app_context():
        discountRecord = DiscountRecord.query.filter(DiscountRecord.discount_code == discount_code).first()
        if not discountRecord:
            app.logger.error('discount code not exists')
            return None
        if discountRecord.status == DISCOUNT_STATUS_INACTIVE:
            return None
        
        discount = Discount.query.filter(Discount.discount_id == discountRecord.discount_id).first()
        buy_record =  AICourseBuyRecord.query.filter(AICourseBuyRecord.record_id == order_id).first()
        
        if not buy_record:
            return None
        if buy_record.discount_value > 0:
             return AICourseBuyRecordDTO(buy_record.record_id,buy_record.user_id,buy_record.course_id,buy_record.price,buy_record.status,buy_record.discount_value)
        if not discount:
            return None
        if discount.status == DISCOUNT_STATUS_INACTIVE:
            app.logger.error('discount not exists')
            return None
        discountRecord.status = DISCOUNT_STATUS_USED
        discountRecord.updated = datetime.now()
        discountRecord.updated = datetime.now()
        discountRecord.user_id = user_id
        discountRecord.order_id = order_id
        if discount.discount_type == DISCOUNT_TYPE_FIXED:
            buy_record.discount_value = discountRecord.discount_value
        elif discount.discount_type == DISCOUNT_TYPE_PERCENT:
            buy_record.discount_value = buy_record.price * discountRecord.discount_value
        buy_record.updated = datetime.now()
        db.session.commit()
        if buy_record.discount_value >= buy_record.price:
            return success_buy_record(app, buy_record.record_id)

        return AICourseBuyRecordDTO(buy_record.record_id,buy_record.user_id,buy_record.course_id,buy_record.price,buy_record.status,buy_record.discount_value)