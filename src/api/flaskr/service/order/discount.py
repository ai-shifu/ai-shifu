# 优惠券&折扣码的逻辑


# 支持一码多用
# 支持一码一用，批量生成


from datetime import datetime
import random
import string
import pytz
import json
from ...api.doc.feishu import send_notify
from ...service.order.funs import (
    query_buy_record,
    success_buy_record,
)

from .models import AICourseBuyRecord, Discount, DiscountRecord
from ...dao import db
from .consts import (
    DISCOUNT_APPLY_TYPE_SPECIFIC,
    DISCOUNT_APPLY_TYPE_ALL,
    DISCOUNT_STATUS_ACTIVE,
    DISCOUNT_TYPE_FIXED,
    DISCOUNT_TYPE_PERCENT,
    DISCOUNT_STATUS_USED,
)
from flask import Flask
from ...util import generate_id
from ..common import raise_error
from ..user.models import User, UserConversion


# generate discount code
def generate_discount_strcode(app: Flask):
    with app.app_context():
        characters = string.ascii_uppercase + string.digits
        discount_code = "".join(random.choices(characters, k=12))
        return discount_code


def generate_discount_code(
    app: Flask,
    user_id,
    discount_value,
    discount_filter,
    discount_start,
    discount_end,
    discount_channel,
    discount_type,
    discount_apply_type,
    discount_count=100,
    discount_code=None,
    discount_id=None,
    **args
):

    app.logger.info("discount_id:" + str(discount_id))
    app.logger.info("generate_discount_code:" + str(args))
    with app.app_context():
        discount_start_time = datetime.strptime(discount_start, "%Y-%m-%d %H:%M:%S")
        discount_end_time = datetime.strptime(discount_end, "%Y-%m-%d %H:%M:%S")
        if discount_end_time < discount_start_time:
            raise_error("COMMON.START_TIME_NOT_ALLOWED")
        if discount_code is None:
            discount_code = generate_discount_strcode(app)
        if discount_id is None or discount_id == "":
            discount = Discount()
            discount.discount_id = generate_id(app)
        else:
            discount = Discount.query.filter(
                Discount.discount_id == discount_id
            ).first()
        discount.discount_code = discount_code
        discount.discount_type = discount_type
        discount.discount_apply_type = discount_apply_type
        discount.discount_value = discount_value
        discount.discount_count = discount_count
        discount.discount_start = discount_start
        discount.discount_end = discount_end
        discount.discount_channel = discount_channel
        discount.discount_filter = "{" + '"course_id":"' + discount_filter + '"' + "}"
        if discount_id is None or discount_id == "":
            if discount_count <= 0:
                raise_error("DISCOUNT.DISCOUNT_COUNT_NOT_ZERO")
            db.session.add(discount)
        else:
            db.session.merge(discount)
        if (discount_id is None or discount_id == "") and str(
            discount_apply_type
        ) == str(DISCOUNT_APPLY_TYPE_SPECIFIC):
            for i in range(discount_count):
                app.logger.info("generate_discount_code_by_rule")
                record = DiscountRecord()
                record.record_id = generate_id(app)
                record.discount_id = discount.discount_id
                discount_code = generate_discount_strcode(app)
                while DiscountRecord.query.filter(
                    DiscountRecord.discount_code == discount_code
                ).first():
                    discount_code = generate_discount_strcode(app)
                record.discount_code = discount_code
                record.discount_type = discount.discount_type
                record.discount_value = discount.discount_value
                record.status = DISCOUNT_STATUS_ACTIVE
                db.session.add(record)
        db.session.commit()
        return discount.discount_id


# generate discount code by rule
def generate_discount_code_by_rule(app: Flask, discount_id):
    with app.app_context():
        discount_info = Discount.query.filter(
            Discount.discount_id == discount_id
        ).first()
        if not discount_info:
            return None
        if discount_info.discount_apply_type == DISCOUNT_APPLY_TYPE_ALL:
            return None
        discount_code = generate_discount_strcode(app)
        discountRecord = DiscountRecord()
        discountRecord.record_id = generate_id(app)
        discountRecord.discount_id = discount_id
        discountRecord.discount_code = discount_code
        discountRecord.discount_type = discount_info.discount_type
        discountRecord.discount_value = discount_info.discount_value
        discountRecord.status = DISCOUNT_STATUS_ACTIVE
        discount_info.discount_count = discount_info.discount_count + 1
        db.session.add(discountRecord)
        db.session.commit()


def send_feishu_discount_code(
    app: Flask, user_id, discount_code, discount_name, discount_value
):
    with app.app_context():
        user_info = User.query.filter(User.user_id == user_id).first()
        title = "优惠码通知"
        msgs = []
        msgs.append("手机号：{}".format(user_info.mobile))
        msgs.append("昵称：{}".format(user_info.name))
        msgs.append("优惠码：{}".format(discount_code))
        msgs.append("优惠名称：{}".format(discount_name))
        msgs.append("优惠额度：{}".format(discount_value))
        user_convertion = UserConversion.query.filter(
            UserConversion.user_id == user_id
        ).first()
        channel = ""
        if user_convertion:
            channel = user_convertion.conversion_source
        msgs.append("渠道：{}".format(channel))
        send_notify(app, title, msgs)

def timeout_discount_code_rollback(app: Flask, user_id,  order_id):
    with app.app_context():
        discount = DiscountRecord.query.filter(
            DiscountRecord.user_id == user_id,
            DiscountRecord.order_id == order_id,
            DiscountRecord.status == DISCOUNT_STATUS_USED,
        ).first()
        if not discount:
            return
        discount.status = DISCOUNT_STATUS_ACTIVE
        db.session.commit()


# use discount code
def use_discount_code(app: Flask, user_id, discount_code, order_id):
    with app.app_context():
        bj_time = pytz.timezone("Asia/Shanghai")
        now = datetime.fromtimestamp(datetime.now().timestamp(), bj_time)
        buy_record = AICourseBuyRecord.query.filter(
            AICourseBuyRecord.record_id == order_id
        ).first()
        if not buy_record:
            raise_error("ORDER.ORDER_NOT_FOUND")
        order_discount = DiscountRecord.query.filter(
            DiscountRecord.order_id == order_id,
            DiscountRecord.status == DISCOUNT_STATUS_USED,
        ).first()
        if order_discount:
            raise_error("DISCOUNT.ORDER_DISCOUNT_ALREADY_USED")
        if order_discount:
            return order_discount
        discountRecord = DiscountRecord.query.filter(
            DiscountRecord.discount_code == discount_code,
            DiscountRecord.status == DISCOUNT_STATUS_ACTIVE,
        ).first()
        discount = None
        if not discountRecord:
            # query fixcode
            discount = Discount.query.filter(
                Discount.discount_code == discount_code
            ).first()
            if not discount:
                raise_error("DISCOUNT.DISCOUNT_NOT_FOUND")
            discountRecord = DiscountRecord()
            discountRecord.record_id = generate_id(app)
            discountRecord.discount_id = discount.discount_id
            discountRecord.discount_code = discount_code
            discountRecord.discount_type = discount.discount_type
            discountRecord.discount_value = discount.discount_value
            discountRecord.status = DISCOUNT_STATUS_ACTIVE
            discountRecord.created = now
            discountRecord.updated = now
            db.session.add(discountRecord)
        if discount is None:
            discount = Discount.query.filter(
                Discount.discount_id == discountRecord.discount_id
            ).first()
        if not discount:
            raise_error("DISCOUNT.DISCOUNT_NOT_FOUND")
        if discountRecord.status != DISCOUNT_STATUS_ACTIVE:
            raise_error("DISCOUNT.DISCOUNT_ALREADY_USED")
        discount_start = bj_time.localize(discount.discount_start)
        discount_end = bj_time.localize(discount.discount_end)
        if discount_start > now:
            raise_error("DISCOUNT.DISCOUNT_NOT_START")
        if discount_end < now:
            raise_error("DISCOUNT.DISCOUNT_ALREADY_EXPIRED")
        if discount.discount_used + 1 > discount.discount_count:
            raise_error("DISCOUNT.DISCOUNT_LIMIT_EXCEEDED")

        if discount.discount_filter:
            try:
                discount_filter = json.loads(discount.discount_filter)
            except json.JSONDecodeError:
                discount_filter = {}
            if "course_id" in discount_filter:
                course_id = discount_filter["course_id"]
                if course_id and course_id != "" and course_id != buy_record.course_id:
                    raise_error("DISCOUNT.DISCOUNT_NOT_APPLY")

        discountRecord.status = DISCOUNT_STATUS_USED
        discountRecord.updated = now
        discountRecord.user_id = user_id
        discountRecord.order_id = order_id
        if discount.discount_type == DISCOUNT_TYPE_FIXED:
            buy_record.discount_value = (
                buy_record.discount_value + discountRecord.discount_value  # noqa W503
            )
        elif discount.discount_type == DISCOUNT_TYPE_PERCENT:
            buy_record.discount_value = (
                buy_record.discodunt_value
                + buy_record.price * discountRecord.discount_value  # noqa W503
            )
        if buy_record.discount_value >= buy_record.price:
            buy_record.discount_value = buy_record.price
        buy_record.pay_value = buy_record.price - buy_record.discount_value
        if buy_record.pay_value < 0:
            buy_record.pay_value = 0
        buy_record.updated = now
        discountRecord.updated = now
        discount.discount_used = discount.discount_used + 1
        db.session.commit()

        if buy_record.discount_value >= buy_record.price:
            return success_buy_record(app, buy_record.record_id)
        else:
            send_feishu_discount_code(
                app,
                user_id,
                discount_code,
                discount.discount_channel,
                discount.discount_value,
            )
        return query_buy_record(app, buy_record.record_id)
