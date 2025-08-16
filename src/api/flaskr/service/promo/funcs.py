"""
Promo functions
"""

from datetime import datetime
import random
import string

from .models import Coupon, CouponUsage as CouponUsageModel
from ...dao import db
from .consts import (
    COUPON_APPLY_TYPE_SPECIFIC,
    COUPON_APPLY_TYPE_ALL,
    COUPON_STATUS_ACTIVE,
    COUPON_STATUS_USED,
)
from flask import Flask
from ...util import generate_id
from ..common import raise_error


def generate_coupon_strcode(app: Flask):
    with app.app_context():
        characters = string.ascii_uppercase + string.digits
        discount_code = "".join(random.choices(characters, k=12))
        return discount_code


def generate_coupon_code(
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
    """
    Generate coupon code
    Args:
        app: Flask app
        user_id: User id
        discount_value: Discount value
        discount_filter: Discount filter
        discount_start: Discount start time
        discount_end: Discount end time
        discount_channel: Discount channel
        discount_type: Discount type
        discount_apply_type: Discount apply type
        discount_count: Discount count
        discount_code: Discount code
        discount_id: Discount id
        args: Additional arguments
    Returns:
        Coupon bid
    Raises:
        raise_error: If the discount code is not found or the discount is already used
    """

    app.logger.info("discount_id:" + str(discount_id))
    app.logger.info("generate_discount_code:" + str(args))
    with app.app_context():
        start = datetime.strptime(discount_start, "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(discount_end, "%Y-%m-%d %H:%M:%S")
        if end < start:
            raise_error("COMMON.START_TIME_NOT_ALLOWED")
        if discount_code is None:
            discount_code = generate_coupon_strcode(app)
        if discount_id is None or discount_id == "":
            coupon = Coupon()
            coupon.coupon_bid = generate_id(app)
        else:
            coupon = Coupon.query.filter(Coupon.coupon_bid == discount_id).first()
        coupon.code = discount_code
        coupon.discount_type = discount_type
        coupon.usage_type = discount_apply_type
        coupon.value = discount_value
        coupon.total_count = discount_count
        coupon.start = start
        coupon.end = end
        coupon.channel = discount_channel
        coupon.filter = "{" + '"course_id":"' + discount_filter + '"' + "}"
        coupon.created_user_bid = user_id
        if discount_id is None or discount_id == "":
            if discount_count <= 0:
                raise_error("DISCOUNT.DISCOUNT_COUNT_NOT_ZERO")
            db.session.add(coupon)
        else:
            db.session.merge(coupon)
        if (discount_id is None or discount_id == "") and str(
            discount_apply_type
        ) == str(COUPON_APPLY_TYPE_SPECIFIC):
            for i in range(discount_count):
                app.logger.info("generate_discount_code_by_rule")
                record = CouponUsageModel()
                record.coupon_usage_bid = generate_id(app)
                record.coupon_bid = coupon.coupon_bid
                code = generate_coupon_strcode(app)
                while CouponUsageModel.query.filter(
                    CouponUsageModel.code == code
                ).first():
                    code = generate_coupon_strcode(app)
                record.code = code
                record.discount_type = coupon.discount_type
                record.value = coupon.value
                record.status = COUPON_STATUS_ACTIVE
                db.session.add(record)
        db.session.commit()
        return coupon.coupon_bid


def generate_coupon_code_by_rule(app: Flask, discount_id):
    """
    Generate coupon code by rule
    Args:
        app: Flask app
        discount_id: Discount id
    Returns:
        Coupon usage bid
    """
    with app.app_context():
        discount_info: Coupon = Coupon.query.filter(
            Coupon.coupon_bid == discount_id
        ).first()
        if not discount_info:
            return None
        if discount_info.usage_type == COUPON_APPLY_TYPE_ALL:
            return None
        discount_code = generate_coupon_strcode(app)
        discountRecord: CouponUsageModel = CouponUsageModel()
        discountRecord.coupon_usage_bid = generate_id(app)
        discountRecord.coupon_bid = discount_info.coupon_bid
        discountRecord.code = discount_code
        discountRecord.discount_type = discount_info.discount_type
        discountRecord.value = discount_info.value
        discountRecord.status = COUPON_STATUS_ACTIVE
        discount_info.total_count = discount_info.total_count + 1
        db.session.add(discountRecord)
        db.session.commit()


def timeout_coupon_code_rollback(app: Flask, user_id, order_id):
    """
    Timeout coupon code rollback
    Args:
        app: Flask app
        user_id: User id
        order_id: Order id
    """
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
