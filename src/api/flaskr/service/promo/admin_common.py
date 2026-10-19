"""Share parsing, lookup, and validation helpers for promotion administration."""

from __future__ import annotations

import decimal
import json
import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.order.api import (
    _load_shifu_map,
)
from flaskr.service.order.models import Order
from flaskr.service.promo.admin_dtos import (
    AdminPromotionListResponseDTO,
    AdminPromotionSummaryDTO,
)
from flaskr.service.promo.consts import (
    COUPON_APPLY_TYPE_ALL,
    COUPON_APPLY_TYPE_SPECIFIC,
    COUPON_TYPE_FIXED,
    COUPON_TYPE_PERCENT,
    PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
    PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED,
    PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
)
from flaskr.service.promo.funcs import (
    build_campaign_enabled_expression,
)
from flaskr.service.promo.models import (
    Coupon,
    CouponUsage,
    PromoCampaign,
    PromoRedemption,
)
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.util.datetime import parse_naive_utc
from sqlalchemy import and_, func, or_

if TYPE_CHECKING:
    from flask_sqlalchemy.query import Query


PROMOTION_SCOPE_ALL_COURSES = "all_courses"

PROMOTION_SCOPE_SINGLE_COURSE = "single_course"

ALL_COURSES_FILTER_VALUE = json.dumps({"course_id": ""}, ensure_ascii=False)

COUPON_USAGE_TYPE_KEY_MAP = {
    COUPON_APPLY_TYPE_ALL: "module.operationsPromotion.usageType.generic",
    COUPON_APPLY_TYPE_SPECIFIC: "module.operationsPromotion.usageType.singleUse",
}

COUPON_DISCOUNT_TYPE_KEY_MAP = {
    COUPON_TYPE_FIXED: "module.operationsPromotion.discountType.fixed",
    COUPON_TYPE_PERCENT: "module.operationsPromotion.discountType.percent",
}

COUPON_COMPUTED_STATUS_KEY_MAP = {
    "inactive": "module.operationsPromotion.status.inactive",
    "not_started": "module.operationsPromotion.status.notStarted",
    "active": "module.operationsPromotion.status.active",
    "expired": "module.operationsPromotion.status.expired",
}

CAMPAIGN_COMPUTED_STATUS_KEY_MAP = {
    "inactive": "module.operationsPromotion.status.inactive",
    "not_started": "module.operationsPromotion.status.notStarted",
    "active": "module.operationsPromotion.status.active",
    "ended": "module.operationsPromotion.status.ended",
}

CAMPAIGN_REDEMPTION_STATUS_KEY_MAP = {
    PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED: "module.operationsPromotion.redemptionStatus.applied",
    PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED: "module.operationsPromotion.redemptionStatus.voided",
}

MAX_PROMOTION_PAGE_SIZE = 100

MAX_SPECIFIC_COUPON_BATCH_SIZE = 2000

PROMOTION_EXPIRING_SOON_DAYS = 7


def _parse_datetime(value: str, field_name: str, *, is_end: bool = False) -> datetime:
    normalized = str(value or "").strip()
    if not normalized:
        raise_param_error(field_name)
    # Date-only filters fill the day bounds (UTC wall-clock day).
    try:
        date_only = parse_naive_utc(normalized, "%Y-%m-%d")
    except ValueError:
        date_only = None
    if date_only is not None:
        if is_end:
            return date_only.replace(hour=23, minute=59, second=59)
        return date_only.replace(hour=0, minute=0, second=0)
    # Full datetime: accept any timezone offset (or 'Z'); naive input is treated
    # as UTC. Stored values are UTC, so convert aware values to UTC and drop the
    # tzinfo. The frontend may send whichever zone it likes — we normalize here.
    candidate = normalized.replace("Z", "+00:00").replace(" ", "T")
    parsed = None
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                parsed = parse_naive_utc(candidate, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        raise_param_error(field_name)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _parse_decimal_value(value: object, field_name: str) -> decimal.Decimal:
    try:
        parsed = decimal.Decimal(str(value).strip())
    except decimal.InvalidOperation:
        raise_param_error(field_name)
    if parsed <= 0:
        raise_param_error(field_name)
    return parsed.quantize(decimal.Decimal("0.01"))


def _parse_int_value(value: object, field_name: str) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        raise_param_error(field_name)
    return parsed


def _parse_bool_value(value: object, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise_param_error(field_name)
    return None


def _resolve_update_datetime(
    payload: dict,
    field_name: str,
    current_value: datetime,
    *,
    is_end: bool = False,
) -> datetime:
    if field_name not in payload:
        return current_value
    value = payload.get(field_name)
    if value is None or str(value).strip() == "":
        return current_value
    return _parse_datetime(value, field_name, is_end=is_end)


def _build_paged_response(
    summary: AdminPromotionSummaryDTO,
    page: int,
    page_size: int,
    total: int,
    items: list[dict],
) -> AdminPromotionListResponseDTO:
    return AdminPromotionListResponseDTO(
        summary=summary,
        page=page,
        page_size=page_size,
        total=total,
        page_count=math.ceil(total / page_size) if page_size > 0 else 0,
        items=items,
    )


def _normalize_coupon_filter(scope_type: str, shifu_bid: str) -> str:
    if scope_type == PROMOTION_SCOPE_SINGLE_COURSE:
        return json.dumps({"course_id": shifu_bid}, ensure_ascii=False)
    return ALL_COURSES_FILTER_VALUE


def _parse_coupon_scope(filter_value: str) -> tuple[str, str]:
    try:
        parsed = json.loads(filter_value or "{}")
    except json.JSONDecodeError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    shifu_bid = str(parsed.get("course_id", "") or "").strip()
    if shifu_bid:
        return PROMOTION_SCOPE_SINGLE_COURSE, shifu_bid
    return PROMOTION_SCOPE_ALL_COURSES, ""


def _resolve_course_query_bids(course_query: str) -> list[str]:
    normalized = str(course_query or "").strip()
    if not normalized:
        return []
    bids = _find_course_bids_by_name(normalized)
    bids.add(normalized)
    return sorted(bid for bid in bids if bid)


def _build_like_pattern(keyword: str) -> str:
    normalized = str(keyword or "").strip().lower()
    escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _build_user_keyword_query(keyword: str) -> Query:
    like_pattern = _build_like_pattern(keyword)
    return (
        db.session.query(UserEntity.user_bid)
        .outerjoin(
            AuthCredential,
            and_(
                AuthCredential.user_bid == UserEntity.user_bid,
                AuthCredential.provider_name.in_(["phone", "email"]),
            ),
        )
        .filter(
            UserEntity.deleted == 0,
            or_(
                func.lower(func.coalesce(UserEntity.user_bid, "")).like(
                    like_pattern, escape="\\"
                ),
                func.lower(func.coalesce(UserEntity.user_identify, "")).like(
                    like_pattern, escape="\\"
                ),
                func.lower(func.coalesce(UserEntity.nickname, "")).like(
                    like_pattern, escape="\\"
                ),
                func.lower(func.coalesce(AuthCredential.identifier, "")).like(
                    like_pattern, escape="\\"
                ),
            ),
        )
        .distinct()
    )


def _apply_keyword_filter(
    query: object, keyword: str, user_bid_field: object, *text_fields: object
) -> Query:
    normalized = str(keyword or "").strip().lower()
    if not normalized:
        return query
    like_pattern = _build_like_pattern(normalized)
    keyword_filters = [
        func.lower(func.coalesce(field, "")).like(like_pattern, escape="\\")
        for field in text_fields
    ]
    keyword_filters.append(user_bid_field.in_(_build_user_keyword_query(normalized)))
    return query.filter(or_(*keyword_filters))


def _validate_coupon_scope_course(shifu_bid: str) -> None:
    normalized_shifu_bid = str(shifu_bid or "").strip()
    if not normalized_shifu_bid:
        raise_param_error("shifu_bid")
    if not _load_shifu_map([normalized_shifu_bid]):
        raise_param_error("shifu_bid")


def _validate_coupon_code_uniqueness(
    code: str, *, exclude_coupon_bid: str = ""
) -> None:
    normalized_code = str(code or "").strip().upper()
    if not normalized_code:
        raise_param_error("code")

    duplicate_coupon_query = Coupon.query.filter(
        Coupon.code == normalized_code,
        Coupon.deleted == 0,
    )
    if exclude_coupon_bid:
        duplicate_coupon_query = duplicate_coupon_query.filter(
            Coupon.coupon_bid != exclude_coupon_bid
        )
    duplicate_coupon = duplicate_coupon_query.first()

    duplicate_usage = CouponUsage.query.filter(
        CouponUsage.code == normalized_code,
        CouponUsage.deleted == 0,
    ).first()

    if duplicate_coupon or duplicate_usage:
        raise_error("server.discount.discountAlreadyUsed")


def _resolve_batch_coupon_code(
    usage_type: int,
    code: object,
    *,
    exclude_coupon_bid: str = "",
) -> str:
    normalized_code = str(code or "").strip().upper()
    if usage_type == COUPON_APPLY_TYPE_SPECIFIC:
        return ""
    if not normalized_code:
        raise_param_error("code")
    _validate_coupon_code_uniqueness(
        normalized_code,
        exclude_coupon_bid=exclude_coupon_bid,
    )
    return normalized_code


def _load_user_name_map(user_bids: list[str]) -> dict[str, str]:
    if not user_bids:
        return {}
    users = UserEntity.query.filter(UserEntity.user_bid.in_(user_bids)).all()
    return {
        user.user_bid: (user.nickname or user.user_identify or user.user_bid or "")
        for user in users
    }


def _find_course_bids_by_name(keyword: str) -> set[str]:
    normalized = str(keyword or "").strip()
    if not normalized:
        return set()
    like_pattern = f"%{normalized}%"
    results = set()
    for model in (PublishedShifu, DraftShifu):
        rows = (
            db.session.query(model.shifu_bid)
            .filter(
                model.deleted == 0,
                model.title.like(like_pattern),
            )
            .distinct()
            .all()
        )
        for row in rows:
            shifu_bid = str(row[0] or "").strip()
            if shifu_bid:
                results.add(shifu_bid)
    return results


def _load_coupon_or_404(coupon_bid: str) -> Coupon:
    coupon = Coupon.query.filter(
        Coupon.coupon_bid == coupon_bid,
        Coupon.deleted == 0,
    ).first()
    if coupon is None:
        raise_param_error("coupon_bid")
    return coupon


def _campaign_has_redemptions(promo_bid: str) -> bool:
    return (
        PromoRedemption.query.filter(
            PromoRedemption.promo_bid == promo_bid,
            PromoRedemption.deleted == 0,
        ).first()
        is not None
    )


def _load_order_map(order_bids: list[str]) -> dict[str, Order]:
    if not order_bids:
        return {}
    orders = Order.query.filter(Order.order_bid.in_(order_bids)).all()
    return {order.order_bid: order for order in orders}


def _load_campaign_or_404(promo_bid: str) -> PromoCampaign:
    campaign = PromoCampaign.query.filter(
        PromoCampaign.promo_bid == promo_bid,
        PromoCampaign.deleted == 0,
    ).first()
    if campaign is None:
        raise_param_error("promo_bid")
    return campaign


def _validate_campaign_overlap(
    shifu_bid: str, start_at: datetime, end_at: datetime, *, exclude_promo_bid: str = ""
) -> None:
    query = PromoCampaign.query.filter(
        PromoCampaign.deleted == 0,
        PromoCampaign.apply_type == PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
        PromoCampaign.shifu_bid == shifu_bid,
        build_campaign_enabled_expression(PromoCampaign),
        PromoCampaign.start_at <= end_at,
        PromoCampaign.end_at >= start_at,
    )
    if exclude_promo_bid:
        query = query.filter(PromoCampaign.promo_bid != exclude_promo_bid)
    if query.first() is not None:
        raise_error("server.discount.discountNotApply")
