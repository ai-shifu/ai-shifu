"""Shared constants and cross-domain helpers for operator course admin.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional, Sequence, Set
from flask import current_app
from sqlalchemy import case, or_
from flaskr.dao import db
from flaskr.service.common.models import (
    raise_error,
)
from flaskr.service.order.models import Order
from flaskr.service.shifu.demo_courses import (
    is_builtin_demo_course,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.user.consts import (
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import (
    AuthCredential,
    UserInfo as UserEntity,
    UserToken,
)


COURSE_STATUS_PUBLISHED = "published"

COURSE_STATUS_UNPUBLISHED = "unpublished"

COURSE_QUICK_FILTER_DRAFT = "draft"

COURSE_QUICK_FILTER_PUBLISHED = "published"

COURSE_QUICK_FILTER_CREATED_LAST_7D = "created_last_7d"

COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D = "learning_active_30d"

COURSE_QUICK_FILTER_PAID_ORDER_30D = "paid_order_30d"

COURSE_QUICK_FILTER_VALUES = {
    COURSE_QUICK_FILTER_DRAFT,
    COURSE_QUICK_FILTER_PUBLISHED,
    COURSE_QUICK_FILTER_CREATED_LAST_7D,
    COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D,
    COURSE_QUICK_FILTER_PAID_ORDER_30D,
}

PROMPT_SOURCE_LESSON = "lesson"

PROMPT_SOURCE_CHAPTER = "chapter"

PROMPT_SOURCE_COURSE = "course"

COURSE_USER_LIST_MAX_PAGE_SIZE = 100

COURSE_USER_ROLE_OPERATOR = "operator"

COURSE_USER_ROLE_CREATOR = "creator"

COURSE_USER_ROLE_STUDENT = "student"

COURSE_USER_ROLE_NORMAL = "normal"

COURSE_USER_LEARNING_STATUS_NOT_STARTED = "not_started"

COURSE_USER_LEARNING_STATUS_LEARNING = "learning"

COURSE_USER_LEARNING_STATUS_COMPLETED = "completed"

OPERATOR_USER_STATUS_UNREGISTERED = "unregistered"

OPERATOR_USER_STATUS_REGISTERED = "registered"

OPERATOR_USER_STATUS_TRIAL = "trial"

OPERATOR_USER_STATUS_PAID = "paid"

OPERATOR_USER_STATUS_UNKNOWN = "unknown"

OPERATOR_USER_LIST_MAX_PAGE_SIZE = 100

OPERATOR_ORDER_LIST_MAX_PAGE_SIZE = 100

OPERATOR_USER_ROLE_REGULAR = "regular"

OPERATOR_USER_ROLE_CREATOR = "creator"

OPERATOR_USER_ROLE_OPERATOR = "operator"

OPERATOR_USER_ROLE_LEARNER = "learner"

OPERATOR_USER_QUICK_FILTER_CREATOR = "creator"

OPERATOR_USER_QUICK_FILTER_LEARNER = "learner"

OPERATOR_USER_QUICK_FILTER_REGISTERED = "registered"

OPERATOR_USER_QUICK_FILTER_PAID = "paid"

OPERATOR_USER_QUICK_FILTER_CREATED_LAST_30D = "created_last_30d"

OPERATOR_USER_QUICK_FILTER_REGISTERED_LAST_30D = "registered_last_30d"

OPERATOR_USER_QUICK_FILTER_LEARNING_ACTIVE_30D = "learning_active_30d"

OPERATOR_USER_QUICK_FILTER_PAID_LAST_30D = "paid_last_30d"

OPERATOR_USER_QUICK_FILTER_GUEST = "guest"

OPERATOR_USER_QUICK_FILTER_VALUES = {
    OPERATOR_USER_QUICK_FILTER_CREATOR,
    OPERATOR_USER_QUICK_FILTER_LEARNER,
    OPERATOR_USER_QUICK_FILTER_REGISTERED,
    OPERATOR_USER_QUICK_FILTER_PAID,
    OPERATOR_USER_QUICK_FILTER_CREATED_LAST_30D,
    OPERATOR_USER_QUICK_FILTER_REGISTERED_LAST_30D,
    OPERATOR_USER_QUICK_FILTER_LEARNING_ACTIVE_30D,
    OPERATOR_USER_QUICK_FILTER_PAID_LAST_30D,
    OPERATOR_USER_QUICK_FILTER_GUEST,
}

OPERATOR_USER_REGISTRATION_CREDENTIAL_PROVIDERS = (
    "phone",
    "email",
    "google",
    "wechat",
)

OPERATOR_USER_REGISTRATION_SOURCE_PHONE = "phone"

OPERATOR_USER_REGISTRATION_SOURCE_EMAIL = "email"

OPERATOR_USER_REGISTRATION_SOURCE_GOOGLE = "google"

OPERATOR_USER_REGISTRATION_SOURCE_WECHAT = "wechat"

OPERATOR_USER_REGISTRATION_SOURCE_IMPORTED = "imported"

OPERATOR_USER_REGISTRATION_SOURCE_UNKNOWN = "unknown"

OPERATOR_USER_SUPPORTED_LOGIN_METHOD_PROVIDERS = {
    "phone",
    "email",
    "google",
    "wechat",
}

OPERATOR_USER_SUPPORTED_REGISTRATION_SOURCE_PROVIDERS = (
    OPERATOR_USER_SUPPORTED_LOGIN_METHOD_PROVIDERS | {"manual", "import", "imported"}
)

OPERATOR_USER_PRELOADED_AUTH_CREDENTIAL_PROVIDERS = (
    OPERATOR_USER_SUPPORTED_REGISTRATION_SOURCE_PROVIDERS | {"password"}
)

COURSE_FOLLOW_UP_LIST_MAX_PAGE_SIZE = 100

COURSE_RATING_LIST_MAX_PAGE_SIZE = 100

COURSE_CREDIT_USAGE_LIST_MAX_PAGE_SIZE = 100

COURSE_CREDIT_USAGE_VIEW_GROUPED = "grouped"

COURSE_CREDIT_USAGE_VIEW_RAW = "raw"

COURSE_CREDIT_USAGE_MODE_LEARN = "learn"

COURSE_CREDIT_USAGE_MODE_LISTEN = "listen"

COURSE_CREDIT_USAGE_MODE_ASK = "ask"

COURSE_CREDIT_USAGE_MODE_MIXED = "mixed"

COURSE_CREDIT_USAGE_SCENE_LEARNING = "learning"

COURSE_CREDIT_USAGE_SCENE_PREVIEW = "preview"

COURSE_CREDIT_USAGE_SCENE_DEBUG = "debug"

OPERATOR_USER_CREDIT_GRANT_SOURCE_REWARD = "reward"

OPERATOR_USER_CREDIT_GRANT_SOURCE_COMPENSATION = "compensation"

OPERATOR_USER_CREDIT_GRANT_TYPE_MANUAL = "manual_credit"

OPERATOR_USER_CREDIT_GRANT_TYPE_REFERRAL_REWARD = "referral_reward"

OPERATOR_USER_CREDIT_TYPE_ALL = "all"

OPERATOR_USER_CREDIT_TYPE_CONSUME = "consume"

OPERATOR_USER_CREDIT_TYPE_GRANT = "grant"

OPERATOR_USER_CREDIT_TYPE_OTHER = "other"

OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_ALL = "all"

OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_SUBSCRIPTION = "subscription"

OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TRIAL_SUBSCRIPTION = "trial_subscription"

OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TOPUP = "topup"

OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_MANUAL = "manual"

OPERATOR_USER_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION = "align_subscription"

OPERATOR_USER_CREDIT_VALIDITY_1D = "1d"

OPERATOR_USER_CREDIT_VALIDITY_7D = "7d"

OPERATOR_USER_CREDIT_VALIDITY_1M = "1m"

OPERATOR_USER_CREDIT_VALIDITY_3M = "3m"

OPERATOR_USER_CREDIT_VALIDITY_1Y = "1y"

OPERATOR_USER_CREDIT_GRANT_SOURCES = {
    OPERATOR_USER_CREDIT_GRANT_SOURCE_REWARD,
    OPERATOR_USER_CREDIT_GRANT_SOURCE_COMPENSATION,
}

OPERATOR_USER_CREDIT_GRANT_TYPES = {
    OPERATOR_USER_CREDIT_GRANT_TYPE_MANUAL,
    OPERATOR_USER_CREDIT_GRANT_TYPE_REFERRAL_REWARD,
}

OPERATOR_USER_CREDIT_FILTER_TYPES = {
    OPERATOR_USER_CREDIT_TYPE_ALL,
    OPERATOR_USER_CREDIT_TYPE_CONSUME,
    OPERATOR_USER_CREDIT_TYPE_GRANT,
    OPERATOR_USER_CREDIT_TYPE_OTHER,
}


def _resolve_operator_credit_grant_type(
    grant_type: str,
    *,
    fallback: str = OPERATOR_USER_CREDIT_GRANT_TYPE_MANUAL,
) -> str:
    normalized_grant_type = str(grant_type or "").strip().lower()
    if normalized_grant_type == "manual_grant":
        return OPERATOR_USER_CREDIT_GRANT_TYPE_MANUAL
    if normalized_grant_type in OPERATOR_USER_CREDIT_GRANT_TYPES:
        return normalized_grant_type
    return fallback


OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCES = {
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_ALL,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_SUBSCRIPTION,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TRIAL_SUBSCRIPTION,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_TOPUP,
    OPERATOR_USER_CREDIT_FILTER_GRANT_SOURCE_MANUAL,
}

OPERATOR_USER_CREDIT_VALIDITY_PRESETS = {
    OPERATOR_USER_CREDIT_VALIDITY_ALIGN_SUBSCRIPTION,
    OPERATOR_USER_CREDIT_VALIDITY_1D,
    OPERATOR_USER_CREDIT_VALIDITY_7D,
    OPERATOR_USER_CREDIT_VALIDITY_1M,
    OPERATOR_USER_CREDIT_VALIDITY_3M,
    OPERATOR_USER_CREDIT_VALIDITY_1Y,
}

OPERATOR_TARGET_CONTACT_MAX_LENGTH = 320

OPERATOR_TARGET_PHONE_PATTERN = re.compile(r"^\d{11}$")

OPERATOR_TARGET_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)

USER_STATE_TO_OPERATOR_STATUS = {
    USER_STATE_UNREGISTERED: OPERATOR_USER_STATUS_UNREGISTERED,
    USER_STATE_REGISTERED: OPERATOR_USER_STATUS_REGISTERED,
    USER_STATE_TRAIL: OPERATOR_USER_STATUS_REGISTERED,
    USER_STATE_PAID: OPERATOR_USER_STATUS_PAID,
    str(USER_STATE_UNREGISTERED): OPERATOR_USER_STATUS_UNREGISTERED,
    str(USER_STATE_REGISTERED): OPERATOR_USER_STATUS_REGISTERED,
    str(USER_STATE_TRAIL): OPERATOR_USER_STATUS_REGISTERED,
    str(USER_STATE_PAID): OPERATOR_USER_STATUS_PAID,
}


def _get_legacy_admin_symbol(name: str, fallback: Any) -> Any:
    admin_module = sys.modules.get("flaskr.service.shifu.admin")
    if admin_module is None:
        return fallback
    return getattr(admin_module, name, fallback)


def _format_decimal(value: Optional[Decimal]) -> str:
    if value is None:
        return "0"
    if isinstance(value, str):
        normalized = value
    else:
        normalized = "{0:.2f}".format(value)
    if normalized.endswith(".00"):
        return normalized[:-3]
    return normalized


def _coerce_operator_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            current_app.logger.warning(
                "Failed to parse operator datetime value '%s'",
                value,
            )
            return None
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    current_app.logger.warning(
        "Unexpected operator datetime value type '%s'",
        type(value).__name__,
    )
    return None


def _format_average_score(value: Optional[Decimal]) -> str:
    if value is None:
        return ""
    return "{0:.1f}".format(value)


def _normalize_metadata_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _normalize_identifier(value: str) -> str:
    normalized = str(value or "").strip()
    if "@" in normalized:
        return normalized.lower()
    return normalized


def _load_course_user_contact_map(
    user_bids: Sequence[str],
) -> Dict[str, Dict[str, str]]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    if not normalized_user_bids:
        return {}

    credential_rows = (
        AuthCredential.query.filter(
            AuthCredential.user_bid.in_(normalized_user_bids),
            AuthCredential.deleted == 0,
            AuthCredential.provider_name.in_(["phone", "email", "google"]),
        )
        .order_by(AuthCredential.id.desc())
        .all()
    )
    contact_map: Dict[str, Dict[str, str]] = {
        user_bid: {"mobile": "", "email": ""} for user_bid in normalized_user_bids
    }
    for credential in credential_rows:
        user_bid = str(credential.user_bid or "").strip()
        if not user_bid:
            continue
        resolved = contact_map.setdefault(user_bid, {"mobile": "", "email": ""})
        identifier = str(credential.identifier or "").strip()
        if (
            credential.provider_name == "phone"
            and not resolved["mobile"]
            and identifier
        ):
            resolved["mobile"] = identifier
        if (
            credential.provider_name in {"email", "google"}
            and not resolved["email"]
            and identifier
        ):
            resolved["email"] = identifier

    users = (
        UserEntity.query.filter(
            UserEntity.user_bid.in_(normalized_user_bids),
            UserEntity.deleted == 0,
        )
        .order_by(UserEntity.id.asc())
        .all()
    )
    for user in users:
        user_bid = str(user.user_bid or "").strip()
        if not user_bid:
            continue
        resolved = contact_map.setdefault(user_bid, {"mobile": "", "email": ""})
        identify = str(user.user_identify or "").strip()
        if len(identify) == 11 and identify.isdigit() and not resolved["mobile"]:
            resolved["mobile"] = identify
        elif "@" in identify and not resolved["email"]:
            resolved["email"] = identify
    return contact_map


def _load_user_map(user_bids: Sequence[str]) -> Dict[str, Dict[str, str]]:
    if not user_bids:
        return {}

    credentials = (
        AuthCredential.query.filter(
            AuthCredential.user_bid.in_(list(user_bids)),
            AuthCredential.provider_name.in_(["phone", "email", "google"]),
            AuthCredential.deleted == 0,
        )
        .order_by(AuthCredential.id.desc())
        .all()
    )
    phone_map: Dict[str, str] = {}
    email_map: Dict[str, str] = {}
    for credential in credentials:
        user_bid = credential.user_bid or ""
        if not user_bid:
            continue
        if credential.provider_name == "phone" and user_bid not in phone_map:
            phone_map[user_bid] = credential.identifier or ""
        if (
            credential.provider_name in {"email", "google"}
            and user_bid not in email_map
        ):
            email_map[user_bid] = credential.identifier or ""

    users = (
        UserEntity.query.filter(
            UserEntity.user_bid.in_(list(user_bids)),
            UserEntity.deleted == 0,
        )
        .order_by(UserEntity.id.asc())
        .all()
    )
    user_map: Dict[str, Dict[str, str]] = {}
    for user in users:
        mobile = phone_map.get(user.user_bid, "")
        email = email_map.get(user.user_bid, "")
        identify = user.user_identify or ""
        if not mobile and identify.isdigit():
            mobile = identify
        if not email and "@" in identify:
            email = identify
        user_map[user.user_bid] = {
            "mobile": mobile or "",
            "email": email or "",
            "identify": identify,
            "nickname": user.nickname or "",
        }
    return user_map


def _resolve_course_user_role(
    *,
    is_creator: bool,
    is_operator: bool,
    is_student: bool,
) -> str:
    if is_operator:
        return COURSE_USER_ROLE_OPERATOR
    if is_creator:
        return COURSE_USER_ROLE_CREATOR
    if is_student:
        return COURSE_USER_ROLE_STUDENT
    return COURSE_USER_ROLE_NORMAL


def _resolve_course_user_learning_status(
    *,
    learned_lesson_count: int,
    total_lesson_count: int,
) -> str:
    if total_lesson_count > 0 and learned_lesson_count >= total_lesson_count:
        return COURSE_USER_LEARNING_STATUS_COMPLETED
    if learned_lesson_count > 0:
        return COURSE_USER_LEARNING_STATUS_LEARNING
    return COURSE_USER_LEARNING_STATUS_NOT_STARTED


def _build_course_order_amount_expr():
    return case(
        (Order.paid_price > 0, Order.paid_price),
        (Order.payable_price > 0, Order.payable_price),
        else_=0,
    )


def _find_matching_creator_bids(keyword: str) -> Optional[Set[str]]:
    normalized = _normalize_identifier(keyword)
    if not normalized:
        return None

    user_bids = {
        row[0]
        for row in db.session.query(UserEntity.user_bid)
        .filter(
            UserEntity.deleted == 0,
            or_(
                UserEntity.user_bid == normalized,
                UserEntity.user_identify == normalized,
            ),
        )
        .all()
        if row and row[0]
    }

    credential_rows = (
        db.session.query(AuthCredential.user_bid)
        .filter(
            AuthCredential.deleted == 0,
            AuthCredential.provider_name.in_(["phone", "email"]),
            AuthCredential.identifier == normalized,
        )
        .all()
    )
    for row in credential_rows:
        if row and row[0]:
            user_bids.add(row[0])

    return user_bids


def _load_operator_user_last_login_map(
    user_bids: Sequence[str],
) -> Dict[str, datetime]:
    normalized_user_bids = [
        str(user_bid or "").strip() for user_bid in user_bids if user_bid
    ]
    if not normalized_user_bids:
        return {}

    rows = (
        db.session.query(
            UserToken.user_id.label("user_bid"),
            db.func.max(UserToken.created).label("last_login_at"),
        )
        .filter(
            UserToken.user_id.in_(normalized_user_bids),
            UserToken.token != "",
        )
        .group_by(UserToken.user_id)
        .all()
    )
    return {
        str(user_bid or "").strip(): last_login_at
        for user_bid, last_login_at in rows
        if str(user_bid or "").strip() and last_login_at
    }


def _is_operator_visible_course(course) -> bool:
    return bool(course.shifu_bid) and not is_builtin_demo_course(
        shifu_bid=course.shifu_bid,
        title=course.title,
        created_user_bid=course.created_user_bid,
    )


def _merge_courses(
    drafts: Iterable[DraftShifu],
    published: Iterable[PublishedShifu],
):
    course_map = {}
    published_bids: Set[str] = set()
    selected_sources: Dict[str, str] = {}
    for course in drafts:
        visible = _is_operator_visible_course(course)
        if visible:
            course_map[course.shifu_bid] = course
            selected_sources[course.shifu_bid] = "draft"
    for course in published:
        visible = _is_operator_visible_course(course)
        if visible:
            published_bids.add(course.shifu_bid)
        if visible and course.shifu_bid not in course_map:
            course_map[course.shifu_bid] = course
            selected_sources[course.shifu_bid] = "published"
    return (
        sorted(
            course_map.values(),
            key=lambda item: (
                item.updated_at or datetime.min,
                item.created_at or datetime.min,
                item.shifu_bid or "",
            ),
            reverse=True,
        ),
        published_bids,
        selected_sources,
    )


def _load_latest_course_versions(
    shifu_bid: str,
) -> tuple[Optional[DraftShifu], Optional[PublishedShifu]]:
    draft = (
        DraftShifu.query.filter(
            DraftShifu.shifu_bid == shifu_bid,
            DraftShifu.deleted == 0,
        )
        .order_by(DraftShifu.id.desc())
        .first()
    )
    published = (
        PublishedShifu.query.filter(
            PublishedShifu.shifu_bid == shifu_bid,
            PublishedShifu.deleted == 0,
        )
        .order_by(PublishedShifu.id.desc())
        .first()
    )
    return draft, published


def _load_operator_course_detail_source(shifu_bid: str):
    draft, published = _load_latest_course_versions(shifu_bid)
    visible_draft = draft if draft and _is_operator_visible_course(draft) else None
    visible_published = (
        published if published and _is_operator_visible_course(published) else None
    )
    if visible_draft is None and visible_published is None:
        return None
    return {
        "course": visible_draft or visible_published,
        "course_status": (
            COURSE_STATUS_PUBLISHED if visible_published else COURSE_STATUS_UNPUBLISHED
        ),
        "outline_model": DraftOutlineItem if visible_draft else PublishedOutlineItem,
    }


def _load_latest_outline_items(model, shifu_bid: str):
    latest_subquery = (
        db.session.query(db.func.max(model.id).label("max_id"))
        .filter(
            model.shifu_bid == shifu_bid,
        )
        .group_by(model.outline_item_bid)
        .subquery()
    )
    rows = (
        db.session.query(model)
        .filter(
            model.id.in_(db.session.query(latest_subquery.c.max_id)),
            model.deleted == 0,
        )
        .all()
    )

    def _position_key(item) -> tuple[tuple[int, int | str], ...]:
        position = str(getattr(item, "position", "") or "").strip()
        if not position:
            return ()
        key_parts: list[tuple[int, int | str]] = []
        for part in position.split("."):
            normalized_part = part.strip()
            if not normalized_part:
                continue
            if normalized_part.isdigit():
                key_parts.append((0, int(normalized_part)))
            else:
                key_parts.append((1, normalized_part))
        return tuple(key_parts)

    return sorted(rows, key=_position_key)


def _load_operator_course_outline_items(
    shifu_bid: str,
) -> tuple[dict[str, object], list[DraftOutlineItem | PublishedOutlineItem]]:
    detail_source = _load_operator_course_detail_source(shifu_bid)
    if detail_source is None:
        raise_error("server.shifu.shifuNotFound")

    outline_model = detail_source["outline_model"]
    outline_items = _load_latest_outline_items(outline_model, shifu_bid)

    return detail_source, outline_items


def _resolve_visible_leaf_outline_bids(
    outline_items: Sequence[DraftOutlineItem | PublishedOutlineItem],
) -> list[str]:
    visible_item_bids: Set[str] = set()
    visible_parent_bids: Set[str] = set()
    for item in outline_items:
        if bool(getattr(item, "hidden", 0)):
            continue
        outline_item_bid = str(getattr(item, "outline_item_bid", "") or "").strip()
        parent_bid = str(getattr(item, "parent_bid", "") or "").strip()
        if not outline_item_bid:
            continue
        visible_item_bids.add(outline_item_bid)
        if parent_bid:
            visible_parent_bids.add(parent_bid)
    return sorted(visible_item_bids - visible_parent_bids)


def _build_course_outline_context_map(
    outline_items: Sequence[DraftOutlineItem | PublishedOutlineItem],
) -> Dict[str, Dict[str, str]]:
    outline_item_map = {
        str(getattr(item, "outline_item_bid", "") or "").strip(): item
        for item in outline_items
        if str(getattr(item, "outline_item_bid", "") or "").strip()
    }
    context_map: Dict[str, Dict[str, str]] = {}

    for outline_item_bid, item in outline_item_map.items():
        lesson_title = str(getattr(item, "title", "") or "").strip()
        lesson_outline_item_bid = outline_item_bid
        chapter_title = lesson_title
        chapter_outline_item_bid = outline_item_bid
        current_item = item
        visited_bids = {outline_item_bid}

        while current_item is not None:
            parent_bid = str(getattr(current_item, "parent_bid", "") or "").strip()
            if not parent_bid or parent_bid in visited_bids:
                break
            visited_bids.add(parent_bid)
            parent_item = outline_item_map.get(parent_bid)
            if parent_item is None:
                break
            chapter_title = str(getattr(parent_item, "title", "") or "").strip()
            chapter_outline_item_bid = parent_bid
            current_item = parent_item

        context_map[outline_item_bid] = {
            "chapter_outline_item_bid": chapter_outline_item_bid,
            "chapter_title": chapter_title,
            "lesson_outline_item_bid": lesson_outline_item_bid,
            "lesson_title": lesson_title,
        }

    return context_map
