"""
Promo functions
"""

from datetime import datetime
import decimal
import random
import string
import json

import pytz

from .models import (
    Coupon,
    CouponUsage as CouponUsageModel,
    PromoCampaign,
    PromoRedemption,
)
from ...dao import db
from .consts import (
    COUPON_APPLY_TYPE_SPECIFIC,
    COUPON_STATUS_ACTIVE,
    COUPON_STATUS_USED,
    PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
    PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED,
    PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
    PROMO_CAMPAIGN_STATUS_ACTIVE,
)
from flask import Flask
from ...util import generate_id
from ..common import raise_error
from .consts import COUPON_TYPE_FIXED, COUPON_TYPE_PERCENT


def generate_coupon_strcode(app: Flask):
    with app.app_context():
        characters = string.ascii_uppercase + string.digits
        discount_code = "".join(random.choices(characters, k=12))
        return discount_code


def generate_coupon_code(
    app: Flask,
    user_id,
    value,
    filter,
    start,
    end,
    channel,
    discount_type,
    usage_type,
    total_count=100,
    code=None,
    coupon_bid=None,
    **args,
):
    """
    Generate coupon code
    Args:
        app: Flask app
        user_id: User id
        value: Discount value
        filter: Discount filter
        start: Discount start time
        end: Discount end time
        channel: Discount channel
        discount_type: Discount type
        usage_type: Discount apply type
        total_count: Discount count
        code: Discount code
        coupon_bid: Discount id
        args: Additional arguments
    Returns:
        Coupon bid
    Raises:
        raise_error: If the discount code is not found or the discount is already used
    """

    with app.app_context():
        start = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
        if end < start:
            raise_error("server.common.startTimeNotAllowed")
        if code is None:
            code = generate_coupon_strcode(app)
        if coupon_bid is None or coupon_bid == "":
            coupon = Coupon()
            coupon.coupon_bid = generate_id(app)
        else:
            coupon = Coupon.query.filter(Coupon.coupon_bid == coupon_bid).first()
        coupon.code = code
        coupon.discount_type = discount_type
        coupon.usage_type = usage_type
        coupon.value = value
        coupon.total_count = total_count
        coupon.start = start
        coupon.end = end
        coupon.channel = channel
        coupon.filter = json.dumps({"course_id": filter})
        coupon.created_user_bid = user_id
        if coupon_bid is None or coupon_bid == "":
            if total_count <= 0:
                raise_error("server.discount.discountCountNotZero")
            db.session.add(coupon)
        else:
            db.session.merge(coupon)
        if (coupon_bid is None or coupon_bid == "") and str(usage_type) == str(
            COUPON_APPLY_TYPE_SPECIFIC
        ):
            for i in range(total_count):
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


def timeout_coupon_code_rollback(app: Flask, user_bid, order_bid):
    """
    Timeout coupon code rollback
    Args:
        app: Flask app
        user_bid: User bid
        order_bid: Order bid
    """
    with app.app_context():
        usage = CouponUsageModel.query.filter(
            CouponUsageModel.user_bid == user_bid,
            CouponUsageModel.order_bid == order_bid,
            CouponUsageModel.status == COUPON_STATUS_USED,
        ).first()
        if not usage:
            return
        usage.status = COUPON_STATUS_ACTIVE
        db.session.commit()


def void_promo_campaign_applications(app: Flask, user_bid: str, order_bid: str) -> None:
    """Mark applied promo campaign applications as voided for an order."""
    with app.app_context():
        PromoRedemption.query.filter(
            PromoRedemption.order_bid == order_bid,
            PromoRedemption.user_bid == user_bid,
            PromoRedemption.deleted == 0,
            PromoRedemption.status == PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
        ).update(
            {PromoRedemption.status: PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED},
            synchronize_session="fetch",
        )
        db.session.commit()


def _calculate_discount_amount(
    payable_price: decimal.Decimal, discount_type: int, value: decimal.Decimal
) -> decimal.Decimal:
    if discount_type == COUPON_TYPE_FIXED:
        return decimal.Decimal(value)
    if discount_type == COUPON_TYPE_PERCENT:
        return (
            decimal.Decimal(value)
            * decimal.Decimal(payable_price)
            / decimal.Decimal(100)
        )
    return decimal.Decimal("0.00")


def apply_promo_campaigns(
    app: Flask,
    shifu_bid: str,
    user_bid: str,
    order_bid: str,
    promo_bid: str | None,
    payable_price: decimal.Decimal,
) -> list[PromoRedemption]:
    """Apply eligible promo campaigns to an order and create application records."""
    with app.app_context():
        now = datetime.now(pytz.timezone("Asia/Shanghai"))

        campaigns: list[PromoCampaign] = PromoCampaign.query.filter(
            PromoCampaign.shifu_bid == shifu_bid,
            PromoCampaign.status == PROMO_CAMPAIGN_STATUS_ACTIVE,
            PromoCampaign.start_at <= now,
            PromoCampaign.end_at >= now,
            PromoCampaign.apply_type == PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
            PromoCampaign.deleted == 0,
        ).all()

        if promo_bid:
            manual_campaign = PromoCampaign.query.filter(
                PromoCampaign.promo_bid == promo_bid,
                PromoCampaign.status == PROMO_CAMPAIGN_STATUS_ACTIVE,
                PromoCampaign.start_at <= now,
                PromoCampaign.end_at >= now,
                PromoCampaign.shifu_bid == shifu_bid,
                PromoCampaign.deleted == 0,
            ).first()
            if manual_campaign and all(
                campaign.promo_bid != manual_campaign.promo_bid
                for campaign in campaigns
            ):
                campaigns.append(manual_campaign)

        applications: list[PromoRedemption] = []
        for campaign in campaigns:
            existing = PromoRedemption.query.filter(
                PromoRedemption.order_bid == order_bid,
                PromoRedemption.promo_bid == campaign.promo_bid,
                PromoRedemption.deleted == 0,
            ).first()
            if existing:
                applications.append(existing)
                continue

            application = PromoRedemption()
            application.redemption_bid = generate_id(app)
            application.promo_bid = campaign.promo_bid
            application.order_bid = order_bid
            application.user_bid = user_bid
            application.shifu_bid = shifu_bid
            application.promo_name = campaign.name
            application.discount_type = campaign.discount_type
            application.value = campaign.value
            application.discount_amount = _calculate_discount_amount(
                payable_price, campaign.discount_type, campaign.value
            )
            application.status = PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED
            db.session.add(application)
            applications.append(application)

        return applications


def query_promo_campaign_applications(
    app: Flask, order_bid: str, recalc_discount: bool
) -> list[PromoRedemption]:
    """Query promo campaign applications tied to an order."""
    with app.app_context():
        records: list[PromoRedemption] = PromoRedemption.query.filter(
            PromoRedemption.order_bid == order_bid,
            PromoRedemption.deleted == 0,
            PromoRedemption.status == PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
        ).all()

        if not recalc_discount or not records:
            return records

        now = datetime.now(pytz.timezone("Asia/Shanghai"))
        campaign_bids = [record.promo_bid for record in records]
        campaigns = PromoCampaign.query.filter(
            PromoCampaign.promo_bid.in_(campaign_bids),
            PromoCampaign.status == PROMO_CAMPAIGN_STATUS_ACTIVE,
            PromoCampaign.start_at <= now,
            PromoCampaign.end_at >= now,
            PromoCampaign.deleted == 0,
        ).all()
        valid_bids = {campaign.promo_bid for campaign in campaigns}
        return [record for record in records if record.promo_bid in valid_bids]
