"""
Promo functions
"""

from contextlib import nullcontext
from datetime import datetime
import decimal

import pytz
from sqlalchemy import and_, or_
from sqlalchemy.sql import func

from .models import (
    CouponUsage as CouponUsageModel,
    PromoCampaign,
    PromoRedemption,
)
from ...dao import db
from .consts import (
    COUPON_BATCH_STATUS_ACTIVE,
    COUPON_BATCH_STATUS_INACTIVE,
    COUPON_STATUS_ACTIVE,
    COUPON_STATUS_USED,
    PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
    PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED,
    PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
    PROMO_CAMPAIGN_STATUS_ACTIVE,
    PROMO_CAMPAIGN_STATUS_INACTIVE,
)
from flask import Flask, has_app_context
from ...util import generate_id
from .consts import COUPON_TYPE_FIXED, COUPON_TYPE_PERCENT


def _is_legacy_operator_promotion(record: object) -> bool:
    return (
        not str(getattr(record, "created_user_bid", "") or "").strip()
        and not str(getattr(record, "updated_user_bid", "") or "").strip()
    )


def is_coupon_enabled_for_runtime(coupon) -> bool:
    status = int(getattr(coupon, "status", 0) or 0)
    return status == COUPON_BATCH_STATUS_ACTIVE or (
        status == COUPON_BATCH_STATUS_INACTIVE
        and _is_legacy_operator_promotion(coupon)
    )


def is_campaign_enabled_for_runtime(campaign) -> bool:
    status = int(getattr(campaign, "status", 0) or 0)
    return status == PROMO_CAMPAIGN_STATUS_ACTIVE or (
        status == PROMO_CAMPAIGN_STATUS_INACTIVE
        and _is_legacy_operator_promotion(campaign)
    )


def build_coupon_enabled_expression(model_or_columns):
    return or_(
        model_or_columns.status == COUPON_BATCH_STATUS_ACTIVE,
        and_(
            model_or_columns.status == COUPON_BATCH_STATUS_INACTIVE,
            func.coalesce(model_or_columns.created_user_bid, "") == "",
            func.coalesce(model_or_columns.updated_user_bid, "") == "",
        ),
    )


def build_campaign_enabled_expression(model_or_columns):
    return or_(
        model_or_columns.status == PROMO_CAMPAIGN_STATUS_ACTIVE,
        and_(
            model_or_columns.status == PROMO_CAMPAIGN_STATUS_INACTIVE,
            func.coalesce(model_or_columns.created_user_bid, "") == "",
            func.coalesce(model_or_columns.updated_user_bid, "") == "",
        ),
    )


def _app_context_scope(app: Flask):
    return nullcontext() if has_app_context() else app.app_context()


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
            {
                PromoRedemption.status: PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED,
                PromoRedemption.updated_at: func.now(),
            },
            synchronize_session="fetch",
        )
        db.session.commit()


def _calculate_discount_amount(
    payable_price: decimal.Decimal, discount_type: int, value: decimal.Decimal
) -> decimal.Decimal:
    if discount_type == COUPON_TYPE_FIXED:
        result = decimal.Decimal(value)
    elif discount_type == COUPON_TYPE_PERCENT:
        result = (
            decimal.Decimal(value)
            * decimal.Decimal(payable_price)
            / decimal.Decimal(100)
        )
    else:
        result = decimal.Decimal("0.00")
    return result.quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP)


def apply_promo_campaigns(
    app: Flask,
    shifu_bid: str,
    user_bid: str,
    order_bid: str,
    promo_bid: str | None,
    payable_price: decimal.Decimal,
) -> list[PromoRedemption]:
    """Apply eligible promo campaigns to an order and create application records."""
    with _app_context_scope(app):
        now = datetime.now(pytz.timezone("Asia/Shanghai"))

        campaigns: list[PromoCampaign] = PromoCampaign.query.filter(
            PromoCampaign.shifu_bid == shifu_bid,
            build_campaign_enabled_expression(PromoCampaign),
            PromoCampaign.start_at <= now,
            PromoCampaign.end_at >= now,
            PromoCampaign.apply_type == PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
            PromoCampaign.deleted == 0,
        ).all()

        if promo_bid:
            manual_campaign = PromoCampaign.query.filter(
                PromoCampaign.promo_bid == promo_bid,
                build_campaign_enabled_expression(PromoCampaign),
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
        campaign_bids = [campaign.promo_bid for campaign in campaigns]
        existing_by_campaign: dict[str, PromoRedemption] = {}
        voided_by_campaign: dict[str, PromoRedemption] = {}
        if campaign_bids:
            existing_records = PromoRedemption.query.filter(
                PromoRedemption.order_bid == order_bid,
                PromoRedemption.promo_bid.in_(campaign_bids),
                PromoRedemption.deleted == 0,
            ).all()
            for record in existing_records:
                if record.status == PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED:
                    existing_by_campaign[record.promo_bid] = record
                elif record.promo_bid not in voided_by_campaign:
                    voided_by_campaign[record.promo_bid] = record
        for campaign in campaigns:
            existing = existing_by_campaign.get(campaign.promo_bid)
            if existing:
                applications.append(existing)
                continue

            voided = voided_by_campaign.get(campaign.promo_bid)
            if voided:
                voided.user_bid = user_bid
                voided.shifu_bid = shifu_bid
                voided.promo_name = campaign.name
                voided.discount_type = campaign.discount_type
                voided.value = campaign.value
                voided.discount_amount = _calculate_discount_amount(
                    payable_price, campaign.discount_type, campaign.value
                )
                voided.status = PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED
                applications.append(voided)
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
    with _app_context_scope(app):
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
            build_campaign_enabled_expression(PromoCampaign),
            PromoCampaign.start_at <= now,
            PromoCampaign.end_at >= now,
            PromoCampaign.deleted == 0,
        ).all()
        valid_bids = {campaign.promo_bid for campaign in campaigns}
        return [record for record in records if record.promo_bid in valid_bids]
