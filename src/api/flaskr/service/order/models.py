import dis
from numpy import record
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
    pay_value = Column(Numeric(10, 2), nullable=False, default='0.00', comment='Payment value')
    discount_value = Column(Numeric(10, 2), nullable=False, default='0.00', comment='Discount value')
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




class PingxxOrder(db.Model):
    __tablename__ = 'pingxx_order'
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment='Unique ID')
    order_id = Column(String(36), index=True, nullable=False, default='', comment='Order UUID')
    user_id = Column(String(36), index=True,nullable=False, default='', comment='User UUID')
    course_id = Column(String(36),index=True, nullable=False, default='', comment='Course UUID')
    record_id = Column(String(36),index=True, nullable=False, default='', comment='Record UUID')
    pingxx_transaction_no = Column(String(36),index=True, nullable=False, default='', comment='Pingxx transaction number')
    pingxx_app_id = Column(String(36),index=True, nullable=False, default='', comment='Pingxx app ID')
    pingxx_channel = Column(String(36), nullable=False, default='', comment='Payment channel')
    pingxx_id = Column(String(36), nullable=False, default='', comment='Pingxx ID')
    channel = Column(String(36), nullable=False, default='', comment='Payment channel')
    amount = Column(BIGINT, nullable=False, default='0.00', comment='Payment amount')
    extra = Column(Text, nullable=False, comment='Extra information')
    currency = Column(String(36), nullable=False, default='CNY', comment='Currency')
    subject = Column(String(255), nullable=False, default='', comment='Payment subject')
    body = Column(String(255), nullable=False, default='', comment='Payment body')
    order_no = Column(String(255), nullable=False, default='', comment='Order number')
    client_ip = Column(String(255), nullable=False, default='', comment='Client IP')
    extra = Column(Text, nullable=False, comment='Extra information')
    created = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Creation time')
    updated = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now(), comment='Update time')
    status = Column(Integer, nullable=False, default=0, comment='Status of the order: 0-unpaid, 1-paid, 2-refunded, 3-closed, 4-failed')
    charge_id = Column(String(255), nullable=False, default='', comment='Charge ID')
    paid_at = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Payment time')
    refunded_at = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Refund time')
    closed_at = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Close time')
    failed_at = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Failed time')
    refund_id = Column(String(255), nullable=False, default='', comment='Refund ID')
    failure_code = Column(String(255), nullable=False, default='', comment='Failure code')
    failure_msg = Column(String(255), nullable=False, default='', comment='Failure message')
    charge_object = Column(Text, nullable=False, comment='Charge object')


# 折扣码
class Discount(db.Model):
    __tablename__ = 'discount'
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment='Unique ID')
    discount_id = Column(String(36), index=True, nullable=False, default='', comment='Discount UUID')
    discount_code = Column(String(36), index=True, nullable=False, default='', comment='Discount code')
    discount_type = Column(Integer, nullable=False, default=0, comment='Discount type: 701-fixed, 702-percent')
    discount_apply_type = Column(Integer, nullable=False, default=0, comment='Discount apply type: 801-all, 802-specific')
    discount_value = Column(Numeric(10, 2), nullable=False, default='0.00', comment='Discount value')
    discount_limit = Column(Numeric(10, 2), nullable=False, default='0.00', comment='Discount limit')
    discount_start = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Discount start time')
    discount_end = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Discount end time')
    discount_channel = Column(String(36), nullable=False, default='', comment='Discount channel')
    discount_filter = Column(Text, nullable=False, comment='Discount filter')
    discount_count = Column(BIGINT, nullable=False, default=0, comment='Discount count')
    discount_used = Column(BIGINT, nullable=False, default=0, comment='Discount used')
    discount_generated_user = Column(String(36), nullable=False, default="", comment='Discount generated user')
    created = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Creation time')
    updated = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now(), comment='Update time')
    status = Column(Integer, nullable=False, default=0, comment='Status of the discount: 0-inactive, 1-active')


class DiscountRecord(db.Model):
    __tablename__ = 'discount_record'
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment='Unique ID')
    record_id = Column(String(36), index=True, nullable=False, default='', comment='Record UUID')
    discount_id = Column(String(36), index=True, nullable=False, default='', comment='Discount UUID')
    user_id = Column(String(36), index=True, nullable=False, default='', comment='User UUID')
    course_id = Column(String(36), index=True, nullable=False, default='', comment='Course UUID')
    order_id = Column(String(36), index=True, nullable=False, default='', comment='Order UUID')
    discount_code = Column(String(36), nullable=False, default='', comment='Discount code')
    discount_type = Column(Integer, nullable=False, default=0, comment='Discount type: 0-percent, 1-amount')
    discount_value = Column(Numeric(10, 2), nullable=False, default='0.00', comment='Discount value')
    status = Column(Integer, nullable=False, default=0, comment='Status of the record: 0-inactive, 1-active')
    created = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Creation time')
    updated = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now(), comment='Update time')



