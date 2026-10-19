"""List coupon usages, coupon codes, and campaign redemptions for operators."""

from __future__ import annotations

import decimal
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.order.api import (
    ORDER_STATUS_KEY_MAP,
    _format_decimal,
    _load_shifu_map,
    _load_user_map,
)
from flaskr.service.promo.admin_common import (
    CAMPAIGN_REDEMPTION_STATUS_KEY_MAP,
    MAX_PROMOTION_PAGE_SIZE,
    _apply_keyword_filter,
    _build_paged_response,
    _load_campaign_or_404,
    _load_coupon_or_404,
    _load_order_map,
)
from flaskr.service.promo.admin_dtos import (
    AdminPromotionCampaignRedemptionDTO,
    AdminPromotionCouponCodeDTO,
    AdminPromotionCouponUsageDTO,
    AdminPromotionListResponseDTO,
    AdminPromotionSummaryDTO,
)
from flaskr.service.promo.consts import (
    COUPON_STATUS_ACTIVE,
    COUPON_STATUS_INACTIVE,
    COUPON_STATUS_TIMEOUT,
    COUPON_STATUS_USED,
    COUPON_TYPE_FIXED,
    PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
)
from flaskr.service.promo.funcs import (
    _calculate_discount_amount,
)
from flaskr.service.promo.models import (
    CouponUsage,
    PromoRedemption,
)
from sqlalchemy import case, func

if TYPE_CHECKING:
    from flask import Flask
    from flaskr.service.order.models import Order


def _calculate_coupon_usage_discount_amount(
    order: Order | None, usage: CouponUsage
) -> str:
    if order is None:
        return _format_decimal(usage.value)
    payable_price = decimal.Decimal(order.payable_price or 0)
    discount_amount = _calculate_discount_amount(
        payable_price,
        int(usage.discount_type or COUPON_TYPE_FIXED),
        decimal.Decimal(usage.value or 0),
    )
    discount_amount = min(discount_amount, payable_price)
    return _format_decimal(discount_amount)


def list_operator_promotion_coupon_usages(
    app: Flask, coupon_bid: str, page: int, page_size: int, filters: dict
) -> AdminPromotionListResponseDTO:
    """Return operator promotion coupon usages."""
    del app
    page_size = min(page_size, MAX_PROMOTION_PAGE_SIZE)
    _load_coupon_or_404(coupon_bid)
    query = CouponUsage.query.filter(
        CouponUsage.coupon_bid == coupon_bid,
        CouponUsage.deleted == 0,
        CouponUsage.order_bid != "",
    )
    status = str(filters.get("status", "") or "").strip()
    keyword = str(filters.get("keyword", "") or "").strip().lower()
    if status:
        query = query.filter(CouponUsage.status == int(status))
    query = _apply_keyword_filter(
        query,
        keyword,
        CouponUsage.user_bid,
        CouponUsage.code,
        CouponUsage.order_bid,
        CouponUsage.user_bid,
    )
    filtered_subquery = query.with_entities(
        CouponUsage.id.label("id"),
        CouponUsage.shifu_bid.label("shifu_bid"),
        CouponUsage.updated_at.label("updated_at"),
    ).subquery()
    summary_row = db.session.query(
        func.count(filtered_subquery.c.id).label("total"),
        func.max(filtered_subquery.c.updated_at).label("latest_usage_at"),
        func.coalesce(
            func.count(
                func.distinct(
                    case(
                        (
                            filtered_subquery.c.shifu_bid != "",
                            filtered_subquery.c.shifu_bid,
                        ),
                        else_=None,
                    )
                )
            ),
            0,
        ).label("covered_courses"),
    ).one()
    start = (page - 1) * page_size
    paged = (
        query.order_by(CouponUsage.updated_at.desc(), CouponUsage.id.desc())
        .offset(start)
        .limit(page_size)
        .all()
    )
    user_map = _load_user_map([usage.user_bid for usage in paged if usage.user_bid])
    order_map = _load_order_map([usage.order_bid for usage in paged if usage.order_bid])
    course_bids = {
        usage.shifu_bid
        or getattr(order_map.get(usage.order_bid or ""), "shifu_bid", "")
        for usage in paged
    }
    course_map = _load_shifu_map(
        [course_bid for course_bid in course_bids if course_bid]
    )
    summary = AdminPromotionSummaryDTO(
        total=int(summary_row.total or 0),
        active=0,
        usage_count=int(summary_row.total or 0),
        latest_usage_at=summary_row.latest_usage_at,
        covered_courses=int(summary_row.covered_courses or 0),
        discount_amount="0",
    )
    items: list[dict] = []
    for usage in paged:
        user = user_map.get(usage.user_bid or "", {})
        order = order_map.get(usage.order_bid or "")
        course_bid = usage.shifu_bid or getattr(order, "shifu_bid", "") or ""
        course = course_map.get(course_bid)
        items.append(
            AdminPromotionCouponUsageDTO(
                coupon_usage_bid=usage.coupon_usage_bid or "",
                code=usage.code or "",
                status=int(usage.status or COUPON_STATUS_INACTIVE),
                status_key={
                    COUPON_STATUS_INACTIVE: "module.order.couponStatus.inactive",
                    COUPON_STATUS_ACTIVE: "module.order.couponStatus.active",
                    COUPON_STATUS_USED: "module.order.couponStatus.used",
                    COUPON_STATUS_TIMEOUT: "module.order.couponStatus.timeout",
                }.get(
                    int(usage.status or COUPON_STATUS_INACTIVE),
                    "module.order.couponStatus.unknown",
                ),
                user_bid=usage.user_bid or "",
                user_mobile=user.get("mobile", ""),
                user_email=user.get("email", ""),
                user_nickname=user.get("nickname", ""),
                shifu_bid=course_bid,
                course_name=getattr(course, "title", "") or "",
                order_bid=usage.order_bid or "",
                order_status=int(getattr(order, "status", 0) or 0),
                order_status_key=ORDER_STATUS_KEY_MAP.get(
                    int(getattr(order, "status", 0) or 0),
                    "server.order.orderStatusInit",
                ),
                payable_price=_format_decimal(getattr(order, "payable_price", 0)),
                discount_amount=_calculate_coupon_usage_discount_amount(order, usage),
                paid_price=_format_decimal(getattr(order, "paid_price", 0)),
                used_at=usage.updated_at,
                updated_at=usage.updated_at,
            ).__json__()
        )
    return _build_paged_response(summary, page, page_size, summary.total, items)


def list_operator_promotion_coupon_codes(
    app: Flask, coupon_bid: str, page: int, page_size: int, filters: dict
) -> AdminPromotionListResponseDTO:
    """Return operator promotion coupon codes."""
    del app
    page_size = min(page_size, MAX_PROMOTION_PAGE_SIZE)
    _load_coupon_or_404(coupon_bid)
    keyword = str(filters.get("keyword", "") or "").strip().lower()
    query = CouponUsage.query.filter(
        CouponUsage.coupon_bid == coupon_bid,
        CouponUsage.deleted == 0,
    )
    query = _apply_keyword_filter(
        query,
        keyword,
        CouponUsage.user_bid,
        CouponUsage.code,
        CouponUsage.order_bid,
        CouponUsage.user_bid,
    )
    filtered_subquery = query.with_entities(
        CouponUsage.id.label("id"),
        CouponUsage.status.label("status"),
        CouponUsage.order_bid.label("order_bid"),
        CouponUsage.updated_at.label("updated_at"),
    ).subquery()
    summary_row = db.session.query(
        func.count(filtered_subquery.c.id).label("total"),
        func.coalesce(
            func.sum(
                case(
                    (filtered_subquery.c.status == COUPON_STATUS_ACTIVE, 1),
                    else_=0,
                )
            ),
            0,
        ).label("active"),
        func.coalesce(
            func.sum(
                case(
                    (filtered_subquery.c.order_bid != "", 1),
                    else_=0,
                )
            ),
            0,
        ).label("usage_count"),
        func.max(filtered_subquery.c.updated_at).label("latest_usage_at"),
    ).one()
    start = (page - 1) * page_size
    paged = (
        query.order_by(CouponUsage.updated_at.desc(), CouponUsage.id.desc())
        .offset(start)
        .limit(page_size)
        .all()
    )
    user_map = _load_user_map([code.user_bid for code in paged if code.user_bid])
    summary = AdminPromotionSummaryDTO(
        total=int(summary_row.total or 0),
        active=int(summary_row.active or 0),
        usage_count=int(summary_row.usage_count or 0),
        latest_usage_at=summary_row.latest_usage_at,
        covered_courses=0,
        discount_amount="0",
    )
    items: list[dict] = []
    for code in paged:
        user = user_map.get(code.user_bid or "", {})
        items.append(
            AdminPromotionCouponCodeDTO(
                coupon_usage_bid=code.coupon_usage_bid or "",
                code=code.code or "",
                status=int(code.status or COUPON_STATUS_INACTIVE),
                status_key={
                    COUPON_STATUS_INACTIVE: "module.order.couponStatus.inactive",
                    COUPON_STATUS_ACTIVE: "module.order.couponStatus.active",
                    COUPON_STATUS_USED: "module.order.couponStatus.used",
                    COUPON_STATUS_TIMEOUT: "module.order.couponStatus.timeout",
                }.get(
                    int(code.status or COUPON_STATUS_INACTIVE),
                    "module.order.couponStatus.unknown",
                ),
                user_bid=code.user_bid or "",
                user_mobile=user.get("mobile", ""),
                user_email=user.get("email", ""),
                user_nickname=user.get("nickname", ""),
                order_bid=code.order_bid or "",
                used_at=code.updated_at if code.order_bid else None,
                updated_at=code.updated_at,
            ).__json__()
        )
    return _build_paged_response(summary, page, page_size, summary.total, items)


def _load_redemption_stats(promo_bids: list[str]) -> dict[str, dict]:
    if not promo_bids:
        return {}
    rows = (
        db.session.query(
            PromoRedemption.promo_bid.label("promo_bid"),
            func.count(PromoRedemption.id).label("redemption_count"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            PromoRedemption.status
                            == PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("count"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            PromoRedemption.status
                            == PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
                            PromoRedemption.discount_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("discount_amount"),
            func.max(
                case(
                    (
                        PromoRedemption.status
                        == PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
                        PromoRedemption.updated_at,
                    ),
                    else_=None,
                )
            ).label("latest_applied_at"),
        )
        .filter(
            PromoRedemption.promo_bid.in_(promo_bids),
            PromoRedemption.deleted == 0,
        )
        .group_by(PromoRedemption.promo_bid)
        .all()
    )
    return {
        row.promo_bid or "": {
            "count": int(row.count or 0),
            "redemption_count": int(row.redemption_count or 0),
            "discount_amount": decimal.Decimal(row.discount_amount or 0),
            "latest_applied_at": row.latest_applied_at,
        }
        for row in rows
        if row.promo_bid
    }


def list_operator_promotion_campaign_redemptions(
    app: Flask, promo_bid: str, page: int, page_size: int, filters: dict
) -> AdminPromotionListResponseDTO:
    """Return operator promotion campaign redemptions."""
    del app
    page_size = min(page_size, MAX_PROMOTION_PAGE_SIZE)
    _load_campaign_or_404(promo_bid)
    keyword = str(filters.get("keyword", "") or "").strip().lower()
    query = PromoRedemption.query.filter(
        PromoRedemption.promo_bid == promo_bid,
        PromoRedemption.deleted == 0,
    )
    query = _apply_keyword_filter(
        query,
        keyword,
        PromoRedemption.user_bid,
        PromoRedemption.order_bid,
        PromoRedemption.user_bid,
    )
    filtered_subquery = query.with_entities(
        PromoRedemption.id.label("id"),
        PromoRedemption.status.label("status"),
        PromoRedemption.updated_at.label("updated_at"),
        PromoRedemption.discount_amount.label("discount_amount"),
    ).subquery()
    summary_row = db.session.query(
        func.count(filtered_subquery.c.id).label("total"),
        func.coalesce(
            func.sum(
                case(
                    (
                        filtered_subquery.c.status
                        == PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("active"),
        func.max(filtered_subquery.c.updated_at).label("latest_usage_at"),
        func.coalesce(
            func.sum(
                case(
                    (
                        filtered_subquery.c.status
                        == PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
                        filtered_subquery.c.discount_amount,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("discount_amount"),
    ).one()
    start = (page - 1) * page_size
    paged = (
        query.order_by(PromoRedemption.updated_at.desc(), PromoRedemption.id.desc())
        .offset(start)
        .limit(page_size)
        .all()
    )
    user_map = _load_user_map([record.user_bid for record in paged if record.user_bid])
    order_map = _load_order_map(
        [record.order_bid for record in paged if record.order_bid]
    )
    summary = AdminPromotionSummaryDTO(
        total=int(summary_row.total or 0),
        active=int(summary_row.active or 0),
        usage_count=int(summary_row.active or 0),
        latest_usage_at=summary_row.latest_usage_at,
        covered_courses=0,
        discount_amount=_format_decimal(
            decimal.Decimal(summary_row.discount_amount or 0)
        ),
    )
    items: list[dict] = []
    for record in paged:
        user = user_map.get(record.user_bid or "", {})
        order = order_map.get(record.order_bid or "")
        items.append(
            AdminPromotionCampaignRedemptionDTO(
                redemption_bid=record.redemption_bid or "",
                user_bid=record.user_bid or "",
                user_mobile=user.get("mobile", ""),
                user_email=user.get("email", ""),
                user_nickname=user.get("nickname", ""),
                order_bid=record.order_bid or "",
                order_status=int(getattr(order, "status", 0) or 0),
                order_status_key=ORDER_STATUS_KEY_MAP.get(
                    int(getattr(order, "status", 0) or 0),
                    "server.order.orderStatusInit",
                ),
                payable_price=_format_decimal(getattr(order, "payable_price", 0)),
                discount_amount=_format_decimal(record.discount_amount),
                paid_price=_format_decimal(getattr(order, "paid_price", 0)),
                status=int(record.status or PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED),
                status_key=CAMPAIGN_REDEMPTION_STATUS_KEY_MAP.get(
                    int(record.status or PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED),
                    "module.operationsPromotion.redemptionStatus.applied",
                ),
                applied_at=record.created_at,
                updated_at=record.updated_at,
            ).__json__()
        )
    return _build_paged_response(summary, page, page_size, summary.total, items)
