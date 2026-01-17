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
import decimal
from typing import List, Tuple, Optional


def _get_course_id_from_filter(coupon: Coupon) -> Optional[str]:
    """Extract course_id from coupon.filter; return None if missing/invalid/empty."""
    if not coupon or not coupon.filter:
        return None
    try:
        coupon_filter = json.loads(coupon.filter)
    except json.JSONDecodeError:
        return None
    if not isinstance(coupon_filter, dict):
        return None
    course_id = coupon_filter.get("course_id")
    if course_id == "":
        return None
    return course_id


def _coupon_matches_course(coupon: Coupon, shifu_bid: str) -> bool:
    """Check whether coupon is applicable to the given course."""
    course_id = _get_course_id_from_filter(coupon)
    if not course_id:
        return True
    return course_id == shifu_bid


def _pick_coupon_candidate(
    active_usages: List[CouponUsageModel],
    coupons_by_bid: dict[str, Coupon],
    coupons_by_code: List[Coupon],
    shifu_bid: str,
    user_id: str,
) -> Tuple[Optional[CouponUsageModel], Optional[Coupon], bool]:
    """
    Pick a coupon_usage/coupon pair that matches the current course.
    Returns (usage, coupon, has_candidate_with_same_code).
    """

    has_candidate_with_same_code = bool(active_usages or coupons_by_code)

    def select(usages: List[CouponUsageModel]) -> Tuple[Optional[CouponUsageModel], Optional[Coupon]]:
        for usage in usages:
            coupon = coupons_by_bid.get(getattr(usage, "coupon_bid", None))
            if coupon and _coupon_matches_course(coupon, shifu_bid):
                return usage, coupon
        return None, None

    # 1) Prefer active usages already tied to this user (still active)
    user_usages = [u for u in active_usages if getattr(u, "user_bid", None) == user_id]
    usage, coupon = select(user_usages)
    if coupon:
        return usage, coupon, has_candidate_with_same_code

    # 2) Fallback to any active usage with matching course
    usage, coupon = select(active_usages)
    if coupon:
        return usage, coupon, has_candidate_with_same_code

    # 3) Finally, look at coupons by code (multi-use scenario without usage)
    for coupon in coupons_by_code:
        if _coupon_matches_course(coupon, shifu_bid):
            return None, coupon, has_candidate_with_same_code

    return None, None, has_candidate_with_same_code


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
            raise_error("server.order.orderNotFound")
        order_coupon_useage: CouponUsageModel = CouponUsageModel.query.filter(
            CouponUsageModel.order_bid == order_id,
            CouponUsageModel.status == COUPON_STATUS_USED,
        ).first()
        if order_coupon_useage:
            raise_error("server.discount.orderDiscountAlreadyUsed")

        active_usages: List[CouponUsageModel] = (
            CouponUsageModel.query.filter(
                CouponUsageModel.code == coupon_code,
                CouponUsageModel.status == COUPON_STATUS_ACTIVE,
            )
            .order_by(CouponUsageModel.id.desc())
            .all()
        )
        coupon_bids = {usage.coupon_bid for usage in active_usages if usage.coupon_bid}
        coupons_by_bid = {}
        if coupon_bids:
            coupons = Coupon.query.filter(Coupon.coupon_bid.in_(coupon_bids)).all()
            coupons_by_bid = {coupon.coupon_bid: coupon for coupon in coupons}
        coupons_by_code: List[Coupon] = (
            Coupon.query.filter(Coupon.code == coupon_code)
            .order_by(Coupon.id.desc())
            .all()
        )

        coupon_usage, coupon, has_same_code_candidate = _pick_coupon_candidate(
            active_usages, coupons_by_bid, coupons_by_code, buy_record.shifu_bid, user_id
        )

        if not coupon:
            if has_same_code_candidate:
                raise_error("server.discount.discountNotApply")
            raise_error("server.discount.discountNotFound")

        if coupon_usage is None:
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

        if coupon_usage.status != COUPON_STATUS_ACTIVE:
            raise_error("server.discount.discountAlreadyUsed")
        coupon_start = bj_time.localize(coupon.start)
        coupon_end = bj_time.localize(coupon.end)
        if coupon_start > now:
            raise_error("server.discount.discountNotStart")
        if coupon_end < now:
            app.logger.info(
                "coupon_end < now:{} {} {}".format(coupon_end, now, coupon_end < now)
            )
            raise_error("server.discount.discountAlreadyExpired")
        if coupon.used_count + 1 > coupon.total_count:
            raise_error("server.discount.discountLimitExceeded")

        if coupon.filter:
            try:
                coupon_filter = json.loads(coupon.filter)
            except json.JSONDecodeError:
                coupon_filter = {}
            if "course_id" in coupon_filter:
                course_id = coupon_filter["course_id"]
                if course_id and course_id != "" and course_id != buy_record.shifu_bid:
                    raise_error("server.discount.discountNotApply")

        coupon_usage.status = COUPON_STATUS_USED
        coupon_usage.updated_at = now
        user_usage_already_bound = coupon_usage.user_bid == user_id
        coupon_usage.user_bid = user_id
        coupon_usage.order_bid = order_id
        if coupon.discount_type == COUPON_TYPE_FIXED:
            buy_record.paid_price = (
                decimal.Decimal(buy_record.paid_price)
                - decimal.Decimal(coupon_usage.value)  # noqa W503
            )
        elif coupon.discount_type == COUPON_TYPE_PERCENT:
            buy_record.paid_price = (
                decimal.Decimal(buy_record.paid_price)
                - decimal.Decimal(buy_record.payable_price)
                * decimal.Decimal(coupon_usage.value)  # noqa W503
            )
        if decimal.Decimal(buy_record.paid_price) < 0:
            buy_record.paid_price = decimal.Decimal(0)
        buy_record.updated_at = now
        coupon_usage.updated_at = now
        if not user_usage_already_bound:
            coupon.used_count = coupon.used_count + 1
        db.session.commit()

        if buy_record.paid_price == 0:
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
