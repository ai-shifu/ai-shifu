"""Share constants, formatting, and filter helpers for dashboard reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.common.models import raise_param_error
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity
from sqlalchemy import or_
from sqlalchemy.orm import aliased

if TYPE_CHECKING:
    from collections.abc import Sequence

    from flaskr.service.shifu.models import (
        PublishedOutlineItem,
    )
    from sqlalchemy.sql.elements import ColumnElement


@dataclass(frozen=True)
class _DashboardCourseMeta:
    shifu_bid: str
    shifu_name: str


@dataclass
class _DashboardEntryMetrics:
    learner_total: int = 0
    learner_count_map: dict[str, int] = field(default_factory=dict)
    order_count_map: dict[str, int] = field(default_factory=dict)
    order_amount_map: dict[str, Decimal] = field(default_factory=dict)
    last_active_map: dict[str, datetime] = field(default_factory=dict)
    active_course_bids: set[str] = field(default_factory=set)


DASHBOARD_COURSE_LEARNER_PAGE_SIZE_MAX = 100

DASHBOARD_COURSE_FOLLOW_UP_PAGE_SIZE_MAX = 100

DASHBOARD_COURSE_RATING_PAGE_SIZE_MAX = 100

COURSE_STATUS_PUBLISHED = "published"

COURSE_STATUS_UNPUBLISHED = "unpublished"

FOLLOW_UP_ELEMENT_TYPE_ASK = "ask"

FOLLOW_UP_ELEMENT_TYPE_ANSWER = "answer"

LEARNING_MODE_READ = "read"

LEARNING_MODE_LISTEN = "listen"

LEARNING_MODE_CLASSROOM = "classroom"

DASHBOARD_LEARNING_MODE_ORDER = (
    LEARNING_MODE_READ,
    LEARNING_MODE_LISTEN,
    LEARNING_MODE_CLASSROOM,
)


def _format_money(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)
    return format(quantized, "f")


def _format_percentage(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.00"
    return _format_money((Decimal(numerator) * Decimal(100)) / Decimal(denominator))


def _format_average_score(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{value:.1f}"


def _format_credit_value(value: Decimal) -> str:
    return _format_money(Decimal(str(value or 0)))


def _normalize_dashboard_identifier(value: str) -> str:
    normalized = str(value or "").strip()
    if "@" in normalized:
        return normalized.lower()
    return normalized


def _dashboard_learner_keyword_matches(
    *,
    keyword: str,
    nickname: str,
    mobile: str,
    email: str,
) -> bool:
    normalized_keyword = _normalize_dashboard_identifier(keyword).lower()
    if not normalized_keyword:
        return True

    normalized_nickname = str(nickname or "").strip().lower()
    normalized_mobile = str(mobile or "").strip()
    normalized_email = str(email or "").strip().lower()

    if normalized_nickname and normalized_keyword in normalized_nickname:
        return True
    if "@" in normalized_keyword:
        return bool(normalized_email) and normalized_keyword == normalized_email
    if normalized_keyword.isdigit():
        return bool(normalized_mobile) and normalized_keyword == normalized_mobile
    return False


def _build_dashboard_learner_keyword_filter(
    user_bid_column: object,
    keyword: str,
) -> ColumnElement[bool] | None:
    normalized_keyword = _normalize_dashboard_identifier(keyword).strip()
    if not normalized_keyword:
        return None

    normalized_keyword_lower = normalized_keyword.lower()
    user_alias = aliased(UserEntity)
    credential_alias = aliased(AuthCredential)
    nickname_match_exists = (
        db.session.query(user_alias.id)
        .filter(
            user_alias.user_bid == user_bid_column,
            user_alias.deleted == 0,
            user_alias.nickname.ilike(f"%{normalized_keyword_lower}%"),
        )
        .exists()
    )
    if "@" in normalized_keyword_lower:
        credential_match_exists = (
            db.session.query(credential_alias.id)
            .filter(
                credential_alias.user_bid == user_bid_column,
                credential_alias.deleted == 0,
                credential_alias.provider_name.in_(["email", "google"]),
                db.func.lower(credential_alias.identifier) == normalized_keyword_lower,
            )
            .exists()
        )
        identify_match_exists = (
            db.session.query(user_alias.id)
            .filter(
                user_alias.user_bid == user_bid_column,
                user_alias.deleted == 0,
                db.func.lower(user_alias.user_identify) == normalized_keyword_lower,
            )
            .exists()
        )
        return or_(
            nickname_match_exists,
            credential_match_exists,
            identify_match_exists,
        )

    if normalized_keyword.isdigit():
        credential_match_exists = (
            db.session.query(credential_alias.id)
            .filter(
                credential_alias.user_bid == user_bid_column,
                credential_alias.deleted == 0,
                credential_alias.provider_name == "phone",
                credential_alias.identifier == normalized_keyword,
            )
            .exists()
        )
        identify_match_exists = (
            db.session.query(user_alias.id)
            .filter(
                user_alias.user_bid == user_bid_column,
                user_alias.deleted == 0,
                user_alias.user_identify == normalized_keyword,
            )
            .exists()
        )
        return or_(
            nickname_match_exists,
            credential_match_exists,
            identify_match_exists,
        )

    return nickname_match_exists


def _resolve_dashboard_outline_keyword_match_bids(
    outline_context_map: dict[str, dict[str, str]],
    keyword: str,
) -> set[str]:
    normalized_keyword = str(keyword or "").strip().lower()
    if not normalized_keyword:
        return set()

    matched_outline_item_bids: set[str] = set()
    for outline_item_bid, context in outline_context_map.items():
        chapter_title = str(context.get("chapter_title", "") or "").lower()
        lesson_title = str(context.get("lesson_title", "") or "").lower()
        if any(
            normalized_keyword in value
            for value in [chapter_title, lesson_title]
            if value
        ):
            matched_outline_item_bids.add(str(outline_item_bid or "").strip())
    return matched_outline_item_bids


def _build_course_outline_context_map(
    outline_items: Sequence[PublishedOutlineItem],
) -> dict[str, dict[str, str]]:
    outline_item_map = {
        str(getattr(item, "outline_item_bid", "") or "").strip(): item
        for item in outline_items
        if str(getattr(item, "outline_item_bid", "") or "").strip()
    }
    context_map: dict[str, dict[str, str]] = {}

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


def _parse_dashboard_date_boundary(
    value: str | None,
    *,
    param_name: str,
    end_of_day: bool = False,
) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        parsed_date = date.fromisoformat(normalized)
    except ValueError:
        raise_param_error(param_name)
    boundary = datetime.combine(parsed_date, datetime.min.time())
    if end_of_day:
        return boundary + timedelta(days=1)
    return boundary


def _validate_dashboard_date_range(
    *,
    start_dt: datetime | None,
    end_dt_exclusive: datetime | None,
    start_param_name: str,
    end_param_name: str,
) -> None:
    if start_dt is None or end_dt_exclusive is None:
        return
    if start_dt >= end_dt_exclusive:
        raise_param_error(f"{start_param_name}/{end_param_name}")
