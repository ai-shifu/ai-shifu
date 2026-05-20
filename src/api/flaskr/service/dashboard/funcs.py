"""Query helpers for the teacher-facing analytics dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Set, Tuple

from flask import Flask
from sqlalchemy import and_, case, false, or_
from sqlalchemy.orm import aliased

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.dashboard.dtos import (
    DashboardCourseDetailBasicInfoDTO,
    DashboardCourseDetailDTO,
    DashboardCourseDetailLearnerItemDTO,
    DashboardCourseDetailLearnersDTO,
    DashboardCourseDetailMetricsDTO,
    DashboardCourseFollowUpCurrentRecordDTO,
    DashboardCourseFollowUpDetailBasicInfoDTO,
    DashboardCourseFollowUpDetailDTO,
    DashboardCourseFollowUpItemDTO,
    DashboardCourseFollowUpListDTO,
    DashboardCourseFollowUpSummaryDTO,
    DashboardCourseRatingItemDTO,
    DashboardCourseRatingListDTO,
    DashboardCourseRatingSummaryDTO,
    DashboardCourseFollowUpTimelineItemDTO,
    DashboardEntryCourseItemDTO,
    DashboardEntryDTO,
    DashboardEntrySummaryDTO,
)
from flaskr.service.learn.const import ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnLessonFeedback,
    LearnProgressRecord,
)
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_RESET,
    ORDER_STATUS_SUCCESS,
)
from flaskr.service.order.models import Order
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
)
from flaskr.service.shifu.demo_courses import is_builtin_demo_course
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity
from flaskr.util.timezone import format_with_app_timezone, serialize_with_app_timezone


@dataclass(frozen=True)
class _DashboardCourseMeta:
    shifu_bid: str
    shifu_name: str


@dataclass
class _DashboardEntryMetrics:
    learner_total: int = 0
    learner_count_map: Dict[str, int] = field(default_factory=dict)
    order_count_map: Dict[str, int] = field(default_factory=dict)
    order_amount_map: Dict[str, Decimal] = field(default_factory=dict)
    last_active_map: Dict[str, datetime] = field(default_factory=dict)
    active_course_bids: Set[str] = field(default_factory=set)


DASHBOARD_COURSE_LEARNER_PAGE_SIZE_MAX = 100
DASHBOARD_COURSE_FOLLOW_UP_PAGE_SIZE_MAX = 100
DASHBOARD_COURSE_RATING_PAGE_SIZE_MAX = 100
COURSE_STATUS_PUBLISHED = "published"
COURSE_STATUS_UNPUBLISHED = "unpublished"


def _format_money(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)
    return format(quantized, "f")


def _format_percentage(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.00"
    return _format_money((Decimal(numerator) * Decimal("100")) / Decimal(denominator))


def _format_average_score(value: Optional[Decimal]) -> str:
    if value is None:
        return ""
    return "{0:.1f}".format(value)


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
    user_bid_column,
    keyword: str,
):
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
    outline_context_map: Dict[str, Dict[str, str]],
    keyword: str,
) -> Set[str]:
    normalized_keyword = str(keyword or "").strip().lower()
    if not normalized_keyword:
        return set()

    matched_outline_item_bids: Set[str] = set()
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


def _build_course_follow_up_base_subquery(shifu_bid: str):
    return (
        db.session.query(
            LearnGeneratedBlock.id.label("id"),
            LearnGeneratedBlock.generated_block_bid.label("generated_block_bid"),
            LearnGeneratedBlock.progress_record_bid.label("progress_record_bid"),
            LearnGeneratedBlock.user_bid.label("user_bid"),
            LearnGeneratedBlock.outline_item_bid.label("outline_item_bid"),
            LearnGeneratedBlock.generated_content.label("follow_up_content"),
            LearnGeneratedBlock.created_at.label("created_at"),
            db.func.row_number()
            .over(
                partition_by=LearnGeneratedBlock.progress_record_bid,
                order_by=(
                    LearnGeneratedBlock.created_at.asc(),
                    LearnGeneratedBlock.id.asc(),
                ),
            )
            .label("turn_index"),
        )
        .filter(
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.role == ROLE_STUDENT,
        )
        .subquery()
    )


def _build_follow_up_user_keyword_filter(
    user_bid_column,
    keyword: str,
):
    normalized = _normalize_dashboard_identifier(keyword)
    if not normalized:
        return None

    credential_match_exists = (
        db.session.query(AuthCredential.id)
        .filter(
            AuthCredential.user_bid == user_bid_column,
            AuthCredential.deleted == 0,
            AuthCredential.provider_name.in_(["phone", "email", "google"]),
            AuthCredential.identifier.ilike(f"%{normalized}%"),
        )
        .exists()
    )

    user_filters = [UserEntity.nickname.ilike(f"%{normalized}%")]
    if "@" in normalized or normalized.isdigit():
        user_filters.append(UserEntity.user_identify.ilike(f"%{normalized}%"))

    user_match_exists = (
        db.session.query(UserEntity.id)
        .filter(
            UserEntity.user_bid == user_bid_column,
            UserEntity.deleted == 0,
            or_(*user_filters),
        )
        .exists()
    )

    return or_(credential_match_exists, user_match_exists)


def _resolve_follow_up_matching_outline_bids(
    outline_context_map: Dict[str, Dict[str, str]],
    chapter_keyword: str,
) -> Optional[Set[str]]:
    normalized_keyword = str(chapter_keyword or "").strip().lower()
    if not normalized_keyword:
        return None

    return {
        outline_item_bid
        for outline_item_bid, context in outline_context_map.items()
        if normalized_keyword
        in str(context.get("chapter_title", "") or "").strip().lower()
        or normalized_keyword
        in str(context.get("lesson_title", "") or "").strip().lower()
    }


def _resolve_follow_up_answer_block(
    blocks: Sequence[LearnGeneratedBlock],
    index: int,
) -> LearnGeneratedBlock | None:
    ask_position = int(blocks[index].position or 0)
    for next_block in blocks[index + 1 :]:
        next_block_type = int(next_block.type or 0)
        next_block_role = int(next_block.role or 0)
        if (
            next_block_type == BLOCK_TYPE_MDASK_VALUE
            and next_block_role == ROLE_STUDENT
        ):
            return None
        if next_block_type == BLOCK_TYPE_MDANSWER_VALUE:
            return next_block
        if (
            next_block_type == BLOCK_TYPE_MDCONTENT_VALUE
            and next_block_role == ROLE_TEACHER
            and int(next_block.position or 0) == ask_position
        ):
            return next_block
    return None


def _resolve_follow_up_answer_content(block: LearnGeneratedBlock | None) -> str:
    if block is None:
        return ""

    generated_content = str(getattr(block, "generated_content", "") or "").strip()
    if generated_content:
        return generated_content

    return str(getattr(block, "block_content_conf", "") or "").strip()


def _load_follow_up_groups_for_progress_record(
    progress_record_bid: str,
) -> list[dict[str, LearnGeneratedBlock | None]]:
    normalized_progress_record_bid = str(progress_record_bid or "").strip()
    if not normalized_progress_record_bid:
        return []

    blocks = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.progress_record_bid == normalized_progress_record_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            or_(
                and_(
                    LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
                    LearnGeneratedBlock.role == ROLE_STUDENT,
                ),
                LearnGeneratedBlock.type == BLOCK_TYPE_MDANSWER_VALUE,
                and_(
                    LearnGeneratedBlock.type == BLOCK_TYPE_MDCONTENT_VALUE,
                    LearnGeneratedBlock.role == ROLE_TEACHER,
                ),
            ),
        )
        .order_by(LearnGeneratedBlock.created_at.asc(), LearnGeneratedBlock.id.asc())
        .all()
    )
    groups: list[dict[str, LearnGeneratedBlock | None]] = []
    for index, block in enumerate(blocks):
        if (
            int(block.type or 0) != BLOCK_TYPE_MDASK_VALUE
            or int(block.role or 0) != ROLE_STUDENT
        ):
            continue
        groups.append(
            {
                "ask_block": block,
                "answer_block": _resolve_follow_up_answer_block(blocks, index),
            }
        )
    return groups


def _load_dashboard_course_user_contact_map(
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


def _load_dashboard_course_meta_map(user_id: str) -> Dict[str, _DashboardCourseMeta]:
    owned_rows = (
        db.session.query(PublishedShifu.shifu_bid)
        .filter(
            PublishedShifu.created_user_bid == user_id,
            PublishedShifu.deleted == 0,
        )
        .distinct()
        .all()
    )
    owned_bids = {str(row[0]).strip() for row in owned_rows if str(row[0]).strip()}
    all_bids = {
        bid
        for bid in owned_bids
        if not is_builtin_demo_course(
            shifu_bid=bid,
            title="",
            created_user_bid="",
        )
    }
    if not all_bids:
        return {}

    latest_subquery = (
        db.session.query(db.func.max(PublishedShifu.id).label("max_id"))
        .filter(
            PublishedShifu.shifu_bid.in_(list(all_bids)),
            PublishedShifu.deleted == 0,
        )
        .group_by(PublishedShifu.shifu_bid)
    ).subquery()

    published_rows: List[PublishedShifu] = (
        db.session.query(PublishedShifu)
        .filter(PublishedShifu.id.in_(db.session.query(latest_subquery.c.max_id)))
        .all()
    )
    course_map: Dict[str, _DashboardCourseMeta] = {}
    for row in published_rows:
        shifu_bid = str(row.shifu_bid or "").strip()
        if not shifu_bid:
            continue
        title = str(row.title or "").strip()
        created_user_bid = str(row.created_user_bid or "").strip()
        if is_builtin_demo_course(
            shifu_bid=shifu_bid,
            title=title,
            created_user_bid=created_user_bid,
        ):
            continue
        course_map[shifu_bid] = _DashboardCourseMeta(
            shifu_bid=shifu_bid,
            shifu_name=title,
        )
    return course_map


def _load_dashboard_course_meta(
    user_id: str,
    shifu_bid: str,
) -> Optional[_DashboardCourseMeta]:
    normalized_user_id = str(user_id or "").strip()
    normalized_shifu_bid = str(shifu_bid or "").strip()
    if not normalized_user_id or not normalized_shifu_bid:
        return None

    latest_row: Optional[PublishedShifu] = (
        PublishedShifu.query.filter(
            PublishedShifu.shifu_bid == normalized_shifu_bid,
            PublishedShifu.created_user_bid == normalized_user_id,
            PublishedShifu.deleted == 0,
        )
        .order_by(PublishedShifu.id.desc())
        .first()
    )
    if latest_row is None:
        return None

    title = str(latest_row.title or "").strip()
    created_user_bid = str(latest_row.created_user_bid or "").strip()
    if is_builtin_demo_course(
        shifu_bid=normalized_shifu_bid,
        title=title,
        created_user_bid=created_user_bid,
    ):
        return None

    return _DashboardCourseMeta(
        shifu_bid=normalized_shifu_bid,
        shifu_name=title,
    )


def _load_dashboard_entry_courses(
    user_id: str,
    *,
    keyword: Optional[str] = None,
) -> List[_DashboardCourseMeta]:
    courses = list(_load_dashboard_course_meta_map(user_id).values())
    normalized_keyword = str(keyword or "").strip().lower()
    if normalized_keyword:
        courses = [
            course
            for course in courses
            if normalized_keyword in course.shifu_bid.lower()
            or normalized_keyword in course.shifu_name.lower()
        ]
    courses.sort(key=lambda item: (item.shifu_name.lower(), item.shifu_bid))
    return courses


def _load_dashboard_course_created_at(shifu_bid: str) -> Optional[datetime]:
    latest_draft: Optional[DraftShifu] = (
        DraftShifu.query.filter(
            DraftShifu.shifu_bid == shifu_bid,
            DraftShifu.deleted == 0,
        )
        .order_by(DraftShifu.id.desc())
        .first()
    )
    if latest_draft and latest_draft.created_at:
        return latest_draft.created_at

    earliest_published_created_at = (
        db.session.query(db.func.min(PublishedShifu.created_at))
        .filter(PublishedShifu.shifu_bid == shifu_bid)
        .scalar()
    )
    return earliest_published_created_at


def _resolve_dashboard_course_status(shifu_bid: str) -> str:
    published_exists = (
        db.session.query(PublishedShifu.id)
        .filter(
            PublishedShifu.shifu_bid == shifu_bid,
            PublishedShifu.deleted == 0,
        )
        .first()
        is not None
    )
    if published_exists:
        return COURSE_STATUS_PUBLISHED
    return COURSE_STATUS_UNPUBLISHED


def _load_dashboard_course_outline_items(
    shifu_bid: str,
) -> List[PublishedOutlineItem]:
    return (
        PublishedOutlineItem.query.filter(
            PublishedOutlineItem.shifu_bid == shifu_bid,
            PublishedOutlineItem.deleted == 0,
            PublishedOutlineItem.hidden == 0,
        )
        .order_by(
            PublishedOutlineItem.created_at.asc(),
            PublishedOutlineItem.id.asc(),
        )
        .all()
    )


def _format_dashboard_datetime_display(
    app: Flask,
    value: Optional[datetime],
    timezone_name: Optional[str],
) -> str:
    return (
        format_with_app_timezone(
            app,
            value,
            "%Y-%m-%d %H:%M:%S",
            timezone_name,
        )
        or ""
    )


def _load_course_leaf_outline_bids(shifu_bid: str) -> List[str]:
    outline_rows = (
        db.session.query(
            PublishedOutlineItem.outline_item_bid,
            PublishedOutlineItem.parent_bid,
        )
        .filter(
            PublishedOutlineItem.shifu_bid == shifu_bid,
            PublishedOutlineItem.deleted == 0,
            PublishedOutlineItem.hidden == 0,
        )
        .all()
    )
    if not outline_rows:
        return []

    visible_bids: Set[str] = set()
    visible_parent_bids: Set[str] = set()
    for outline_item_bid, parent_bid in outline_rows:
        normalized_outline_item_bid = str(outline_item_bid or "").strip()
        normalized_parent_bid = str(parent_bid or "").strip()
        if not normalized_outline_item_bid:
            continue
        visible_bids.add(normalized_outline_item_bid)
        if normalized_parent_bid:
            visible_parent_bids.add(normalized_parent_bid)
    return sorted(
        outline_item_bid
        for outline_item_bid in visible_bids
        if outline_item_bid not in visible_parent_bids
    )


def _load_course_learner_bids(shifu_bid: str) -> Set[str]:
    learner_bids: Set[str] = set()

    progress_rows = (
        db.session.query(LearnProgressRecord.user_bid)
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .distinct()
        .all()
    )
    learner_bids.update(
        str(row[0]).strip() for row in progress_rows if str(row[0]).strip()
    )

    manual_order_rows = (
        db.session.query(Order.user_bid)
        .filter(
            Order.shifu_bid == shifu_bid,
            Order.deleted == 0,
            Order.payment_channel == "manual",
            Order.status == ORDER_STATUS_SUCCESS,
        )
        .distinct()
        .all()
    )
    learner_bids.update(
        str(row[0]).strip() for row in manual_order_rows if str(row[0]).strip()
    )
    return learner_bids


def _load_dashboard_course_user_map(
    user_bids: Sequence[str],
) -> Dict[str, UserEntity]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    if not normalized_user_bids:
        return {}

    users = (
        UserEntity.query.filter(
            UserEntity.user_bid.in_(normalized_user_bids),
            UserEntity.deleted == 0,
        )
        .order_by(UserEntity.id.desc())
        .all()
    )
    return {
        str(user.user_bid or "").strip(): user
        for user in users
        if str(user.user_bid or "").strip()
    }


def _load_dashboard_course_last_learning_map(
    shifu_bid: str,
    user_bids: Sequence[str],
) -> Dict[str, datetime]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    if not normalized_user_bids:
        return {}

    rows = (
        db.session.query(
            LearnProgressRecord.user_bid,
            db.func.max(LearnProgressRecord.updated_at).label("last_learning_at"),
        )
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.user_bid.in_(normalized_user_bids),
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .group_by(LearnProgressRecord.user_bid)
        .all()
    )
    return {
        str(user_bid or "").strip(): last_learning_at
        for user_bid, last_learning_at in rows
        if str(user_bid or "").strip() and last_learning_at
    }


def _load_dashboard_course_joined_at_map(
    shifu_bid: str,
    user_bids: Sequence[str],
) -> Dict[str, datetime]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    if not normalized_user_bids:
        return {}

    joined_at_map: Dict[str, datetime] = {}

    def _merge_rows(rows: Sequence[tuple[str, Optional[datetime]]]) -> None:
        for user_bid, joined_at in rows:
            normalized_user_bid = str(user_bid or "").strip()
            if not normalized_user_bid or not joined_at:
                continue
            current = joined_at_map.get(normalized_user_bid)
            if current is None or joined_at < current:
                joined_at_map[normalized_user_bid] = joined_at

    _merge_rows(
        db.session.query(
            Order.user_bid,
            db.func.min(Order.created_at).label("joined_at"),
        )
        .filter(
            Order.shifu_bid == shifu_bid,
            Order.user_bid.in_(normalized_user_bids),
            Order.deleted == 0,
            Order.status == ORDER_STATUS_SUCCESS,
        )
        .group_by(Order.user_bid)
        .all()
    )
    _merge_rows(
        db.session.query(
            AiCourseAuth.user_id,
            db.func.min(
                db.func.coalesce(AiCourseAuth.updated_at, AiCourseAuth.created_at)
            ).label("joined_at"),
        )
        .filter(
            AiCourseAuth.course_id == shifu_bid,
            AiCourseAuth.user_id.in_(normalized_user_bids),
            AiCourseAuth.status == 1,
        )
        .group_by(AiCourseAuth.user_id)
        .all()
    )
    _merge_rows(
        db.session.query(
            LearnProgressRecord.user_bid,
            db.func.min(LearnProgressRecord.created_at).label("joined_at"),
        )
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.user_bid.in_(normalized_user_bids),
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .group_by(LearnProgressRecord.user_bid)
        .all()
    )
    return joined_at_map


def _load_dashboard_course_learned_lesson_count_map(
    shifu_bid: str,
    user_bids: Sequence[str],
    leaf_outline_bids: Sequence[str],
) -> Dict[str, int]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    normalized_leaf_outline_bids = [
        str(outline_item_bid or "").strip()
        for outline_item_bid in leaf_outline_bids
        if str(outline_item_bid or "").strip()
    ]
    if not normalized_user_bids or not normalized_leaf_outline_bids:
        return {}

    rows = (
        db.session.query(
            LearnProgressRecord.user_bid,
            db.func.count(db.func.distinct(LearnProgressRecord.outline_item_bid)).label(
                "learned_lesson_count"
            ),
        )
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.user_bid.in_(normalized_user_bids),
            LearnProgressRecord.outline_item_bid.in_(normalized_leaf_outline_bids),
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .group_by(LearnProgressRecord.user_bid)
        .all()
    )
    return {
        str(user_bid or "").strip(): int(learned_lesson_count or 0)
        for user_bid, learned_lesson_count in rows
        if str(user_bid or "").strip()
    }


def _load_dashboard_course_follow_up_count_map(
    shifu_bid: str,
    user_bids: Sequence[str],
) -> Dict[str, int]:
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    if not normalized_user_bids:
        return {}

    rows = (
        db.session.query(
            LearnGeneratedBlock.user_bid,
            db.func.count(LearnGeneratedBlock.id).label("follow_up_count"),
        )
        .filter(
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.user_bid.in_(normalized_user_bids),
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.role == ROLE_STUDENT,
        )
        .group_by(LearnGeneratedBlock.user_bid)
        .all()
    )
    return {
        str(user_bid or "").strip(): int(follow_up_count or 0)
        for user_bid, follow_up_count in rows
        if str(user_bid or "").strip()
    }


def _resolve_dashboard_course_learning_status(
    *,
    learned_lesson_count: int,
    total_lesson_count: int,
) -> str:
    if total_lesson_count > 0 and learned_lesson_count >= total_lesson_count:
        return "completed"
    if learned_lesson_count > 0:
        return "learning"
    return "not_started"


def _count_completed_learners(shifu_bid: str, leaf_outline_bids: List[str]) -> int:
    if not leaf_outline_bids:
        return 0

    progress_rows = (
        db.session.query(
            LearnProgressRecord.user_bid,
            LearnProgressRecord.outline_item_bid,
            LearnProgressRecord.status,
        )
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid.in_(leaf_outline_bids),
            LearnProgressRecord.deleted == 0,
        )
        .order_by(
            LearnProgressRecord.user_bid.asc(),
            LearnProgressRecord.outline_item_bid.asc(),
            LearnProgressRecord.created_at.asc(),
            LearnProgressRecord.id.asc(),
        )
        .all()
    )

    completed_leaf_bids_by_user: Dict[str, Set[str]] = {}
    records_by_user_and_outline: Dict[Tuple[str, str], List[int]] = {}

    for user_bid, outline_item_bid, status in progress_rows:
        normalized_user_bid = str(user_bid or "").strip()
        normalized_outline_item_bid = str(outline_item_bid or "").strip()
        if not normalized_user_bid or not normalized_outline_item_bid:
            continue

        record_statuses = records_by_user_and_outline.setdefault(
            (normalized_user_bid, normalized_outline_item_bid),
            [],
        )
        record_statuses.append(int(status or 0))

    for (
        user_bid,
        outline_item_bid,
    ), record_statuses in records_by_user_and_outline.items():
        has_completed_record = any(
            record_status == LEARN_STATUS_COMPLETED for record_status in record_statuses
        )
        has_reset_with_follow_up_record = any(
            record_status == LEARN_STATUS_RESET
            for record_status in record_statuses[:-1]
        )
        if not has_completed_record and not has_reset_with_follow_up_record:
            continue

        completed_outline_bids = completed_leaf_bids_by_user.setdefault(
            user_bid,
            set(),
        )
        completed_outline_bids.add(outline_item_bid)

    leaf_count = len(leaf_outline_bids)
    return sum(
        1
        for completed_outline_bids in completed_leaf_bids_by_user.values()
        if len(completed_outline_bids) >= leaf_count
    )


def _collect_dashboard_entry_metrics(
    shifu_bids: List[str],
    *,
    start_dt: Optional[datetime],
    end_dt_exclusive: Optional[datetime],
) -> _DashboardEntryMetrics:
    if not shifu_bids:
        return _DashboardEntryMetrics()

    learner_users_by_course: Dict[str, Set[str]] = {}

    def _collect_learner(shifu_bid: object, user_bid: object) -> None:
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_user_bid = str(user_bid or "").strip()
        if not normalized_shifu_bid or not normalized_user_bid:
            return
        learners = learner_users_by_course.setdefault(normalized_shifu_bid, set())
        learners.add(normalized_user_bid)

    progress_learner_query = db.session.query(
        LearnProgressRecord.shifu_bid.label("shifu_bid"),
        LearnProgressRecord.user_bid.label("user_bid"),
    ).filter(
        LearnProgressRecord.shifu_bid.in_(shifu_bids),
        LearnProgressRecord.deleted == 0,
        LearnProgressRecord.status != LEARN_STATUS_RESET,
    )
    if start_dt is not None:
        progress_learner_query = progress_learner_query.filter(
            LearnProgressRecord.created_at >= start_dt
        )
    if end_dt_exclusive is not None:
        progress_learner_query = progress_learner_query.filter(
            LearnProgressRecord.created_at < end_dt_exclusive
        )
    progress_learner_rows = progress_learner_query.distinct().all()
    for shifu_bid, user_bid in progress_learner_rows:
        _collect_learner(shifu_bid, user_bid)

    manual_import_learner_query = db.session.query(
        Order.shifu_bid.label("shifu_bid"),
        Order.user_bid.label("user_bid"),
    ).filter(
        Order.shifu_bid.in_(shifu_bids),
        Order.deleted == 0,
        Order.payment_channel == "manual",
        Order.status == ORDER_STATUS_SUCCESS,
    )
    if start_dt is not None:
        manual_import_learner_query = manual_import_learner_query.filter(
            Order.created_at >= start_dt
        )
    if end_dt_exclusive is not None:
        manual_import_learner_query = manual_import_learner_query.filter(
            Order.created_at < end_dt_exclusive
        )
    manual_import_rows = manual_import_learner_query.distinct().all()
    for shifu_bid, user_bid in manual_import_rows:
        _collect_learner(shifu_bid, user_bid)

    learner_count_map: Dict[str, int] = {}
    learner_total_users: Set[str] = set()
    for shifu_bid, learner_bids in learner_users_by_course.items():
        learner_count_map[shifu_bid] = len(learner_bids)
        learner_total_users.update(learner_bids)
    learner_total = len(learner_total_users)

    order_query = db.session.query(
        Order.shifu_bid.label("shifu_bid"),
        db.func.count(Order.id).label("order_count"),
        db.func.coalesce(db.func.sum(Order.paid_price), 0).label("order_amount"),
    ).filter(
        Order.shifu_bid.in_(shifu_bids),
        Order.deleted == 0,
        Order.status == ORDER_STATUS_SUCCESS,
    )
    if start_dt is not None:
        order_query = order_query.filter(Order.created_at >= start_dt)
    if end_dt_exclusive is not None:
        order_query = order_query.filter(Order.created_at < end_dt_exclusive)
    order_rows = order_query.group_by(Order.shifu_bid).all()
    order_count_map: Dict[str, int] = {}
    order_amount_map: Dict[str, Decimal] = {}
    for shifu_bid, order_count, order_amount in order_rows:
        if not shifu_bid:
            continue
        normalized_shifu_bid = str(shifu_bid)
        order_count_map[normalized_shifu_bid] = int(order_count or 0)
        order_amount_map[normalized_shifu_bid] = Decimal(str(order_amount or 0))

    last_active_query = db.session.query(
        LearnProgressRecord.shifu_bid.label("shifu_bid"),
        db.func.max(LearnProgressRecord.updated_at).label("last_active"),
    ).filter(
        LearnProgressRecord.shifu_bid.in_(shifu_bids),
        LearnProgressRecord.deleted == 0,
    )
    if start_dt is not None:
        last_active_query = last_active_query.filter(
            LearnProgressRecord.updated_at >= start_dt
        )
    if end_dt_exclusive is not None:
        last_active_query = last_active_query.filter(
            LearnProgressRecord.updated_at < end_dt_exclusive
        )

    last_active_rows = last_active_query.group_by(LearnProgressRecord.shifu_bid).all()
    last_active_map: Dict[str, datetime] = {}
    for shifu_bid, last_active in last_active_rows:
        if not shifu_bid or not last_active:
            continue
        last_active_map[str(shifu_bid)] = last_active

    active_course_bids = (
        set(learner_count_map.keys())
        .union(order_count_map.keys())
        .union(order_amount_map.keys())
    )
    return _DashboardEntryMetrics(
        learner_total=learner_total,
        learner_count_map=learner_count_map,
        order_count_map=order_count_map,
        order_amount_map=order_amount_map,
        last_active_map=last_active_map,
        active_course_bids=active_course_bids,
    )


def build_dashboard_entry(
    app: Flask,
    user_id: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    keyword: Optional[str] = None,
    page_index: int = 1,
    page_size: int = 20,
    timezone_name: Optional[str] = None,
) -> DashboardEntryDTO:
    def _parse_optional_date(raw: Optional[str]) -> Optional[date]:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            raise_param_error(f"invalid date: {text}")

    with app.app_context():
        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = max(int(page_size or 20), 1)
        safe_page_size = min(safe_page_size, 100)

        parsed_start = _parse_optional_date(start_date)
        parsed_end = _parse_optional_date(end_date)
        if parsed_start is None and parsed_end is None:
            start_dt, end_dt_exclusive = None, None
        else:
            resolved_end = parsed_end or date.today()
            resolved_start = parsed_start or (resolved_end - timedelta(days=13))
            if resolved_start > resolved_end:
                raise_param_error("start_date must be <= end_date")
            if (resolved_end - resolved_start).days + 1 > 366:
                raise_param_error("date range too large (max 366 days)")
            start_dt = datetime.combine(resolved_start, datetime.min.time())
            end_dt_exclusive = datetime.combine(
                resolved_end + timedelta(days=1),
                datetime.min.time(),
            )

        courses = _load_dashboard_entry_courses(user_id, keyword=keyword)
        total = len(courses)
        if total == 0:
            return DashboardEntryDTO(
                summary=DashboardEntrySummaryDTO(
                    course_count=0,
                    learner_count=0,
                    order_count=0,
                    order_amount="0.00",
                ),
                page=safe_page_index,
                page_size=safe_page_size,
                page_count=0,
                total=0,
                items=[],
            )

        shifu_bids = [course.shifu_bid for course in courses]
        metrics = _collect_dashboard_entry_metrics(
            shifu_bids,
            start_dt=start_dt,
            end_dt_exclusive=end_dt_exclusive,
        )
        has_date_filter = start_dt is not None or end_dt_exclusive is not None
        if has_date_filter:
            courses = [
                item for item in courses if item.shifu_bid in metrics.active_course_bids
            ]
            total = len(courses)
            if total == 0:
                return DashboardEntryDTO(
                    summary=DashboardEntrySummaryDTO(
                        course_count=0,
                        learner_count=0,
                        order_count=0,
                        order_amount="0.00",
                    ),
                    page=safe_page_index,
                    page_size=safe_page_size,
                    page_count=0,
                    total=0,
                    items=[],
                )

        page_count = (total + safe_page_size - 1) // safe_page_size
        resolved_page = min(safe_page_index, max(page_count, 1))
        offset = (resolved_page - 1) * safe_page_size
        page_courses = courses[offset : offset + safe_page_size]

        items: List[DashboardEntryCourseItemDTO] = []
        for course in page_courses:
            shifu_bid = course.shifu_bid
            last_active = metrics.last_active_map.get(shifu_bid)
            items.append(
                DashboardEntryCourseItemDTO(
                    shifu_bid=shifu_bid,
                    shifu_name=course.shifu_name,
                    learner_count=metrics.learner_count_map.get(shifu_bid, 0),
                    order_count=metrics.order_count_map.get(shifu_bid, 0),
                    order_amount=_format_money(
                        metrics.order_amount_map.get(shifu_bid, Decimal("0"))
                    ),
                    last_active_at=serialize_with_app_timezone(
                        app,
                        last_active,
                        timezone_name,
                    )
                    or "",
                    last_active_at_display=format_with_app_timezone(
                        app,
                        last_active,
                        "%Y-%m-%d %H:%M:%S",
                        timezone_name,
                    )
                    or "",
                )
            )

        total_order_amount = Decimal("0")
        for value in metrics.order_amount_map.values():
            total_order_amount += value

        return DashboardEntryDTO(
            summary=DashboardEntrySummaryDTO(
                course_count=total,
                learner_count=metrics.learner_total,
                order_count=sum(metrics.order_count_map.values()),
                order_amount=_format_money(total_order_amount),
            ),
            page=resolved_page,
            page_size=safe_page_size,
            page_count=page_count,
            total=total,
            items=items,
        )


def _build_dashboard_course_learners(
    app: Flask,
    *,
    shifu_bid: str,
    learner_bids: Sequence[str],
    leaf_outline_bids: Sequence[str],
    page_index: int,
    page_size: int,
    keyword: Optional[str],
    learning_status: Optional[str],
    last_learning_start_time: Optional[str],
    last_learning_end_time: Optional[str],
    timezone_name: Optional[str],
) -> DashboardCourseDetailLearnersDTO:
    safe_page_size = min(
        max(int(page_size or 20), 1),
        DASHBOARD_COURSE_LEARNER_PAGE_SIZE_MAX,
    )
    normalized_page_index = max(int(page_index or 1), 1)
    last_learning_start_dt = _parse_dashboard_date_boundary(
        last_learning_start_time,
        param_name="last_learning_start_time",
    )
    last_learning_end_dt_exclusive = _parse_dashboard_date_boundary(
        last_learning_end_time,
        param_name="last_learning_end_time",
        end_of_day=True,
    )
    _validate_dashboard_date_range(
        start_dt=last_learning_start_dt,
        end_dt_exclusive=last_learning_end_dt_exclusive,
        start_param_name="last_learning_start_time",
        end_param_name="last_learning_end_time",
    )
    normalized_shifu_bid = str(shifu_bid or "").strip()
    normalized_learner_bids = sorted(
        {
            str(user_bid or "").strip()
            for user_bid in learner_bids
            if str(user_bid or "").strip()
        }
    )
    normalized_leaf_outline_bids = sorted(
        {
            str(outline_item_bid or "").strip()
            for outline_item_bid in leaf_outline_bids
            if str(outline_item_bid or "").strip()
        }
    )
    if not normalized_shifu_bid or not normalized_learner_bids:
        return DashboardCourseDetailLearnersDTO(
            page=1,
            page_size=safe_page_size,
            page_count=0,
            total=0,
            items=[],
        )

    total_lesson_count = len(normalized_leaf_outline_bids)
    normalized_learning_status = str(learning_status or "").strip().lower()
    if normalized_learning_status not in {"", "not_started", "learning", "completed"}:
        normalized_learning_status = ""

    learner_source = (
        db.session.query(
            LearnProgressRecord.user_bid.label("user_bid"),
        )
        .filter(
            LearnProgressRecord.shifu_bid == normalized_shifu_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.user_bid.in_(normalized_learner_bids),
        )
        .distinct()
        .union(
            db.session.query(
                Order.user_bid.label("user_bid"),
            )
            .filter(
                Order.shifu_bid == normalized_shifu_bid,
                Order.deleted == 0,
                Order.payment_channel == "manual",
                Order.status == ORDER_STATUS_SUCCESS,
                Order.user_bid.in_(normalized_learner_bids),
            )
            .distinct()
        )
        .subquery()
    )
    last_learning_subquery = (
        db.session.query(
            LearnProgressRecord.user_bid.label("user_bid"),
            db.func.max(LearnProgressRecord.updated_at).label("last_learning_at"),
        )
        .filter(
            LearnProgressRecord.shifu_bid == normalized_shifu_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.user_bid.in_(normalized_learner_bids),
        )
        .group_by(LearnProgressRecord.user_bid)
        .subquery()
    )
    order_joined_at_subquery = (
        db.session.query(
            Order.user_bid.label("user_bid"),
            db.func.min(Order.created_at).label("joined_at"),
        )
        .filter(
            Order.shifu_bid == normalized_shifu_bid,
            Order.deleted == 0,
            Order.status == ORDER_STATUS_SUCCESS,
            Order.user_bid.in_(normalized_learner_bids),
        )
        .group_by(Order.user_bid)
        .subquery()
    )
    auth_joined_at_subquery = (
        db.session.query(
            AiCourseAuth.user_id.label("user_bid"),
            db.func.min(
                db.func.coalesce(AiCourseAuth.updated_at, AiCourseAuth.created_at)
            ).label("joined_at"),
        )
        .filter(
            AiCourseAuth.course_id == normalized_shifu_bid,
            AiCourseAuth.user_id.in_(normalized_learner_bids),
            AiCourseAuth.status == 1,
        )
        .group_by(AiCourseAuth.user_id)
        .subquery()
    )
    progress_joined_at_subquery = (
        db.session.query(
            LearnProgressRecord.user_bid.label("user_bid"),
            db.func.min(LearnProgressRecord.created_at).label("joined_at"),
        )
        .filter(
            LearnProgressRecord.shifu_bid == normalized_shifu_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.user_bid.in_(normalized_learner_bids),
        )
        .group_by(LearnProgressRecord.user_bid)
        .subquery()
    )
    joined_at_subquery = (
        db.session.query(
            learner_source.c.user_bid.label("user_bid"),
            order_joined_at_subquery.c.joined_at.label("order_joined_at"),
            auth_joined_at_subquery.c.joined_at.label("auth_joined_at"),
            progress_joined_at_subquery.c.joined_at.label("progress_joined_at"),
        )
        .select_from(learner_source)
        .outerjoin(
            order_joined_at_subquery,
            order_joined_at_subquery.c.user_bid == learner_source.c.user_bid,
        )
        .outerjoin(
            auth_joined_at_subquery,
            auth_joined_at_subquery.c.user_bid == learner_source.c.user_bid,
        )
        .outerjoin(
            progress_joined_at_subquery,
            progress_joined_at_subquery.c.user_bid == learner_source.c.user_bid,
        )
        .subquery()
    )
    learned_lesson_count_subquery = (
        db.session.query(
            LearnProgressRecord.user_bid.label("user_bid"),
            db.func.count(db.func.distinct(LearnProgressRecord.outline_item_bid)).label(
                "learned_lesson_count"
            ),
        )
        .filter(
            LearnProgressRecord.shifu_bid == normalized_shifu_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.user_bid.in_(normalized_learner_bids),
            LearnProgressRecord.outline_item_bid.in_(normalized_leaf_outline_bids)
            if normalized_leaf_outline_bids
            else False,
        )
        .group_by(LearnProgressRecord.user_bid)
        .subquery()
    )
    follow_up_count_subquery = (
        db.session.query(
            LearnGeneratedBlock.user_bid.label("user_bid"),
            db.func.count(LearnGeneratedBlock.id).label("follow_up_count"),
        )
        .filter(
            LearnGeneratedBlock.shifu_bid == normalized_shifu_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.role == ROLE_STUDENT,
            LearnGeneratedBlock.user_bid.in_(normalized_learner_bids),
        )
        .group_by(LearnGeneratedBlock.user_bid)
        .subquery()
    )

    learned_lesson_count_expression = db.func.coalesce(
        learned_lesson_count_subquery.c.learned_lesson_count,
        0,
    )
    if total_lesson_count > 0:
        learning_status_expression = case(
            (learned_lesson_count_expression >= total_lesson_count, "completed"),
            (learned_lesson_count_expression > 0, "learning"),
            else_="not_started",
        )
    else:
        learning_status_expression = case(
            (learned_lesson_count_expression > 0, "learning"),
            else_="not_started",
        )

    joined_at_missing_filter = and_(
        joined_at_subquery.c.order_joined_at.is_(None),
        joined_at_subquery.c.auth_joined_at.is_(None),
        joined_at_subquery.c.progress_joined_at.is_(None),
    )
    joined_at_sentinel = datetime(9999, 12, 31, 23, 59, 59)
    order_joined_at_expression = db.func.coalesce(
        joined_at_subquery.c.order_joined_at,
        joined_at_sentinel,
    )
    auth_joined_at_expression = db.func.coalesce(
        joined_at_subquery.c.auth_joined_at,
        joined_at_sentinel,
    )
    progress_joined_at_expression = db.func.coalesce(
        joined_at_subquery.c.progress_joined_at,
        joined_at_sentinel,
    )
    earliest_order_or_auth_expression = case(
        (
            order_joined_at_expression <= auth_joined_at_expression,
            order_joined_at_expression,
        ),
        else_=auth_joined_at_expression,
    )
    joined_at_expression = case(
        (joined_at_missing_filter, None),
        (
            earliest_order_or_auth_expression <= progress_joined_at_expression,
            earliest_order_or_auth_expression,
        ),
        else_=progress_joined_at_expression,
    )
    filtered_query = (
        db.session.query(
            learner_source.c.user_bid.label("user_bid"),
            UserEntity.nickname.label("nickname"),
            last_learning_subquery.c.last_learning_at.label("last_learning_at"),
            joined_at_expression.label("joined_at"),
            learned_lesson_count_expression.label("learned_lesson_count"),
            db.func.coalesce(
                follow_up_count_subquery.c.follow_up_count,
                0,
            ).label("follow_up_count"),
            learning_status_expression.label("learning_status"),
        )
        .select_from(learner_source)
        .outerjoin(
            UserEntity,
            and_(
                UserEntity.user_bid == learner_source.c.user_bid,
                UserEntity.deleted == 0,
            ),
        )
        .outerjoin(
            last_learning_subquery,
            last_learning_subquery.c.user_bid == learner_source.c.user_bid,
        )
        .outerjoin(
            joined_at_subquery,
            joined_at_subquery.c.user_bid == learner_source.c.user_bid,
        )
        .outerjoin(
            follow_up_count_subquery,
            follow_up_count_subquery.c.user_bid == learner_source.c.user_bid,
        )
        .outerjoin(
            learned_lesson_count_subquery,
            learned_lesson_count_subquery.c.user_bid == learner_source.c.user_bid,
        )
    )
    keyword_filter = _build_dashboard_learner_keyword_filter(
        learner_source.c.user_bid,
        str(keyword or ""),
    )
    if keyword_filter is not None:
        filtered_query = filtered_query.filter(keyword_filter)
    if normalized_learning_status:
        filtered_query = filtered_query.filter(
            learning_status_expression == normalized_learning_status
        )
    if last_learning_start_dt is not None:
        filtered_query = filtered_query.filter(
            last_learning_subquery.c.last_learning_at >= last_learning_start_dt
        )
    if last_learning_end_dt_exclusive is not None:
        filtered_query = filtered_query.filter(
            last_learning_subquery.c.last_learning_at < last_learning_end_dt_exclusive
        )

    total = (
        db.session.query(db.func.count())
        .select_from(filtered_query.subquery())
        .scalar()
        or 0
    )
    if total == 0:
        return DashboardCourseDetailLearnersDTO(
            page=1,
            page_size=safe_page_size,
            page_count=0,
            total=0,
            items=[],
        )

    page_count = (total + safe_page_size - 1) // safe_page_size
    resolved_page = min(normalized_page_index, max(page_count, 1))
    offset = (resolved_page - 1) * safe_page_size
    page_rows = (
        filtered_query.order_by(
            last_learning_subquery.c.last_learning_at.is_(None),
            last_learning_subquery.c.last_learning_at.desc(),
            joined_at_expression.is_(None),
            joined_at_expression.desc(),
            learner_source.c.user_bid.desc(),
        )
        .offset(offset)
        .limit(safe_page_size)
        .all()
    )
    page_user_bids = [
        str(getattr(row, "user_bid", "") or "").strip()
        for row in page_rows
        if str(getattr(row, "user_bid", "") or "").strip()
    ]
    contact_map = _load_dashboard_course_user_contact_map(page_user_bids)
    paged_items = []
    for row in page_rows:
        user_bid = str(getattr(row, "user_bid", "") or "").strip()
        contact = contact_map.get(user_bid, {"mobile": "", "email": ""})
        last_learning_at = getattr(row, "last_learning_at", None)
        joined_at = getattr(row, "joined_at", None)
        paged_items.append(
            DashboardCourseDetailLearnerItemDTO(
                user_bid=user_bid,
                mobile=str(contact.get("mobile", "") or "").strip(),
                email=str(contact.get("email", "") or "").strip(),
                nickname=str(getattr(row, "nickname", "") or "").strip(),
                learned_lesson_count=int(getattr(row, "learned_lesson_count", 0) or 0),
                total_lesson_count=total_lesson_count,
                learning_status=str(getattr(row, "learning_status", "") or ""),
                follow_up_count=int(getattr(row, "follow_up_count", 0) or 0),
                last_learning_at=serialize_with_app_timezone(
                    app,
                    last_learning_at,
                    timezone_name,
                )
                or "",
                last_learning_at_display=format_with_app_timezone(
                    app,
                    last_learning_at,
                    "%Y-%m-%d %H:%M:%S",
                    timezone_name,
                )
                or "",
                joined_at=serialize_with_app_timezone(
                    app,
                    joined_at,
                    timezone_name,
                )
                or "",
                joined_at_display=format_with_app_timezone(
                    app,
                    joined_at,
                    "%Y-%m-%d %H:%M:%S",
                    timezone_name,
                )
                or "",
            )
        )
    return DashboardCourseDetailLearnersDTO(
        page=resolved_page,
        page_size=safe_page_size,
        page_count=page_count,
        total=total,
        items=paged_items,
    )


def _parse_dashboard_date_boundary(
    value: Optional[str],
    *,
    param_name: str,
    end_of_day: bool = False,
) -> Optional[datetime]:
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
    start_dt: Optional[datetime],
    end_dt_exclusive: Optional[datetime],
    start_param_name: str,
    end_param_name: str,
) -> None:
    if start_dt is None or end_dt_exclusive is None:
        return
    if start_dt >= end_dt_exclusive:
        raise_param_error(f"{start_param_name}/{end_param_name}")


def build_dashboard_course_follow_ups(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    *,
    page_index: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    user_bid: Optional[str] = None,
    chapter_keyword: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    timezone_name: Optional[str] = None,
) -> DashboardCourseFollowUpListDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        if _load_dashboard_course_meta(user_id, normalized_shifu_bid) is None:
            raise_error("server.shifu.shifuNotFound")

        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            DASHBOARD_COURSE_FOLLOW_UP_PAGE_SIZE_MAX,
        )
        outline_items = _load_dashboard_course_outline_items(normalized_shifu_bid)
        outline_context_map = _build_course_outline_context_map(outline_items)

        follow_up_base = _build_course_follow_up_base_subquery(normalized_shifu_bid)
        full_summary_row = db.session.query(
            db.func.count(follow_up_base.c.id).label("follow_up_count"),
            db.func.count(
                db.func.distinct(db.func.nullif(follow_up_base.c.user_bid, ""))
            ).label("user_count"),
            db.func.count(
                db.func.distinct(db.func.nullif(follow_up_base.c.outline_item_bid, ""))
            ).label("lesson_count"),
            db.func.max(follow_up_base.c.created_at).label("latest_follow_up_at"),
        ).one()
        full_summary = DashboardCourseFollowUpSummaryDTO(
            follow_up_count=int(getattr(full_summary_row, "follow_up_count", 0) or 0),
            user_count=int(getattr(full_summary_row, "user_count", 0) or 0),
            lesson_count=int(getattr(full_summary_row, "lesson_count", 0) or 0),
            latest_follow_up_at=_format_dashboard_datetime_display(
                app,
                getattr(full_summary_row, "latest_follow_up_at", None),
                timezone_name,
            ),
        )
        user_keyword_filter = _build_follow_up_user_keyword_filter(
            follow_up_base.c.user_bid,
            str(keyword or "").strip(),
        )
        matching_outline_item_bids = _resolve_follow_up_matching_outline_bids(
            outline_context_map,
            str(chapter_keyword or "").strip().lower(),
        )

        if chapter_keyword and not matching_outline_item_bids:
            return DashboardCourseFollowUpListDTO(
                summary=full_summary,
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )

        start_dt = _parse_dashboard_date_boundary(
            start_time,
            param_name="start_time",
        )
        end_dt_exclusive = _parse_dashboard_date_boundary(
            end_time,
            param_name="end_time",
            end_of_day=True,
        )
        _validate_dashboard_date_range(
            start_dt=start_dt,
            end_dt_exclusive=end_dt_exclusive,
            start_param_name="start_time",
            end_param_name="end_time",
        )

        filtered_query = db.session.query(follow_up_base)
        normalized_user_bid = str(user_bid or "").strip()
        if normalized_user_bid:
            filtered_query = filtered_query.filter(
                follow_up_base.c.user_bid == normalized_user_bid
            )
        if user_keyword_filter is not None:
            filtered_query = filtered_query.filter(user_keyword_filter)
        if matching_outline_item_bids is not None:
            filtered_query = filtered_query.filter(
                follow_up_base.c.outline_item_bid.in_(
                    sorted(matching_outline_item_bids)
                )
            )
        if start_dt is not None:
            filtered_query = filtered_query.filter(
                follow_up_base.c.created_at >= start_dt
            )
        if end_dt_exclusive is not None:
            filtered_query = filtered_query.filter(
                follow_up_base.c.created_at < end_dt_exclusive
            )

        filtered_follow_ups = filtered_query.subquery()
        total = db.session.query(db.func.count(filtered_follow_ups.c.id)).scalar() or 0
        if total == 0:
            return DashboardCourseFollowUpListDTO(
                summary=full_summary,
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )

        page_count = (
            (total + safe_page_size - 1) // safe_page_size if safe_page_size else 0
        )
        resolved_page = min(safe_page_index, max(page_count, 1))
        start = (resolved_page - 1) * safe_page_size
        paged_rows = (
            db.session.query(filtered_follow_ups)
            .order_by(
                filtered_follow_ups.c.created_at.desc(),
                filtered_follow_ups.c.id.desc(),
            )
            .offset(start)
            .limit(safe_page_size)
            .all()
        )
        user_bids = sorted(
            {
                str(getattr(row, "user_bid", "") or "").strip()
                for row in paged_rows
                if str(getattr(row, "user_bid", "") or "").strip()
            }
        )
        user_map = _load_dashboard_course_user_map(user_bids)
        contact_map = _load_dashboard_course_user_contact_map(user_bids)

        items: List[DashboardCourseFollowUpItemDTO] = []
        for row in paged_rows:
            generated_block_bid = str(
                getattr(row, "generated_block_bid", "") or ""
            ).strip()
            outline_item_bid = str(getattr(row, "outline_item_bid", "") or "").strip()
            user_bid = str(getattr(row, "user_bid", "") or "").strip()
            context = outline_context_map.get(
                outline_item_bid,
                {
                    "chapter_title": "",
                    "lesson_title": "",
                },
            )
            user = user_map.get(user_bid)
            contact = contact_map.get(user_bid, {})
            items.append(
                DashboardCourseFollowUpItemDTO(
                    generated_block_bid=generated_block_bid,
                    progress_record_bid=str(
                        getattr(row, "progress_record_bid", "") or ""
                    ),
                    user_bid=user_bid,
                    mobile=str(contact.get("mobile", "") or ""),
                    email=str(contact.get("email", "") or ""),
                    nickname=str(getattr(user, "nickname", "") or ""),
                    chapter_title=str(context.get("chapter_title", "") or ""),
                    lesson_title=str(context.get("lesson_title", "") or ""),
                    follow_up_content=str(getattr(row, "follow_up_content", "") or ""),
                    turn_index=int(getattr(row, "turn_index", 0) or 0),
                    created_at=_format_dashboard_datetime_display(
                        app,
                        getattr(row, "created_at", None),
                        timezone_name,
                    ),
                )
            )

        return DashboardCourseFollowUpListDTO(
            summary=full_summary,
            items=items,
            page=resolved_page,
            page_size=safe_page_size,
            total=total,
            page_count=page_count,
        )


def build_dashboard_course_follow_up_detail(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    generated_block_bid: str,
    *,
    timezone_name: Optional[str] = None,
) -> DashboardCourseFollowUpDetailDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_generated_block_bid = str(generated_block_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")
        if not normalized_generated_block_bid:
            raise_param_error("generated_block_bid is required")

        course_meta = _load_dashboard_course_meta(user_id, normalized_shifu_bid)
        if course_meta is None:
            raise_error("server.shifu.shifuNotFound")

        outline_items = _load_dashboard_course_outline_items(normalized_shifu_bid)
        outline_context_map = _build_course_outline_context_map(outline_items)
        ask_block = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.shifu_bid == normalized_shifu_bid,
                LearnGeneratedBlock.generated_block_bid
                == normalized_generated_block_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
                LearnGeneratedBlock.role == ROLE_STUDENT,
            )
            .order_by(LearnGeneratedBlock.id.desc())
            .first()
        )
        if ask_block is None:
            raise_param_error("generated_block_bid")

        progress_record_bid = str(ask_block.progress_record_bid or "").strip()
        groups = _load_follow_up_groups_for_progress_record(progress_record_bid)
        selected_group_index = next(
            (
                index
                for index, group in enumerate(groups)
                if str(group["ask_block"].generated_block_bid or "").strip()
                == normalized_generated_block_bid
            ),
            -1,
        )
        if selected_group_index < 0:
            raise_param_error("generated_block_bid")

        selected_group = groups[selected_group_index]
        user_bid = str(ask_block.user_bid or "").strip()
        user = _load_dashboard_course_user_map([user_bid]).get(user_bid)
        contact = _load_dashboard_course_user_contact_map([user_bid]).get(user_bid, {})
        context = outline_context_map.get(
            str(ask_block.outline_item_bid or "").strip(),
            {
                "chapter_title": "",
                "lesson_title": "",
            },
        )

        timeline: List[DashboardCourseFollowUpTimelineItemDTO] = []
        for index, group in enumerate(groups):
            current_ask_block = group["ask_block"]
            is_current = index == selected_group_index
            timeline.append(
                DashboardCourseFollowUpTimelineItemDTO(
                    role="student",
                    content=str(
                        getattr(current_ask_block, "generated_content", "") or ""
                    ),
                    created_at=_format_dashboard_datetime_display(
                        app,
                        getattr(current_ask_block, "created_at", None),
                        timezone_name,
                    ),
                    is_current=is_current,
                )
            )
            answer_block = group.get("answer_block")
            answer_content = _resolve_follow_up_answer_content(answer_block)
            if answer_content:
                timeline.append(
                    DashboardCourseFollowUpTimelineItemDTO(
                        role="teacher",
                        content=answer_content,
                        created_at=_format_dashboard_datetime_display(
                            app,
                            getattr(answer_block, "created_at", None),
                            timezone_name,
                        ),
                        is_current=is_current,
                    )
                )

        selected_answer_block = selected_group.get("answer_block")
        return DashboardCourseFollowUpDetailDTO(
            basic_info=DashboardCourseFollowUpDetailBasicInfoDTO(
                generated_block_bid=normalized_generated_block_bid,
                progress_record_bid=progress_record_bid,
                user_bid=user_bid,
                mobile=str(contact.get("mobile", "") or ""),
                email=str(contact.get("email", "") or ""),
                nickname=str(getattr(user, "nickname", "") or ""),
                chapter_title=str(context.get("chapter_title", "") or ""),
                lesson_title=str(context.get("lesson_title", "") or ""),
                created_at=_format_dashboard_datetime_display(
                    app,
                    getattr(ask_block, "created_at", None),
                    timezone_name,
                ),
                turn_index=selected_group_index + 1,
            ),
            current_record=DashboardCourseFollowUpCurrentRecordDTO(
                follow_up_content=str(
                    getattr(ask_block, "generated_content", "") or ""
                ),
                answer_content=_resolve_follow_up_answer_content(selected_answer_block),
            ),
            timeline=timeline,
        )


def build_dashboard_course_ratings(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    *,
    page_index: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    chapter_keyword: Optional[str] = None,
    score: Optional[str] = None,
    has_comment: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    timezone_name: Optional[str] = None,
) -> DashboardCourseRatingListDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        course_meta = _load_dashboard_course_meta(user_id, normalized_shifu_bid)
        if course_meta is None:
            raise_error("server.shifu.shifuNotFound")

        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            DASHBOARD_COURSE_RATING_PAGE_SIZE_MAX,
        )
        normalized_score = str(score or "").strip()
        normalized_has_comment = str(has_comment or "").strip().lower()
        if normalized_score and normalized_score not in {"1", "2", "3", "4", "5"}:
            raise_param_error("score")
        if normalized_has_comment and normalized_has_comment != "true":
            raise_param_error("has_comment")

        outline_items = _load_dashboard_course_outline_items(normalized_shifu_bid)
        outline_context_map = _build_course_outline_context_map(outline_items)
        normalized_chapter_keyword = str(chapter_keyword or "").strip().lower()
        start_dt = _parse_dashboard_date_boundary(
            start_time,
            param_name="start_time",
        )
        end_dt_exclusive = _parse_dashboard_date_boundary(
            end_time,
            param_name="end_time",
            end_of_day=True,
        )
        _validate_dashboard_date_range(
            start_dt=start_dt,
            end_dt_exclusive=end_dt_exclusive,
            start_param_name="start_time",
            end_param_name="end_time",
        )
        rated_at_expression = db.func.coalesce(
            LearnLessonFeedback.updated_at,
            LearnLessonFeedback.created_at,
        )
        rating_base_query = db.session.query(
            LearnLessonFeedback.id.label("id"),
            LearnLessonFeedback.lesson_feedback_bid.label("lesson_feedback_bid"),
            LearnLessonFeedback.progress_record_bid.label("progress_record_bid"),
            LearnLessonFeedback.user_bid.label("user_bid"),
            LearnLessonFeedback.outline_item_bid.label("outline_item_bid"),
            LearnLessonFeedback.score.label("score"),
            LearnLessonFeedback.comment.label("comment"),
            rated_at_expression.label("rated_at"),
        ).filter(
            LearnLessonFeedback.shifu_bid == normalized_shifu_bid,
            LearnLessonFeedback.deleted == 0,
        )
        summary_row = (
            db.session.query(
                db.func.avg(LearnLessonFeedback.score).label("average_score"),
                db.func.count(LearnLessonFeedback.id).label("rating_count"),
                db.func.count(db.func.distinct(LearnLessonFeedback.user_bid)).label(
                    "user_count"
                ),
                db.func.max(rated_at_expression).label("latest_rated_at"),
            )
            .filter(
                LearnLessonFeedback.shifu_bid == normalized_shifu_bid,
                LearnLessonFeedback.deleted == 0,
            )
            .first()
        )
        full_summary = DashboardCourseRatingSummaryDTO(
            average_score=_format_average_score(
                getattr(summary_row, "average_score", None)
            ),
            rating_count=int(getattr(summary_row, "rating_count", 0) or 0),
            user_count=int(getattr(summary_row, "user_count", 0) or 0),
            latest_rated_at=_format_dashboard_datetime_display(
                app,
                getattr(summary_row, "latest_rated_at", None),
                timezone_name,
            ),
        )
        filtered_query = rating_base_query
        keyword_filter = _build_dashboard_learner_keyword_filter(
            LearnLessonFeedback.user_bid,
            str(keyword or ""),
        )
        if keyword_filter is not None:
            filtered_query = filtered_query.filter(keyword_filter)

        if normalized_chapter_keyword:
            matched_outline_item_bids = sorted(
                _resolve_dashboard_outline_keyword_match_bids(
                    outline_context_map,
                    normalized_chapter_keyword,
                )
            )
            if matched_outline_item_bids:
                filtered_query = filtered_query.filter(
                    LearnLessonFeedback.outline_item_bid.in_(matched_outline_item_bids)
                )
            else:
                filtered_query = filtered_query.filter(false())

        if normalized_score:
            filtered_query = filtered_query.filter(
                LearnLessonFeedback.score == int(normalized_score)
            )
        if normalized_has_comment == "true":
            filtered_query = filtered_query.filter(
                db.func.trim(db.func.coalesce(LearnLessonFeedback.comment, "")) != ""
            )
        if start_dt is not None:
            filtered_query = filtered_query.filter(rated_at_expression >= start_dt)
        if end_dt_exclusive is not None:
            filtered_query = filtered_query.filter(
                rated_at_expression < end_dt_exclusive
            )

        total = (
            db.session.query(db.func.count())
            .select_from(filtered_query.subquery())
            .scalar()
            or 0
        )
        if total == 0:
            return DashboardCourseRatingListDTO(
                summary=full_summary,
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )

        page_count = (
            (total + safe_page_size - 1) // safe_page_size if safe_page_size else 0
        )
        resolved_page = min(safe_page_index, max(page_count, 1))
        start = (resolved_page - 1) * safe_page_size
        page_rows = (
            filtered_query.order_by(
                rated_at_expression.desc(),
                LearnLessonFeedback.id.desc(),
            )
            .offset(start)
            .limit(safe_page_size)
            .all()
        )
        page_user_bids = sorted(
            {
                str(getattr(row, "user_bid", "") or "").strip()
                for row in page_rows
                if str(getattr(row, "user_bid", "") or "").strip()
            }
        )
        user_map = _load_dashboard_course_user_map(page_user_bids)
        contact_map = _load_dashboard_course_user_contact_map(page_user_bids)
        items: List[DashboardCourseRatingItemDTO] = []
        for row in page_rows:
            user_bid = str(getattr(row, "user_bid", "") or "").strip()
            outline_item_bid = str(getattr(row, "outline_item_bid", "") or "").strip()
            rated_at = getattr(row, "rated_at", None)
            user = user_map.get(user_bid)
            contact = contact_map.get(user_bid, {"mobile": "", "email": ""})
            context = outline_context_map.get(
                outline_item_bid,
                {
                    "chapter_title": "",
                    "lesson_title": "",
                },
            )
            items.append(
                DashboardCourseRatingItemDTO(
                    lesson_feedback_bid=str(
                        getattr(row, "lesson_feedback_bid", "") or ""
                    ),
                    progress_record_bid=str(
                        getattr(row, "progress_record_bid", "") or ""
                    ),
                    user_bid=user_bid,
                    mobile=str(contact.get("mobile", "") or ""),
                    email=str(contact.get("email", "") or ""),
                    nickname=str(getattr(user, "nickname", "") or ""),
                    chapter_title=str(context.get("chapter_title", "") or ""),
                    lesson_title=str(context.get("lesson_title", "") or ""),
                    score=int(getattr(row, "score", 0) or 0),
                    comment=str(getattr(row, "comment", "") or ""),
                    rated_at=_format_dashboard_datetime_display(
                        app,
                        rated_at,
                        timezone_name,
                    ),
                )
            )
        return DashboardCourseRatingListDTO(
            summary=full_summary,
            items=items,
            page=resolved_page,
            page_size=safe_page_size,
            total=total,
            page_count=page_count,
        )


def build_dashboard_course_learners(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    *,
    page_index: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    learning_status: Optional[str] = None,
    last_learning_start_time: Optional[str] = None,
    last_learning_end_time: Optional[str] = None,
    timezone_name: Optional[str] = None,
) -> DashboardCourseDetailLearnersDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        course_meta = _load_dashboard_course_meta(user_id, normalized_shifu_bid)
        if course_meta is None:
            raise_error("server.shifu.shifuNotFound")

        learner_bids = sorted(_load_course_learner_bids(normalized_shifu_bid))
        leaf_outline_bids = _load_course_leaf_outline_bids(normalized_shifu_bid)
        return _build_dashboard_course_learners(
            app,
            shifu_bid=normalized_shifu_bid,
            learner_bids=learner_bids,
            leaf_outline_bids=leaf_outline_bids,
            page_index=page_index,
            page_size=page_size,
            keyword=keyword,
            learning_status=learning_status,
            last_learning_start_time=last_learning_start_time,
            last_learning_end_time=last_learning_end_time,
            timezone_name=timezone_name,
        )


def build_dashboard_course_detail(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    *,
    timezone_name: Optional[str] = None,
) -> DashboardCourseDetailDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        course_meta = _load_dashboard_course_meta(user_id, normalized_shifu_bid)
        if course_meta is None:
            raise_error("server.shifu.shifuNotFound")

        learner_bids = _load_course_learner_bids(normalized_shifu_bid)
        learner_count = len(learner_bids)
        leaf_outline_bids = _load_course_leaf_outline_bids(normalized_shifu_bid)
        sorted_learner_bids = sorted(learner_bids)

        order_summary = (
            db.session.query(
                db.func.count(Order.id).label("order_count"),
                db.func.coalesce(db.func.sum(Order.paid_price), 0).label(
                    "order_amount"
                ),
            )
            .filter(
                Order.shifu_bid == normalized_shifu_bid,
                Order.deleted == 0,
                Order.status == ORDER_STATUS_SUCCESS,
            )
            .first()
        )
        order_count = int(getattr(order_summary, "order_count", 0) or 0)
        order_amount = Decimal(str(getattr(order_summary, "order_amount", 0) or 0))

        completed_learner_count = _count_completed_learners(
            normalized_shifu_bid,
            leaf_outline_bids,
        )

        active_learner_count_last_7_days = (
            db.session.query(db.func.count(db.distinct(LearnProgressRecord.user_bid)))
            .filter(
                LearnProgressRecord.shifu_bid == normalized_shifu_bid,
                LearnProgressRecord.deleted == 0,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
                LearnProgressRecord.updated_at >= datetime.utcnow() - timedelta(days=7),
            )
            .scalar()
            or 0
        )

        total_follow_up_count = (
            db.session.query(db.func.count(LearnGeneratedBlock.id))
            .filter(
                LearnGeneratedBlock.shifu_bid == normalized_shifu_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
                LearnGeneratedBlock.role == ROLE_STUDENT,
            )
            .scalar()
            or 0
        )
        rating_score = (
            db.session.query(db.func.avg(LearnLessonFeedback.score))
            .filter(
                LearnLessonFeedback.shifu_bid == normalized_shifu_bid,
                LearnLessonFeedback.deleted == 0,
            )
            .scalar()
        )

        created_at = _load_dashboard_course_created_at(normalized_shifu_bid)
        joined_at_map = _load_dashboard_course_joined_at_map(
            normalized_shifu_bid,
            sorted_learner_bids,
        )
        learned_lesson_count_map = _load_dashboard_course_learned_lesson_count_map(
            normalized_shifu_bid,
            sorted_learner_bids,
            leaf_outline_bids,
        )
        new_learner_count_last_7_days = sum(
            1
            for joined_at in joined_at_map.values()
            if joined_at >= datetime.utcnow() - timedelta(days=7)
        )
        learning_learner_count = sum(
            1
            for learner_bid in sorted_learner_bids
            if _resolve_dashboard_course_learning_status(
                learned_lesson_count=int(
                    learned_lesson_count_map.get(learner_bid, 0) or 0
                ),
                total_lesson_count=len(leaf_outline_bids),
            )
            == "learning"
        )

        return DashboardCourseDetailDTO(
            basic_info=DashboardCourseDetailBasicInfoDTO(
                shifu_bid=normalized_shifu_bid,
                course_name=course_meta.shifu_name,
                course_status=_resolve_dashboard_course_status(normalized_shifu_bid),
                created_at=serialize_with_app_timezone(
                    app,
                    created_at,
                    timezone_name,
                )
                or "",
                created_at_display=format_with_app_timezone(
                    app,
                    created_at,
                    "%Y-%m-%d %H:%M:%S",
                    timezone_name,
                )
                or "",
                chapter_count=len(leaf_outline_bids),
                learner_count=learner_count,
            ),
            metrics=DashboardCourseDetailMetricsDTO(
                order_count=order_count,
                order_amount=_format_money(order_amount),
                new_learner_count_last_7_days=int(new_learner_count_last_7_days),
                learning_learner_count=int(learning_learner_count),
                completed_learner_count=completed_learner_count,
                completion_rate=_format_percentage(
                    completed_learner_count,
                    learner_count,
                ),
                active_learner_count_last_7_days=int(active_learner_count_last_7_days),
                total_follow_up_count=int(total_follow_up_count),
                rating_score=_format_average_score(rating_score),
            ),
        )
