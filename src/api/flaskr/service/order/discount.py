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

from .models import Order, Coupon, CouponUsage as CouponUsageModel
from ...dao import db
from .consts import (
    COUPON_APPLY_TYPE_SPECIFIC,
    COUPON_APPLY_TYPE_ALL,
    COUPON_STATUS_ACTIVE,
    COUPON_TYPE_FIXED,
    COUPON_TYPE_PERCENT,
    COUPON_STATUS_USED,
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
            discount = Coupon()
            discount.coupon_bid = generate_id(app)
        else:
            discount = Coupon.query.filter(Coupon.coupon_bid == discount_id).first()
        discount.coupon_code = discount_code
        discount.coupon_type = discount_type
        discount.coupon_apply_type = discount_apply_type
        discount.coupon_value = discount_value
        discount.coupon_total_count = discount_count
        discount.coupon_start = discount_start
        discount.coupon_end = discount_end
        discount.coupon_channel = discount_channel
        discount.coupon_filter = "{" + '"course_id":"' + discount_filter + '"' + "}"
        if discount_id is None or discount_id == "":
            if discount_count <= 0:
                raise_error("DISCOUNT.DISCOUNT_COUNT_NOT_ZERO")
            db.session.add(discount)
        else:
            db.session.merge(discount)
        if (discount_id is None or discount_id == "") and str(
            discount_apply_type
        ) == str(COUPON_APPLY_TYPE_SPECIFIC):
            for i in range(discount_count):
                app.logger.info("generate_discount_code_by_rule")
                record = CouponUsageModel()
                record.coupon_usage_bid = generate_id(app)
                record.coupon_bid = discount.coupon_bid
                discount_code = generate_discount_strcode(app)
                while CouponUsageModel.query.filter(
                    CouponUsageModel.coupon_code == discount_code
                ).first():
                    discount_code = generate_discount_strcode(app)
                record.coupon_code = discount_code
                record.coupon_type = discount.coupon_type
                record.coupon_value = discount.coupon_value
                record.status = COUPON_STATUS_ACTIVE
                db.session.add(record)
        db.session.commit()
        return discount.coupon_bid


# generate discount code by rule
def generate_discount_code_by_rule(app: Flask, discount_id):
    with app.app_context():
        discount_info: Coupon = Coupon.query.filter(
            Coupon.coupon_bid == discount_id
        ).first()
        if not discount_info:
            return None
        if discount_info.coupon_apply_type == COUPON_APPLY_TYPE_ALL:
            return None
        discount_code = generate_discount_strcode(app)
        discountRecord: CouponUsageModel = CouponUsageModel()
        discountRecord.coupon_usage_bid = generate_id(app)
        discountRecord.coupon_bid = discount_id
        discountRecord.coupon_code = discount_code
        discountRecord.coupon_type = discount_info.coupon_type
        discountRecord.coupon_value = discount_info.coupon_value
        discountRecord.status = COUPON_STATUS_ACTIVE
        discount_info.coupon_total_count = discount_info.coupon_total_count + 1
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


def timeout_discount_code_rollback(app: Flask, user_id, order_id):
    with app.app_context():
        discount = CouponUsageModel.query.filter(
            CouponUsageModel.user_bid == user_id,
            CouponUsageModel.order_bid == order_id,
            CouponUsageModel.status == COUPON_STATUS_USED,
        ).first()
        if not discount:
            return
        discount.status = COUPON_STATUS_ACTIVE
        db.session.commit()


# use discount code
def use_discount_code(app: Flask, user_id, discount_code, order_id):
    with app.app_context():
        bj_time = pytz.timezone("Asia/Shanghai")
        now = datetime.fromtimestamp(datetime.now().timestamp(), bj_time)
        buy_record: Order = Order.query.filter(Order.order_bid == order_id).first()
        if not buy_record:
            raise_error("ORDER.ORDER_NOT_FOUND")
        order_discount = CouponUsageModel.query.filter(
            CouponUsageModel.order_bid == order_id,
            CouponUsageModel.status == COUPON_STATUS_USED,
        ).first()
        if order_discount:
            raise_error("DISCOUNT.ORDER_DISCOUNT_ALREADY_USED")
        if order_discount:
            return order_discount

        userDiscountRecord = CouponUsageModel.query.filter(
            CouponUsageModel.coupon_code == discount_code,
            CouponUsageModel.status == COUPON_STATUS_ACTIVE,
            CouponUsageModel.user_bid == user_id,
        ).first()

        discountRecord = None
        discount = None
        if userDiscountRecord:
            discountRecord = userDiscountRecord
        else:
            discountRecord = (
                CouponUsageModel.query.filter(
                    CouponUsageModel.coupon_code == discount_code,
                    CouponUsageModel.status == COUPON_STATUS_ACTIVE,
                )
                .order_by(CouponUsageModel.id.desc())
                .first()
            )

        if not discountRecord:
            # query fixcode
            discount: Coupon = (
                Coupon.query.filter(Coupon.coupon_code == discount_code)
                .order_by(Coupon.id.desc())
                .first()
            )
            if not discount:
                raise_error("DISCOUNT.DISCOUNT_NOT_FOUND")
            discountRecord = CouponUsageModel()
            discountRecord.coupon_usage_bid = generate_id(app)
            discountRecord.coupon_bid = discount.coupon_bid
            discountRecord.coupon_code = discount_code
            discountRecord.coupon_type = discount.coupon_type
            discountRecord.coupon_value = discount.coupon_value
            discountRecord.status = COUPON_STATUS_ACTIVE
            discountRecord.created_at = now
            discountRecord.updated_at = now
            db.session.add(discountRecord)
        if discount is None:
            discount = Coupon.query.filter(
                Coupon.coupon_bid == discountRecord.coupon_bid
            ).first()
        if not discount:
            raise_error("DISCOUNT.DISCOUNT_NOT_FOUND")
        if discountRecord.status != COUPON_STATUS_ACTIVE:
            raise_error("DISCOUNT.DISCOUNT_ALREADY_USED")
        discount_start = bj_time.localize(discount.coupon_start)
        discount_end = bj_time.localize(discount.coupon_end)
        if discount_start > now:
            raise_error("DISCOUNT.DISCOUNT_NOT_START")
        if discount_end < now:
            app.logger.info(
                "discount_end < now:{} {} {}".format(
                    discount_end, now, discount_end < now
                )
            )
            raise_error("DISCOUNT.DISCOUNT_ALREADY_EXPIRED")
        if discount.coupon_used_count + 1 > discount.coupon_total_count:
            raise_error("DISCOUNT.DISCOUNT_LIMIT_EXCEEDED")

        if discount.coupon_filter:
            try:
                discount_filter = json.loads(discount.coupon_filter)
            except json.JSONDecodeError:
                discount_filter = {}
            if "course_id" in discount_filter:
                course_id = discount_filter["course_id"]
                if course_id and course_id != "" and course_id != buy_record.shifu_bid:
                    raise_error("DISCOUNT.DISCOUNT_NOT_APPLY")

        discountRecord.status = COUPON_STATUS_USED
        discountRecord.updated_at = now
        discountRecord.user_bid = user_id
        discountRecord.order_bid = order_id
        if discount.coupon_type == COUPON_TYPE_FIXED:
            buy_record.payable_price = (
                buy_record.payable_price + discountRecord.coupon_value  # noqa W503
            )
        elif discount.coupon_type == COUPON_TYPE_PERCENT:
            buy_record.payable_price = (
                buy_record.payable_price
                + buy_record.payable_price * discountRecord.coupon_value  # noqa W503
            )
        if buy_record.payable_price >= buy_record.payable_price:
            buy_record.payable_price = buy_record.payable_price
        buy_record.paid_price = buy_record.payable_price - buy_record.payable_price
        if buy_record.paid_price < 0:
            buy_record.paid_price = 0
        buy_record.updated_at = now
        discountRecord.updated_at = now
        if not userDiscountRecord:
            discount.coupon_used_count = discount.coupon_used_count + 1
        db.session.commit()

        if buy_record.payable_price >= buy_record.payable_price:
            return success_buy_record(app, buy_record.order_bid)
        else:
            send_feishu_discount_code(
                app,
                user_id,
                discount_code,
                discount.coupon_name,
                discount.coupon_value,
            )
        return query_buy_record(app, buy_record.order_bid)
