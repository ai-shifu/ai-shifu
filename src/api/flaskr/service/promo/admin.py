from __future__ import annotations

import decimal
import json
import secrets
import string
from datetime import datetime
import math
from typing import Dict, Optional

from flask import Flask, current_app
from sqlalchemy import and_, case, func, or_

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.order.admin import (
    ORDER_STATUS_KEY_MAP,
    _format_decimal,
    _load_shifu_map,
    _load_user_map,
)
from flaskr.service.order.models import Order
from flaskr.service.promo.admin_dtos import (
    AdminPromotionCampaignDetailDTO,
    AdminPromotionCampaignItemDTO,
    AdminPromotionCampaignRedemptionDTO,
    AdminPromotionCouponCodeDTO,
    AdminPromotionCouponDetailDTO,
    AdminPromotionCouponItemDTO,
    AdminPromotionCouponUsageDTO,
    AdminPromotionListResponseDTO,
    AdminPromotionSummaryDTO,
)
from flaskr.service.promo.consts import (
    COUPON_APPLY_TYPE_ALL,
    COUPON_APPLY_TYPE_SPECIFIC,
    COUPON_BATCH_STATUS_ACTIVE,
    COUPON_BATCH_STATUS_INACTIVE,
    COUPON_STATUS_ACTIVE,
    COUPON_STATUS_INACTIVE,
    COUPON_STATUS_TIMEOUT,
    COUPON_STATUS_USED,
    COUPON_TYPE_FIXED,
    COUPON_TYPE_PERCENT,
    PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
    PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED,
    PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
    PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
    PROMO_CAMPAIGN_JOIN_TYPE_MANUAL,
    PROMO_CAMPAIGN_STATUS_ACTIVE,
    PROMO_CAMPAIGN_STATUS_INACTIVE,
)
from flaskr.service.promo.funcs import _calculate_discount_amount
from flaskr.service.promo.models import (
    Coupon,
    CouponUsage,
    PromoCampaign,
    PromoRedemption,
)
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity
from flaskr.util.timezone import get_app_timezone
from flaskr.util.uuid import generate_id

PROMOTION_SCOPE_ALL_COURSES = "all_courses"
PROMOTION_SCOPE_SINGLE_COURSE = "single_course"
PROMOTION_ADMIN_SOURCE_TIMEZONE = "Asia/Shanghai"
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


def _now_local_naive() -> datetime:
    source_tz = get_app_timezone(
        current_app._get_current_object(),
        PROMOTION_ADMIN_SOURCE_TIMEZONE,
    )
    return datetime.now(source_tz).replace(tzinfo=None)


def _normalize_promotion_admin_input_datetime(value: datetime) -> datetime:
    source_tz = get_app_timezone(
        current_app._get_current_object(),
        PROMOTION_ADMIN_SOURCE_TIMEZONE,
    )
    return value.replace(tzinfo=source_tz).replace(tzinfo=None)


def _parse_datetime(value: str, field_name: str, *, is_end: bool = False) -> datetime:
    normalized = str(value or "").strip()
    if not normalized:
        raise_param_error(field_name)
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            parsed = datetime.strptime(normalized, fmt)
            if fmt == "%Y-%m-%d":
                if is_end:
                    return parsed.replace(hour=23, minute=59, second=59)
                return parsed.replace(hour=0, minute=0, second=0)
            return _normalize_promotion_admin_input_datetime(parsed)
        except ValueError:
            continue
    raise_param_error(field_name)


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


def _format_promotion_admin_datetime(value: Optional[datetime]) -> str:
    if not value:
        return ""

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return ""
        parsed_value = None
        for candidate in (
            normalized.replace("Z", "+00:00"),
            normalized.replace(" ", "T"),
        ):
            try:
                parsed_value = datetime.fromisoformat(candidate)
                break
            except ValueError:
                continue
        if parsed_value is None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    parsed_value = datetime.strptime(normalized, fmt)
                    break
                except ValueError:
                    continue
        if parsed_value is None:
            raise_param_error("promotion_datetime")
        value = parsed_value

    app = current_app._get_current_object()
    source_tz = get_app_timezone(app, PROMOTION_ADMIN_SOURCE_TIMEZONE)
    target_tz = get_app_timezone(app, "UTC")
    localized_value = (
        value
        if getattr(value, "tzinfo", None) is not None
        else value.replace(tzinfo=source_tz)
    )
    return localized_value.astimezone(target_tz).isoformat().replace("+00:00", "Z")


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


def _build_user_keyword_query(keyword: str):
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


def _apply_keyword_filter(query, keyword: str, user_bid_field, *text_fields):
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


def _build_coupon_status_filter(status: str):
    normalized = str(status or "").strip()
    if not normalized:
        return None
    now = _now_local_naive()
    if normalized == "inactive":
        return Coupon.status != COUPON_BATCH_STATUS_ACTIVE
    if normalized == "not_started":
        return and_(
            Coupon.status == COUPON_BATCH_STATUS_ACTIVE,
            Coupon.start > now,
        )
    if normalized == "active":
        return and_(
            Coupon.status == COUPON_BATCH_STATUS_ACTIVE,
            Coupon.start <= now,
            Coupon.end >= now,
        )
    if normalized == "expired":
        return and_(
            Coupon.status == COUPON_BATCH_STATUS_ACTIVE,
            Coupon.end < now,
        )
    return None


def _build_campaign_status_filter(status: str):
    normalized = str(status or "").strip()
    if not normalized:
        return None
    now = _now_local_naive()
    if normalized == "inactive":
        return PromoCampaign.status != PROMO_CAMPAIGN_STATUS_ACTIVE
    if normalized == "not_started":
        return and_(
            PromoCampaign.status == PROMO_CAMPAIGN_STATUS_ACTIVE,
            PromoCampaign.start_at > now,
        )
    if normalized == "active":
        return and_(
            PromoCampaign.status == PROMO_CAMPAIGN_STATUS_ACTIVE,
            PromoCampaign.start_at <= now,
            PromoCampaign.end_at >= now,
        )
    if normalized == "ended":
        return and_(
            PromoCampaign.status == PROMO_CAMPAIGN_STATUS_ACTIVE,
            PromoCampaign.end_at < now,
        )
    return None


def _generate_random_coupon_code(length: int = 12) -> str:
    charset = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(charset) for _ in range(length))


def _generate_unique_coupon_code() -> str:
    for _ in range(20):
        code = _generate_random_coupon_code()
        exists = Coupon.query.filter(Coupon.code == code, Coupon.deleted == 0).first()
        if exists:
            continue
        usage_exists = CouponUsage.query.filter(
            CouponUsage.code == code,
            CouponUsage.deleted == 0,
        ).first()
        if not usage_exists:
            return code
    raise_error("server.common.unknownError")


def _generate_unique_coupon_codes(count: int) -> list[str]:
    if count <= 0:
        return []

    max_rounds = 20
    rounds = 0
    generated: list[str] = []
    seen_candidates: set[str] = set()
    while len(generated) < count:
        if rounds >= max_rounds:
            raise_error("server.common.unknownError")
        rounds += 1
        remaining = count - len(generated)
        batch_size = max(remaining * 2, 20)
        candidates: list[str] = []
        while len(candidates) < batch_size:
            code = _generate_random_coupon_code()
            if code in seen_candidates:
                continue
            seen_candidates.add(code)
            candidates.append(code)

        existing_coupon_codes = {
            row[0]
            for row in Coupon.query.with_entities(Coupon.code)
            .filter(
                Coupon.deleted == 0,
                Coupon.code.in_(candidates),
            )
            .all()
        }
        existing_usage_codes = {
            row[0]
            for row in CouponUsage.query.with_entities(CouponUsage.code)
            .filter(
                CouponUsage.deleted == 0,
                CouponUsage.code.in_(candidates),
            )
            .all()
        }
        existing_codes = existing_coupon_codes | existing_usage_codes
        for code in candidates:
            if code in existing_codes:
                continue
            generated.append(code)
            if len(generated) >= count:
                break
    return generated


def _build_specific_coupon_usages(
    app: Flask,
    *,
    coupon_bid: str,
    name: str,
    discount_type: int,
    value: decimal.Decimal,
    shifu_bid: str,
    count: int,
) -> list[CouponUsage]:
    codes = _generate_unique_coupon_codes(count)
    usages: list[CouponUsage] = []
    for code in codes:
        usage = CouponUsage()
        usage.coupon_usage_bid = generate_id(app)
        usage.coupon_bid = coupon_bid
        usage.name = name
        usage.code = code
        usage.discount_type = discount_type
        usage.value = value
        usage.status = COUPON_STATUS_ACTIVE
        usage.shifu_bid = shifu_bid
        usages.append(usage)
    return usages


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


def _compute_coupon_status(coupon: Coupon) -> str:
    now = _now_local_naive()
    if int(coupon.status or 0) != COUPON_BATCH_STATUS_ACTIVE:
        return "inactive"
    if coupon.start and coupon.start > now:
        return "not_started"
    if coupon.end and coupon.end < now:
        return "expired"
    return "active"


def _compute_campaign_status(campaign: PromoCampaign) -> str:
    now = _now_local_naive()
    if int(campaign.status or 0) != PROMO_CAMPAIGN_STATUS_ACTIVE:
        return "inactive"
    if campaign.start_at and campaign.start_at > now:
        return "not_started"
    if campaign.end_at and campaign.end_at < now:
        return "ended"
    return "active"


def _build_coupon_item(
    coupon: Coupon, course_map: Dict[str, DraftShifu | PublishedShifu]
) -> AdminPromotionCouponItemDTO:
    scope_type, shifu_bid = _parse_coupon_scope(coupon.filter or "{}")
    course = course_map.get(shifu_bid)
    computed_status = _compute_coupon_status(coupon)
    usage_type = int(coupon.usage_type or COUPON_APPLY_TYPE_ALL)
    return AdminPromotionCouponItemDTO(
        coupon_bid=coupon.coupon_bid or "",
        name=getattr(coupon, "name", "") or coupon.channel or "",
        code="" if usage_type == COUPON_APPLY_TYPE_SPECIFIC else (coupon.code or ""),
        usage_type=usage_type,
        usage_type_key=COUPON_USAGE_TYPE_KEY_MAP.get(
            usage_type, "module.operationsPromotion.usageType.generic"
        ),
        discount_type=int(coupon.discount_type or COUPON_TYPE_FIXED),
        discount_type_key=COUPON_DISCOUNT_TYPE_KEY_MAP.get(
            int(coupon.discount_type or COUPON_TYPE_FIXED),
            "module.operationsPromotion.discountType.fixed",
        ),
        value=_format_decimal(coupon.value),
        scope_type=scope_type,
        shifu_bid=shifu_bid,
        course_name=getattr(course, "title", "") or "",
        start_at=_format_promotion_admin_datetime(coupon.start),
        end_at=_format_promotion_admin_datetime(coupon.end),
        total_count=int(coupon.total_count or 0),
        used_count=int(coupon.used_count or 0),
        computed_status=computed_status,
        computed_status_key=COUPON_COMPUTED_STATUS_KEY_MAP[computed_status],
        created_at=_format_promotion_admin_datetime(coupon.created_at),
        updated_at=_format_promotion_admin_datetime(coupon.updated_at),
    )


def _build_campaign_item(
    campaign: PromoCampaign,
    course_map: Dict[str, DraftShifu | PublishedShifu],
    applied_order_count: int,
    total_discount_amount: decimal.Decimal,
    has_redemptions: bool,
) -> AdminPromotionCampaignItemDTO:
    computed_status = _compute_campaign_status(campaign)
    course = course_map.get(campaign.shifu_bid or "")
    return AdminPromotionCampaignItemDTO(
        promo_bid=campaign.promo_bid or "",
        name=campaign.name or "",
        shifu_bid=campaign.shifu_bid or "",
        course_name=getattr(course, "title", "") or "",
        apply_type=int(campaign.apply_type or PROMO_CAMPAIGN_JOIN_TYPE_AUTO),
        discount_type=int(campaign.discount_type or COUPON_TYPE_FIXED),
        discount_type_key=COUPON_DISCOUNT_TYPE_KEY_MAP.get(
            int(campaign.discount_type or COUPON_TYPE_FIXED),
            "module.operationsPromotion.discountType.fixed",
        ),
        value=_format_decimal(campaign.value),
        channel=campaign.channel or "",
        start_at=_format_promotion_admin_datetime(campaign.start_at),
        end_at=_format_promotion_admin_datetime(campaign.end_at),
        computed_status=computed_status,
        computed_status_key=CAMPAIGN_COMPUTED_STATUS_KEY_MAP[computed_status],
        applied_order_count=applied_order_count,
        has_redemptions=has_redemptions,
        total_discount_amount=_format_decimal(total_discount_amount),
        created_at=_format_promotion_admin_datetime(campaign.created_at),
        updated_at=_format_promotion_admin_datetime(campaign.updated_at),
    )


def _load_user_name_map(user_bids: list[str]) -> Dict[str, str]:
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
    results = set()
    for model in (PublishedShifu, DraftShifu):
        records = model.query.filter(
            model.deleted == 0,
            model.title.like(f"%{normalized}%"),
        ).all()
        for record in records:
            if record.shifu_bid:
                results.add(record.shifu_bid)
    return results


def list_operator_promotion_coupons(
    app: Flask, page: int, page_size: int, filters: dict
) -> AdminPromotionListResponseDTO:
    del app
    page_size = min(page_size, MAX_PROMOTION_PAGE_SIZE)
    query = Coupon.query.filter(Coupon.deleted == 0)
    keyword = str(filters.get("keyword", "") or "").strip()
    name = str(filters.get("name", "") or "").strip()
    course_query = str(
        filters.get("course_query")
        or filters.get("course_name")
        or filters.get("shifu_bid")
        or ""
    ).strip()
    usage_type = str(filters.get("usage_type", "") or "").strip()
    discount_type = str(filters.get("discount_type", "") or "").strip()
    if usage_type:
        query = query.filter(Coupon.usage_type == int(usage_type))
    if discount_type:
        query = query.filter(Coupon.discount_type == int(discount_type))
    if keyword:
        keyword_like = f"%{keyword}%"
        keyword_coupon_bids_query = (
            db.session.query(CouponUsage.coupon_bid)
            .filter(
                CouponUsage.deleted == 0,
                CouponUsage.code.ilike(keyword_like),
            )
            .distinct()
        )
        query = query.filter(
            or_(
                Coupon.coupon_bid.ilike(keyword_like),
                Coupon.code.ilike(keyword_like),
                Coupon.coupon_bid.in_(keyword_coupon_bids_query),
            )
        )
    if name:
        name_like = f"%{name}%"
        query = query.filter(
            or_(
                Coupon.name.ilike(name_like),
                and_(Coupon.name == "", Coupon.channel.ilike(name_like)),
            )
        )
    if course_query:
        course_bids = _resolve_course_query_bids(course_query)
        query = query.filter(
            Coupon.filter.in_(
                [
                    _normalize_coupon_filter(PROMOTION_SCOPE_SINGLE_COURSE, bid)
                    for bid in course_bids
                ]
            )
        )
    start_time = filters.get("start_time")
    end_time = filters.get("end_time")
    if start_time is not None:
        query = query.filter(Coupon.end >= start_time)
    if end_time is not None:
        query = query.filter(Coupon.start <= end_time)
    status_filter = _build_coupon_status_filter(str(filters.get("status", "") or ""))
    if status_filter is not None:
        query = query.filter(status_filter)

    filtered_subquery = query.with_entities(
        Coupon.coupon_bid.label("coupon_bid"),
        Coupon.used_count.label("used_count"),
        Coupon.filter.label("filter"),
        Coupon.status.label("status"),
        Coupon.start.label("start"),
        Coupon.end.label("end"),
    ).subquery()
    latest_usage = (
        db.session.query(CouponUsage.updated_at)
        .filter(
            CouponUsage.deleted == 0,
            CouponUsage.order_bid != "",
            CouponUsage.coupon_bid.in_(
                db.session.query(filtered_subquery.c.coupon_bid)
            ),
        )
        .order_by(CouponUsage.updated_at.desc())
        .first()
    )
    now = _now_local_naive()
    summary_row = db.session.query(
        func.count(filtered_subquery.c.coupon_bid).label("total"),
        func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            filtered_subquery.c.status == COUPON_BATCH_STATUS_ACTIVE,
                            filtered_subquery.c.start <= now,
                            filtered_subquery.c.end >= now,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("active"),
        func.coalesce(func.sum(filtered_subquery.c.used_count), 0).label("usage_count"),
        func.coalesce(
            func.count(
                func.distinct(
                    case(
                        (
                            filtered_subquery.c.filter != ALL_COURSES_FILTER_VALUE,
                            filtered_subquery.c.filter,
                        ),
                        else_=None,
                    )
                )
            ),
            0,
        ).label("covered_courses"),
    ).one()
    summary = AdminPromotionSummaryDTO(
        total=int(summary_row.total or 0),
        active=int(summary_row.active or 0),
        usage_count=int(summary_row.usage_count or 0),
        latest_usage_at=_format_promotion_admin_datetime(
            getattr(latest_usage, "updated_at", None)
        ),
        covered_courses=int(summary_row.covered_courses or 0),
        discount_amount="0",
    )

    start = (page - 1) * page_size
    paged = query.order_by(Coupon.id.desc()).offset(start).limit(page_size).all()
    course_bids = [
        _parse_coupon_scope(coupon.filter or "{}")[1]
        for coupon in paged
        if _parse_coupon_scope(coupon.filter or "{}")[1]
    ]
    course_map = _load_shifu_map(course_bids)
    items = [_build_coupon_item(coupon, course_map).__json__() for coupon in paged]
    return _build_paged_response(summary, page, page_size, summary.total, items)


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


def _coupon_is_enableable(coupon: Coupon) -> bool:
    now = _now_local_naive()
    if coupon.end and coupon.end < now:
        return False
    return int(coupon.used_count or 0) < int(coupon.total_count or 0)


def _campaign_is_enableable(campaign: PromoCampaign) -> bool:
    now = _now_local_naive()
    return not campaign.end_at or campaign.end_at >= now


def _campaign_strategy_fields_editable(campaign: PromoCampaign) -> bool:
    if campaign.start_at and campaign.start_at <= _now_local_naive():
        return False
    return not _campaign_has_redemptions(campaign.promo_bid or "")


def create_operator_promotion_coupon(
    app: Flask, operator_user_bid: str, payload: dict
) -> dict:
    with app.app_context():
        name = str(payload.get("name", "") or "").strip()
        if not name:
            raise_param_error("name")
        usage_type = _parse_int_value(payload.get("usage_type"), "usage_type")
        if usage_type not in {COUPON_APPLY_TYPE_ALL, COUPON_APPLY_TYPE_SPECIFIC}:
            raise_param_error("usage_type")
        discount_type = _parse_int_value(payload.get("discount_type"), "discount_type")
        if discount_type not in {COUPON_TYPE_FIXED, COUPON_TYPE_PERCENT}:
            raise_param_error("discount_type")
        value = _parse_decimal_value(payload.get("value"), "value")
        if discount_type == COUPON_TYPE_PERCENT and value > decimal.Decimal("100"):
            raise_param_error("value")
        total_count = payload.get("total_count")
        if total_count in (None, ""):
            raise_param_error("total_count")
        total_count_int = _parse_int_value(total_count, "total_count")
        if total_count_int <= 0:
            raise_param_error("total_count")
        if (
            usage_type == COUPON_APPLY_TYPE_SPECIFIC
            and total_count_int > MAX_SPECIFIC_COUPON_BATCH_SIZE
        ):
            raise_param_error("total_count")
        scope_type = str(
            payload.get("scope_type", PROMOTION_SCOPE_ALL_COURSES) or ""
        ).strip()
        if scope_type not in {
            PROMOTION_SCOPE_ALL_COURSES,
            PROMOTION_SCOPE_SINGLE_COURSE,
        }:
            raise_param_error("scope_type")
        shifu_bid = str(payload.get("shifu_bid", "") or "").strip()
        if scope_type == PROMOTION_SCOPE_SINGLE_COURSE and not shifu_bid:
            raise_param_error("shifu_bid")
        if scope_type == PROMOTION_SCOPE_SINGLE_COURSE:
            _validate_coupon_scope_course(shifu_bid)
        start_at = _parse_datetime(payload.get("start_at"), "start_at")
        end_at = _parse_datetime(payload.get("end_at"), "end_at", is_end=True)
        if end_at < start_at:
            raise_param_error("end_at")
        enabled = _parse_bool_value(payload.get("enabled", True), "enabled")
        code = _resolve_batch_coupon_code(usage_type, payload.get("code", ""))

        coupon = Coupon()
        coupon.coupon_bid = generate_id(app)
        coupon.name = name
        coupon.code = code
        coupon.discount_type = discount_type
        coupon.usage_type = usage_type
        coupon.value = value
        coupon.start = start_at
        coupon.end = end_at
        coupon.channel = ""
        coupon.filter = _normalize_coupon_filter(scope_type, shifu_bid)
        coupon.total_count = total_count_int
        coupon.used_count = 0
        coupon.status = (
            COUPON_BATCH_STATUS_ACTIVE if enabled else COUPON_BATCH_STATUS_INACTIVE
        )
        coupon.created_user_bid = operator_user_bid
        coupon.updated_user_bid = operator_user_bid
        db.session.add(coupon)

        if usage_type == COUPON_APPLY_TYPE_SPECIFIC:
            db.session.bulk_save_objects(
                _build_specific_coupon_usages(
                    app,
                    coupon_bid=coupon.coupon_bid,
                    name=name,
                    discount_type=discount_type,
                    value=value,
                    shifu_bid=shifu_bid,
                    count=total_count_int,
                )
            )

        db.session.commit()
        return {"coupon_bid": coupon.coupon_bid}


def update_operator_promotion_coupon(
    app: Flask, operator_user_bid: str, coupon_bid: str, payload: dict
) -> dict:
    with app.app_context():
        coupon = _load_coupon_or_404(coupon_bid)
        name = str(payload.get("name", "") or "").strip()
        if not name:
            raise_param_error("name")

        usage_type = _parse_int_value(payload.get("usage_type"), "usage_type")
        if usage_type != int(coupon.usage_type or COUPON_APPLY_TYPE_ALL):
            raise_param_error("usage_type")

        discount_type = _parse_int_value(payload.get("discount_type"), "discount_type")
        if discount_type != int(coupon.discount_type or COUPON_TYPE_FIXED):
            raise_param_error("discount_type")

        value = _parse_decimal_value(payload.get("value"), "value")
        if discount_type == COUPON_TYPE_PERCENT and value > decimal.Decimal("100"):
            raise_param_error("value")
        if value != decimal.Decimal(coupon.value or 0).quantize(
            decimal.Decimal("0.01")
        ):
            raise_param_error("value")

        total_count = payload.get("total_count")
        if total_count in (None, ""):
            raise_param_error("total_count")
        total_count_int = _parse_int_value(total_count, "total_count")
        if total_count_int <= 0:
            raise_param_error("total_count")
        used_count = int(coupon.used_count or 0)
        if total_count_int < used_count:
            raise_param_error("total_count")
        if (
            usage_type == COUPON_APPLY_TYPE_SPECIFIC
            and total_count_int > MAX_SPECIFIC_COUPON_BATCH_SIZE
            and total_count_int > int(coupon.total_count or 0)
        ):
            raise_param_error("total_count")

        scope_type = str(
            payload.get("scope_type", PROMOTION_SCOPE_ALL_COURSES) or ""
        ).strip()
        if scope_type not in {
            PROMOTION_SCOPE_ALL_COURSES,
            PROMOTION_SCOPE_SINGLE_COURSE,
        }:
            raise_param_error("scope_type")
        shifu_bid = str(payload.get("shifu_bid", "") or "").strip()
        if scope_type == PROMOTION_SCOPE_SINGLE_COURSE and not shifu_bid:
            raise_param_error("shifu_bid")
        current_scope_type, current_shifu_bid = _parse_coupon_scope(
            coupon.filter or "{}"
        )
        if scope_type != current_scope_type or shifu_bid != current_shifu_bid:
            raise_param_error("scope_type")

        start_at = _resolve_update_datetime(payload, "start_at", coupon.start)
        end_at = _resolve_update_datetime(
            payload,
            "end_at",
            coupon.end,
            is_end=True,
        )
        if end_at < start_at:
            raise_param_error("end_at")

        current_code = str(coupon.code or "").strip().upper()
        provided_code = str(payload.get("code", "") or "").strip().upper()
        if usage_type == COUPON_APPLY_TYPE_ALL and provided_code != current_code:
            raise_param_error("code")

        coupon.name = name
        coupon.start = start_at
        coupon.end = end_at
        coupon.total_count = total_count_int
        coupon.updated_user_bid = operator_user_bid
        if usage_type == COUPON_APPLY_TYPE_SPECIFIC:
            coupon.code = ""

        if usage_type == COUPON_APPLY_TYPE_SPECIFIC:
            unused_codes = (
                CouponUsage.query.filter(
                    CouponUsage.coupon_bid == coupon_bid,
                    CouponUsage.deleted == 0,
                    CouponUsage.order_bid == "",
                )
                .order_by(CouponUsage.id.asc())
                .all()
            )
            target_unused_count = total_count_int - used_count

            for usage in unused_codes[:target_unused_count]:
                usage.name = name

            for usage in unused_codes[target_unused_count:]:
                usage.deleted = 1

            additional_count = target_unused_count - len(unused_codes)
            if additional_count > 0:
                db.session.bulk_save_objects(
                    _build_specific_coupon_usages(
                        app,
                        coupon_bid=coupon.coupon_bid,
                        name=name,
                        discount_type=int(coupon.discount_type or COUPON_TYPE_FIXED),
                        value=decimal.Decimal(coupon.value or 0),
                        shifu_bid=current_shifu_bid,
                        count=additional_count,
                    )
                )

        db.session.commit()
        return {"coupon_bid": coupon.coupon_bid}


def get_operator_promotion_coupon_detail(
    app: Flask, coupon_bid: str
) -> AdminPromotionCouponDetailDTO:
    del app
    coupon = _load_coupon_or_404(coupon_bid)
    scope_type, shifu_bid = _parse_coupon_scope(coupon.filter or "{}")
    course_map = _load_shifu_map([shifu_bid] if shifu_bid else [])
    user_name_map = _load_user_name_map(
        [
            coupon.created_user_bid,
            getattr(coupon, "updated_user_bid", ""),
        ]
    )
    latest_usage = (
        CouponUsage.query.filter(
            CouponUsage.coupon_bid == coupon.coupon_bid,
            CouponUsage.deleted == 0,
            CouponUsage.order_bid != "",
        )
        .order_by(CouponUsage.updated_at.desc())
        .first()
    )
    item = _build_coupon_item(coupon, course_map)
    item.scope_type = scope_type
    return AdminPromotionCouponDetailDTO(
        coupon=item,
        created_user_bid=coupon.created_user_bid or "",
        created_user_name=user_name_map.get(coupon.created_user_bid or "", ""),
        updated_user_bid=getattr(coupon, "updated_user_bid", "") or "",
        updated_user_name=user_name_map.get(
            getattr(coupon, "updated_user_bid", "") or "", ""
        ),
        remaining_count=max(
            int(coupon.total_count or 0) - int(coupon.used_count or 0), 0
        ),
        latest_used_at=_format_promotion_admin_datetime(
            getattr(latest_usage, "updated_at", None)
        ),
    )


def update_operator_promotion_coupon_status(
    app: Flask, operator_user_bid: str, coupon_bid: str, enabled: object
) -> dict:
    with app.app_context():
        enabled_value = _parse_bool_value(enabled, "enabled")
        coupon = _load_coupon_or_404(coupon_bid)
        if enabled_value and not _coupon_is_enableable(coupon):
            raise_error("server.discount.discountNotApply")
        coupon.status = (
            COUPON_BATCH_STATUS_ACTIVE
            if enabled_value
            else COUPON_BATCH_STATUS_INACTIVE
        )
        coupon.updated_user_bid = operator_user_bid
        db.session.commit()
        return {"coupon_bid": coupon.coupon_bid, "enabled": enabled_value}


def _load_order_map(order_bids: list[str]) -> Dict[str, Order]:
    if not order_bids:
        return {}
    orders = Order.query.filter(Order.order_bid.in_(order_bids)).all()
    return {order.order_bid: order for order in orders}


def _calculate_coupon_usage_discount_amount(
    order: Optional[Order], usage: CouponUsage
) -> str:
    if order is None:
        return _format_decimal(usage.value)
    payable_price = decimal.Decimal(order.payable_price or 0)
    discount_amount = _calculate_discount_amount(
        payable_price,
        int(usage.discount_type or COUPON_TYPE_FIXED),
        decimal.Decimal(usage.value or 0),
    )
    if discount_amount > payable_price:
        discount_amount = payable_price
    return _format_decimal(discount_amount)


def list_operator_promotion_coupon_usages(
    app: Flask, coupon_bid: str, page: int, page_size: int, filters: dict
) -> AdminPromotionListResponseDTO:
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
        latest_usage_at=_format_promotion_admin_datetime(summary_row.latest_usage_at),
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
                used_at=_format_promotion_admin_datetime(usage.updated_at),
                updated_at=_format_promotion_admin_datetime(usage.updated_at),
            ).__json__()
        )
    return _build_paged_response(summary, page, page_size, summary.total, items)


def list_operator_promotion_coupon_codes(
    app: Flask, coupon_bid: str, page: int, page_size: int, filters: dict
) -> AdminPromotionListResponseDTO:
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
        latest_usage_at=_format_promotion_admin_datetime(summary_row.latest_usage_at),
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
                used_at=_format_promotion_admin_datetime(
                    code.updated_at if code.order_bid else None
                ),
                updated_at=_format_promotion_admin_datetime(code.updated_at),
            ).__json__()
        )
    return _build_paged_response(summary, page, page_size, summary.total, items)


def _load_redemption_stats(promo_bids: list[str]) -> Dict[str, dict]:
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


def list_operator_promotion_campaigns(
    app: Flask, page: int, page_size: int, filters: dict
) -> AdminPromotionListResponseDTO:
    del app
    page_size = min(page_size, MAX_PROMOTION_PAGE_SIZE)
    query = PromoCampaign.query.filter(
        PromoCampaign.deleted == 0,
    )
    keyword = str(filters.get("keyword", "") or "").strip()
    course_query = str(
        filters.get("course_query")
        or filters.get("course_name")
        or filters.get("shifu_bid")
        or ""
    ).strip()
    discount_type = str(filters.get("discount_type", "") or "").strip()
    if discount_type:
        query = query.filter(PromoCampaign.discount_type == int(discount_type))
    if keyword:
        keyword_like = f"%{keyword}%"
        query = query.filter(
            or_(
                PromoCampaign.promo_bid.ilike(keyword_like),
                PromoCampaign.name.ilike(keyword_like),
            )
        )
    if course_query:
        course_bids = _resolve_course_query_bids(course_query)
        query = query.filter(PromoCampaign.shifu_bid.in_(course_bids))
    start_time = filters.get("start_time")
    end_time = filters.get("end_time")
    if start_time is not None:
        query = query.filter(PromoCampaign.end_at >= start_time)
    if end_time is not None:
        query = query.filter(PromoCampaign.start_at <= end_time)
    status_filter = _build_campaign_status_filter(str(filters.get("status", "") or ""))
    if status_filter is not None:
        query = query.filter(status_filter)

    filtered_subquery = query.with_entities(
        PromoCampaign.promo_bid.label("promo_bid"),
        PromoCampaign.shifu_bid.label("shifu_bid"),
        PromoCampaign.status.label("status"),
        PromoCampaign.start_at.label("start_at"),
        PromoCampaign.end_at.label("end_at"),
    ).subquery()
    now = _now_local_naive()
    active_campaign_case = case(
        (
            and_(
                filtered_subquery.c.status == PROMO_CAMPAIGN_STATUS_ACTIVE,
                filtered_subquery.c.start_at <= now,
                filtered_subquery.c.end_at >= now,
            ),
            filtered_subquery.c.promo_bid,
        ),
        else_=None,
    )
    summary_row = (
        db.session.query(
            func.count(func.distinct(filtered_subquery.c.promo_bid)).label("total"),
            func.count(func.distinct(active_campaign_case)).label("active"),
            func.coalesce(
                func.count(func.distinct(filtered_subquery.c.shifu_bid)),
                0,
            ).label("covered_courses"),
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
            ).label("usage_count"),
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
        .select_from(filtered_subquery)
        .outerjoin(
            PromoRedemption,
            and_(
                PromoRedemption.promo_bid == filtered_subquery.c.promo_bid,
                PromoRedemption.deleted == 0,
            ),
        )
        .one()
    )
    summary = AdminPromotionSummaryDTO(
        total=int(summary_row.total or 0),
        active=int(summary_row.active or 0),
        usage_count=int(summary_row.usage_count or 0),
        latest_usage_at=_format_promotion_admin_datetime(summary_row.latest_applied_at),
        covered_courses=int(summary_row.covered_courses or 0),
        discount_amount=_format_decimal(
            decimal.Decimal(summary_row.discount_amount or 0)
        ),
    )
    start = (page - 1) * page_size
    paged = query.order_by(PromoCampaign.id.desc()).offset(start).limit(page_size).all()
    stats_map = _load_redemption_stats(
        [campaign.promo_bid for campaign in paged if campaign.promo_bid]
    )
    course_map = _load_shifu_map(
        [campaign.shifu_bid for campaign in paged if campaign.shifu_bid]
    )
    items = [
        _build_campaign_item(
            campaign,
            course_map,
            int(stats_map.get(campaign.promo_bid or "", {}).get("count", 0)),
            stats_map.get(campaign.promo_bid or "", {}).get(
                "discount_amount", decimal.Decimal("0")
            ),
            bool(
                stats_map.get(campaign.promo_bid or "", {}).get("redemption_count", 0)
            ),
        ).__json__()
        for campaign in paged
    ]
    return _build_paged_response(summary, page, page_size, summary.total, items)


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
        PromoCampaign.status == PROMO_CAMPAIGN_STATUS_ACTIVE,
        PromoCampaign.start_at <= end_at,
        PromoCampaign.end_at >= start_at,
    )
    if exclude_promo_bid:
        query = query.filter(PromoCampaign.promo_bid != exclude_promo_bid)
    if query.first() is not None:
        raise_error("server.discount.discountNotApply")


def create_operator_promotion_campaign(
    app: Flask, operator_user_bid: str, payload: dict
) -> dict:
    with app.app_context():
        name = str(payload.get("name", "") or "").strip()
        if not name:
            raise_param_error("name")
        apply_type = _parse_int_value(payload.get("apply_type"), "apply_type")
        if apply_type not in {
            PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
            PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            PROMO_CAMPAIGN_JOIN_TYPE_MANUAL,
        }:
            raise_param_error("apply_type")
        shifu_bid = str(payload.get("shifu_bid", "") or "").strip()
        if not shifu_bid:
            raise_param_error("shifu_bid")
        discount_type = _parse_int_value(payload.get("discount_type"), "discount_type")
        if discount_type not in {COUPON_TYPE_FIXED, COUPON_TYPE_PERCENT}:
            raise_param_error("discount_type")
        value = _parse_decimal_value(payload.get("value"), "value")
        if discount_type == COUPON_TYPE_PERCENT and value > decimal.Decimal("100"):
            raise_param_error("value")
        start_at = _parse_datetime(payload.get("start_at"), "start_at")
        end_at = _parse_datetime(payload.get("end_at"), "end_at", is_end=True)
        if end_at < start_at:
            raise_param_error("end_at")
        enabled = _parse_bool_value(payload.get("enabled", True), "enabled")
        description = str(payload.get("description", "") or "").strip()
        channel = str(payload.get("channel", "") or "").strip()
        if enabled:
            _validate_campaign_overlap(shifu_bid, start_at, end_at)

        campaign = PromoCampaign()
        campaign.promo_bid = generate_id(app)
        campaign.shifu_bid = shifu_bid
        campaign.name = name
        campaign.description = description
        campaign.apply_type = apply_type
        campaign.status = (
            PROMO_CAMPAIGN_STATUS_ACTIVE if enabled else PROMO_CAMPAIGN_STATUS_INACTIVE
        )
        campaign.start_at = start_at
        campaign.end_at = end_at
        campaign.discount_type = discount_type
        campaign.value = value
        campaign.channel = channel
        campaign.filter = "{}"
        campaign.created_user_bid = operator_user_bid
        campaign.updated_user_bid = operator_user_bid
        db.session.add(campaign)
        db.session.commit()
        return {"promo_bid": campaign.promo_bid}


def update_operator_promotion_campaign(
    app: Flask, operator_user_bid: str, promo_bid: str, payload: dict
) -> dict:
    with app.app_context():
        campaign = _load_campaign_or_404(promo_bid)
        name = str(payload.get("name", "") or "").strip()
        if not name:
            raise_param_error("name")
        apply_type = _parse_int_value(payload.get("apply_type"), "apply_type")
        if apply_type not in {
            PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
            PROMO_CAMPAIGN_JOIN_TYPE_EVENT,
            PROMO_CAMPAIGN_JOIN_TYPE_MANUAL,
        }:
            raise_param_error("apply_type")
        shifu_bid = str(payload.get("shifu_bid", "") or "").strip()
        if shifu_bid != str(campaign.shifu_bid or "").strip():
            raise_param_error("shifu_bid")
        discount_type = _parse_int_value(payload.get("discount_type"), "discount_type")
        if discount_type != int(campaign.discount_type or COUPON_TYPE_FIXED):
            raise_param_error("discount_type")
        value = _parse_decimal_value(payload.get("value"), "value")
        if discount_type == COUPON_TYPE_PERCENT and value > decimal.Decimal("100"):
            raise_param_error("value")
        strategy_fields_editable = _campaign_strategy_fields_editable(campaign)
        if value != decimal.Decimal(campaign.value or 0).quantize(
            decimal.Decimal("0.01")
        ):
            raise_param_error("value")
        start_at = _resolve_update_datetime(
            payload,
            "start_at",
            campaign.start_at,
        )
        end_at = _resolve_update_datetime(
            payload,
            "end_at",
            campaign.end_at,
            is_end=True,
        )
        if end_at < start_at:
            raise_param_error("end_at")
        description = str(payload.get("description", "") or "").strip()
        channel = str(payload.get("channel", "") or "").strip()
        if channel != str(campaign.channel or "").strip():
            raise_param_error("channel")
        if (
            apply_type != int(campaign.apply_type or PROMO_CAMPAIGN_JOIN_TYPE_AUTO)
            and not strategy_fields_editable
        ):
            raise_param_error("apply_type")
        if (
            int(campaign.status or 0) == PROMO_CAMPAIGN_STATUS_ACTIVE
            and apply_type == PROMO_CAMPAIGN_JOIN_TYPE_AUTO
        ):
            _validate_campaign_overlap(
                shifu_bid,
                start_at,
                end_at,
                exclude_promo_bid=campaign.promo_bid or "",
            )

        campaign.name = name
        campaign.description = description
        campaign.apply_type = apply_type
        campaign.start_at = start_at
        campaign.end_at = end_at
        campaign.value = value
        campaign.channel = channel
        campaign.updated_user_bid = operator_user_bid
        db.session.commit()
        return {"promo_bid": campaign.promo_bid}


def get_operator_promotion_campaign_detail(
    app: Flask, promo_bid: str
) -> AdminPromotionCampaignDetailDTO:
    del app
    campaign = _load_campaign_or_404(promo_bid)
    course_map = _load_shifu_map([campaign.shifu_bid] if campaign.shifu_bid else [])
    user_name_map = _load_user_name_map(
        [
            campaign.created_user_bid,
            campaign.updated_user_bid,
        ]
    )
    stats = _load_redemption_stats([campaign.promo_bid]).get(
        campaign.promo_bid or "", {}
    )
    item = _build_campaign_item(
        campaign,
        course_map,
        int(stats.get("count", 0)),
        stats.get("discount_amount", decimal.Decimal("0")),
        bool(stats.get("redemption_count", 0)),
    )
    return AdminPromotionCampaignDetailDTO(
        campaign=item,
        description=campaign.description or "",
        created_user_bid=campaign.created_user_bid or "",
        created_user_name=user_name_map.get(campaign.created_user_bid or "", ""),
        updated_user_bid=campaign.updated_user_bid or "",
        updated_user_name=user_name_map.get(campaign.updated_user_bid or "", ""),
        latest_applied_at=_format_promotion_admin_datetime(
            stats.get("latest_applied_at")
        ),
    )


def update_operator_promotion_campaign_status(
    app: Flask, operator_user_bid: str, promo_bid: str, enabled: object
) -> dict:
    with app.app_context():
        enabled_value = _parse_bool_value(enabled, "enabled")
        campaign = _load_campaign_or_404(promo_bid)
        if enabled_value and not _campaign_is_enableable(campaign):
            raise_error("server.discount.discountNotApply")
        if (
            enabled_value
            and int(campaign.apply_type or PROMO_CAMPAIGN_JOIN_TYPE_AUTO)
            == PROMO_CAMPAIGN_JOIN_TYPE_AUTO
        ):
            _validate_campaign_overlap(
                campaign.shifu_bid or "",
                campaign.start_at,
                campaign.end_at,
                exclude_promo_bid=campaign.promo_bid or "",
            )
        campaign.status = (
            PROMO_CAMPAIGN_STATUS_ACTIVE
            if enabled_value
            else PROMO_CAMPAIGN_STATUS_INACTIVE
        )
        campaign.updated_user_bid = operator_user_bid
        db.session.commit()
        return {"promo_bid": campaign.promo_bid, "enabled": enabled_value}


def list_operator_promotion_campaign_redemptions(
    app: Flask, promo_bid: str, page: int, page_size: int, filters: dict
) -> AdminPromotionListResponseDTO:
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
        latest_usage_at=_format_promotion_admin_datetime(summary_row.latest_usage_at),
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
                applied_at=_format_promotion_admin_datetime(record.created_at),
                updated_at=_format_promotion_admin_datetime(record.updated_at),
            ).__json__()
        )
    return _build_paged_response(summary, page, page_size, summary.total, items)
