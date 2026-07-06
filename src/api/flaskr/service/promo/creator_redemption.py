from __future__ import annotations

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.promo.admin import (
    MAX_PROMOTION_PAGE_SIZE,
    PROMOTION_SCOPE_SINGLE_COURSE,
    _build_paged_response,
    _list_promotion_coupons,
    _load_coupon_or_404,
    _normalize_coupon_filter,
    _parse_coupon_scope,
    create_operator_promotion_coupon,
    get_operator_promotion_coupon_detail,
    list_operator_promotion_coupon_codes,
    list_operator_promotion_coupon_usages,
    update_operator_promotion_coupon,
    update_operator_promotion_coupon_status,
)
from flaskr.service.promo.admin_dtos import (
    AdminPromotionCouponDetailDTO,
    AdminPromotionListResponseDTO,
    AdminPromotionSummaryDTO,
)
from flaskr.service.promo.models import Coupon
from flaskr.service.shifu.models import PublishedShifu


def list_creator_course_redemption_coupons(
    app: Flask, creator_user_bid: str, page: int, page_size: int, filters: dict
) -> AdminPromotionListResponseDTO:
    """List course-scoped redemption coupons created by the current creator."""
    del app
    normalized_creator = str(creator_user_bid or "").strip()
    if not normalized_creator:
        raise_param_error("creator_user_bid")

    course_rows = (
        db.session.query(PublishedShifu.shifu_bid)
        .filter(
            PublishedShifu.created_user_bid == normalized_creator,
            PublishedShifu.deleted == 0,
        )
        .distinct()
        .all()
    )
    allowed_course_bids = sorted(
        row[0] for row in course_rows if row and str(row[0] or "").strip()
    )
    if not allowed_course_bids:
        empty_summary = AdminPromotionSummaryDTO(
            total=0,
            active=0,
            usage_count=0,
            latest_usage_at="",
            covered_courses=0,
            discount_amount="0",
        )
        safe_page_size = min(max(page_size, 1), MAX_PROMOTION_PAGE_SIZE)
        return _build_paged_response(empty_summary, max(page, 1), safe_page_size, 0, [])

    allowed_filters = [
        _normalize_coupon_filter(PROMOTION_SCOPE_SINGLE_COURSE, bid)
        for bid in allowed_course_bids
    ]
    base_query = Coupon.query.filter(
        Coupon.deleted == 0,
        Coupon.created_user_bid == normalized_creator,
        Coupon.filter.in_(allowed_filters),
    )
    return _list_promotion_coupons(page, page_size, filters, base_query)


def _load_creator_published_course_or_none(
    creator_user_bid: str, shifu_bid: str
) -> PublishedShifu | None:
    normalized_creator = str(creator_user_bid or "").strip()
    normalized_shifu_bid = str(shifu_bid or "").strip()
    if not normalized_creator or not normalized_shifu_bid:
        return None
    return (
        PublishedShifu.query.filter(
            PublishedShifu.shifu_bid == normalized_shifu_bid,
            PublishedShifu.created_user_bid == normalized_creator,
            PublishedShifu.deleted == 0,
        )
        .order_by(PublishedShifu.id.desc())
        .first()
    )


def _load_creator_course_redemption_coupon_or_404(
    creator_user_bid: str, coupon_bid: str
) -> Coupon:
    normalized_creator = str(creator_user_bid or "").strip()
    if not normalized_creator:
        raise_param_error("creator_user_bid")
    coupon = _load_coupon_or_404(str(coupon_bid or "").strip())
    scope_type, shifu_bid = _parse_coupon_scope(coupon.filter or "{}")
    if (
        coupon.created_user_bid != normalized_creator
        or scope_type != PROMOTION_SCOPE_SINGLE_COURSE
        or _load_creator_published_course_or_none(normalized_creator, shifu_bid) is None
    ):
        raise_error("server.shifu.noPermission")
    return coupon


def list_creator_course_redemption_coupon_usages(
    app: Flask,
    creator_user_bid: str,
    coupon_bid: str,
    page: int,
    page_size: int,
    filters: dict,
) -> AdminPromotionListResponseDTO:
    """List usage records for a creator-owned course redemption coupon."""
    _load_creator_course_redemption_coupon_or_404(creator_user_bid, coupon_bid)
    return list_operator_promotion_coupon_usages(
        app, coupon_bid, page, page_size, filters
    )


def list_creator_course_redemption_coupon_codes(
    app: Flask,
    creator_user_bid: str,
    coupon_bid: str,
    page: int,
    page_size: int,
    filters: dict,
) -> AdminPromotionListResponseDTO:
    """List generated sub-codes for a creator-owned course redemption coupon."""
    _load_creator_course_redemption_coupon_or_404(creator_user_bid, coupon_bid)
    return list_operator_promotion_coupon_codes(
        app, coupon_bid, page, page_size, filters
    )


def get_creator_course_redemption_coupon_detail(
    app: Flask,
    creator_user_bid: str,
    coupon_bid: str,
) -> AdminPromotionCouponDetailDTO:
    """Get detail for a creator-owned course redemption coupon."""
    _load_creator_course_redemption_coupon_or_404(creator_user_bid, coupon_bid)
    return get_operator_promotion_coupon_detail(app, coupon_bid)


def update_creator_course_redemption_coupon(
    app: Flask,
    creator_user_bid: str,
    coupon_bid: str,
    payload: dict,
) -> dict:
    """Update a creator-owned course redemption coupon with operator rules."""
    _load_creator_course_redemption_coupon_or_404(creator_user_bid, coupon_bid)
    return update_operator_promotion_coupon(app, creator_user_bid, coupon_bid, payload)


def update_creator_course_redemption_coupon_status(
    app: Flask,
    creator_user_bid: str,
    coupon_bid: str,
    enabled: object,
) -> dict:
    """Update status for a creator-owned course redemption coupon."""
    _load_creator_course_redemption_coupon_or_404(creator_user_bid, coupon_bid)
    return update_operator_promotion_coupon_status(
        app, creator_user_bid, coupon_bid, enabled
    )


def create_creator_course_redemption_coupon(
    app: Flask, creator_user_bid: str, payload: dict
) -> dict:
    """Create a redemption coupon scoped to one course owned by the creator."""
    with app.app_context():
        normalized_creator = str(creator_user_bid or "").strip()
        if not normalized_creator:
            raise_param_error("creator_user_bid")
        shifu_bid = str(payload.get("shifu_bid", "") or "").strip()
        if not shifu_bid:
            raise_param_error("shifu_bid")
        if (
            _load_creator_published_course_or_none(normalized_creator, shifu_bid)
            is None
        ):
            raise_error("server.shifu.noPermission")

        normalized_payload = dict(payload)
        normalized_payload["scope_type"] = PROMOTION_SCOPE_SINGLE_COURSE
        normalized_payload["shifu_bid"] = shifu_bid
        return create_operator_promotion_coupon(
            app, normalized_creator, normalized_payload
        )
