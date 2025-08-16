from flask import Flask
from flaskr.service.promo.models import Coupon, CouponUsage as CouponUsageModel
from flaskr.service.order.models import Order
from flaskr.service.order.funs import success_buy_record, query_buy_record
from flaskr.service.promo.consts import (
    COUPON_STATUS_USED,
    COUPON_STATUS_ACTIVE,
    COUPON_TYPE_FIXED,
    COUPON_TYPE_PERCENT,
)
from flaskr.service.common import raise_error
from flaskr.util import generate_id
import pytz
from datetime import datetime
import json
from .feishu_funcs import send_feishu_coupon_code
from flaskr.dao import db


def use_coupon_code(app: Flask, user_id, coupon_code, order_id):
    """
    Use coupon code
    Args:
        app: Flask app
        user_id: User id
        coupon_code: Coupon code
        order_id: Order id
    Returns:
        Order object
    Raises:
        raise_error: If the coupon code is not found or the coupon is already used
    """
    with app.app_context():
        bj_time = pytz.timezone("Asia/Shanghai")
        now = datetime.fromtimestamp(datetime.now().timestamp(), bj_time)
        buy_record: Order = Order.query.filter(Order.order_bid == order_id).first()
        if not buy_record:
            raise_error("ORDER.ORDER_NOT_FOUND")
        order_coupon_useage: CouponUsageModel = CouponUsageModel.query.filter(
            CouponUsageModel.order_bid == order_id,
            CouponUsageModel.status == COUPON_STATUS_USED,
        ).first()
        if order_coupon_useage:
            raise_error("DISCOUNT.ORDER_DISCOUNT_ALREADY_USED")

        user_coupon_useage: CouponUsageModel = CouponUsageModel.query.filter(
            CouponUsageModel.code == coupon_code,
            CouponUsageModel.status == COUPON_STATUS_ACTIVE,
            CouponUsageModel.user_bid == user_id,
        ).first()

        coupon_usage: CouponUsageModel = None
        coupon: Coupon = None
        if user_coupon_useage:
            coupon_usage = user_coupon_useage
        else:
            coupon_usage = (
                CouponUsageModel.query.filter(
                    CouponUsageModel.code == coupon_code,
                    CouponUsageModel.status == COUPON_STATUS_ACTIVE,
                )
                .order_by(CouponUsageModel.id.desc())
                .first()
            )

        if not coupon_usage:
            # query fixcode
            coupon: Coupon = (
                Coupon.query.filter(Coupon.code == coupon_code)
                .order_by(Coupon.id.desc())
                .first()
            )
            if not coupon:
                raise_error("DISCOUNT.DISCOUNT_NOT_FOUND")
            coupon_usage = CouponUsageModel()
            coupon_usage.coupon_usage_bid = generate_id(app)
            coupon_usage.coupon_bid = coupon.coupon_bid
            coupon_usage.code = coupon_code
            coupon_usage.discount_type = coupon.discount_type
            coupon_usage.value = coupon.value
            coupon_usage.status = COUPON_STATUS_ACTIVE
            coupon_usage.created_at = now
            coupon_usage.updated_at = now
            db.session.add(coupon_usage)
        if coupon is None:
            coupon = Coupon.query.filter(
                Coupon.coupon_bid == coupon_usage.coupon_bid
            ).first()
        if not coupon:
            raise_error("DISCOUNT.DISCOUNT_NOT_FOUND")
        if coupon_usage.status != COUPON_STATUS_ACTIVE:
            raise_error("DISCOUNT.DISCOUNT_ALREADY_USED")
        coupon_start = bj_time.localize(coupon.start)
        coupon_end = bj_time.localize(coupon.end)
        if coupon_start > now:
            raise_error("DISCOUNT.DISCOUNT_NOT_START")
        if coupon_end < now:
            app.logger.info(
                "coupon_end < now:{} {} {}".format(coupon_end, now, coupon_end < now)
            )
            raise_error("DISCOUNT.DISCOUNT_ALREADY_EXPIRED")
        if coupon.used_count + 1 > coupon.total_count:
            raise_error("DISCOUNT.DISCOUNT_LIMIT_EXCEEDED")

        if coupon.filter:
            try:
                coupon_filter = json.loads(coupon.filter)
            except json.JSONDecodeError:
                coupon_filter = {}
            if "course_id" in coupon_filter:
                course_id = coupon_filter["course_id"]
                if course_id and course_id != "" and course_id != buy_record.shifu_bid:
                    raise_error("DISCOUNT.DISCOUNT_NOT_APPLY")

        coupon_usage.status = COUPON_STATUS_USED
        coupon_usage.updated_at = now
        coupon_usage.user_bid = user_id
        coupon_usage.order_bid = order_id
        if coupon.discount_type == COUPON_TYPE_FIXED:
            buy_record.payable_price = (
                buy_record.payable_price + coupon_usage.value  # noqa W503
            )
        elif coupon.discount_type == COUPON_TYPE_PERCENT:
            buy_record.payable_price = (
                buy_record.payable_price
                + buy_record.payable_price * coupon_usage.value  # noqa W503
            )
        if buy_record.payable_price >= buy_record.payable_price:
            buy_record.payable_price = buy_record.payable_price
        buy_record.paid_price = buy_record.payable_price - buy_record.payable_price
        if buy_record.paid_price < 0:
            buy_record.paid_price = 0
        buy_record.updated_at = now
        coupon_usage.updated_at = now
        if not user_coupon_useage:
            coupon.used_count = coupon.used_count + 1
        db.session.commit()

        if buy_record.payable_price >= buy_record.payable_price:
            return success_buy_record(app, buy_record.order_bid)
        else:
            send_feishu_coupon_code(
                app,
                user_id,
                coupon_code,
                coupon.code,
                coupon.value,
            )
        return query_buy_record(app, buy_record.order_bid)
