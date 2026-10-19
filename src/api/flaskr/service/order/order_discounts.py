"""Compute coupon and promotion discounts shown on legacy orders."""

import decimal

from flaskr.i18n import _
from flaskr.service.common.pricing import calculate_percentage_amount
from flaskr.service.order.legacy_order_dtos import (
    DiscountInfo,
    PayItemDto,
)
from flaskr.service.promo.consts import (
    COUPON_TYPE_FIXED,
    COUPON_TYPE_PERCENT,
    PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
)
from flaskr.service.promo.models import (
    Coupon,
    PromoCampaign,
    PromoRedemption,
)
from flaskr.service.promo.models import (
    CouponUsage as CouponUsageModel,
)


def _resolve_coupon_display_name(coupon: Coupon) -> str:
    coupon_name = str(getattr(coupon, "name", "") or "").strip()
    coupon_code = str(getattr(coupon, "code", "") or "").strip()
    if coupon_name and coupon_code and coupon_name != coupon_code:
        return f"{coupon_name} ({coupon_code})"
    if coupon_name:
        return coupon_name
    if coupon_code:
        return coupon_code
    return str(getattr(coupon, "channel", "") or "").strip()


def _sum_discount_items(items: list[PayItemDto]) -> decimal.Decimal:
    total = decimal.Decimal("0.00")
    for item in items:
        try:
            total += decimal.Decimal(str(item.price or 0))
        except decimal.InvalidOperation:
            continue
    return total


def _supplement_promo_discount_items(
    record_id: str,
    items: list[PayItemDto],
    expected_discount_value: decimal.Decimal,
) -> list[PayItemDto]:
    current_discount_value = _sum_discount_items(items)
    if current_discount_value >= expected_discount_value:
        return items

    existing_price_names = {
        str(getattr(item, "price_name", "") or "").strip() for item in items
    }
    promo_records = (
        PromoRedemption.query.filter(
            PromoRedemption.order_bid == record_id,
            PromoRedemption.deleted == 0,
            PromoRedemption.status == PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
        )
        .order_by(PromoRedemption.updated_at.desc(), PromoRedemption.id.desc())
        .all()
    )
    promo_bids = [record.promo_bid for record in promo_records if record.promo_bid]
    promo_name_map = {}
    if promo_bids:
        promo_name_map = {
            campaign.promo_bid: str(campaign.name or "").strip()
            for campaign in PromoCampaign.query.filter(
                PromoCampaign.promo_bid.in_(promo_bids)
            ).all()
        }
    for record in promo_records:
        remaining_discount = expected_discount_value - current_discount_value
        if remaining_discount <= 0:
            break
        promo_name = (
            promo_name_map.get(record.promo_bid) or str(record.promo_name or "").strip()
        )
        if promo_name and promo_name in existing_price_names:
            continue
        try:
            record_discount = decimal.Decimal(str(record.discount_amount or 0))
        except decimal.InvalidOperation:
            continue
        if record_discount <= 0:
            continue
        item_discount = min(record_discount, remaining_discount)
        items.append(
            PayItemDto(
                _("server.order.payItemPromotion"),
                promo_name,
                item_discount,
                is_discount=True,
                discount_code=None,
            )
        )
        current_discount_value += item_discount
        if promo_name:
            existing_price_names.add(promo_name)
    return items


def calculate_discount_value(
    price: decimal.Decimal,
    campaign_applications: list,
    discount_records: list[CouponUsageModel],
) -> DiscountInfo:
    """Calculate discount value."""
    discount_value = 0
    items = []
    if campaign_applications is not None and len(campaign_applications) > 0:
        for campaign_application in campaign_applications:
            discount_value += campaign_application.discount_amount
            items.append(
                PayItemDto(
                    _("server.order.payItemPromotion"),
                    campaign_application.promo_name,
                    campaign_application.discount_amount,
                    is_discount=True,
                    discount_code=None,
                )
            )
    if discount_records is not None and len(discount_records) > 0:
        discount_ids = [i.coupon_bid for i in discount_records]
        coupons: list[Coupon] = Coupon.query.filter(
            Coupon.coupon_bid.in_(discount_ids)
        ).all()
        coupon_maps: dict[str, Coupon] = {i.coupon_bid: i for i in coupons}
        for discount_record in discount_records:
            discount = coupon_maps.get(discount_record.coupon_bid)
            if discount:
                coupon_amount = decimal.Decimal(discount.value)
                if discount.discount_type == COUPON_TYPE_FIXED:
                    discount_value += coupon_amount
                elif discount.discount_type == COUPON_TYPE_PERCENT:
                    coupon_amount = calculate_percentage_amount(price, coupon_amount)
                    discount_value += coupon_amount
                items.append(
                    PayItemDto(
                        _("server.order.payItemCoupon"),
                        _resolve_coupon_display_name(discount),
                        coupon_amount,
                        is_discount=True,
                        discount_code=discount.code,
                    )
                )
    discount_value = min(discount_value, price)
    return DiscountInfo(discount_value, items)
