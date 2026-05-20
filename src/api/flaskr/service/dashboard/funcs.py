"""Query helpers for the teacher-facing analytics dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Set, Tuple

from flask import Flask

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
from flaskr.service.learn.const import ROLE_STUDENT
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
from flaskr.service.shifu.consts import BLOCK_TYPE_MDASK_VALUE
from flaskr.service.shifu.demo_courses import is_builtin_demo_course
from flaskr.service.shifu.admin import (
    _build_course_follow_up_base_subquery,
    _build_course_outline_context_map,
    _build_follow_up_user_keyword_filter,
    _format_average_score,
    _load_follow_up_groups_for_progress_record,
    _resolve_follow_up_answer_content,
    _resolve_follow_up_matching_outline_bids,
)
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
    normalized_learner_bids = [
        str(user_bid or "").strip()
        for user_bid in learner_bids
        if str(user_bid or "").strip()
    ]
    if not normalized_learner_bids:
        return DashboardCourseDetailLearnersDTO(
            page=1,
            page_size=safe_page_size,
            page_count=0,
            total=0,
            items=[],
        )

    user_map = _load_dashboard_course_user_map(normalized_learner_bids)
    contact_map = _load_dashboard_course_user_contact_map(normalized_learner_bids)
    last_learning_map = _load_dashboard_course_last_learning_map(
        shifu_bid,
        normalized_learner_bids,
    )
    joined_at_map = _load_dashboard_course_joined_at_map(
        shifu_bid,
        normalized_learner_bids,
    )
    learned_lesson_count_map = _load_dashboard_course_learned_lesson_count_map(
        shifu_bid,
        normalized_learner_bids,
        leaf_outline_bids,
    )
    follow_up_count_map = _load_dashboard_course_follow_up_count_map(
        shifu_bid,
        normalized_learner_bids,
    )
    total_lesson_count = len(leaf_outline_bids)
    normalized_learning_status = str(learning_status or "").strip().lower()
    if normalized_learning_status not in {"", "not_started", "learning", "completed"}:
        normalized_learning_status = ""

    items_with_sort_keys: list[
        tuple[tuple[datetime, datetime, str], DashboardCourseDetailLearnerItemDTO]
    ] = []
    for user_bid in normalized_learner_bids:
        user = user_map.get(user_bid)
        contact = contact_map.get(user_bid, {"mobile": "", "email": ""})
        nickname = str(getattr(user, "nickname", "") or "").strip()
        mobile = str(contact.get("mobile", "") or "").strip()
        email = str(contact.get("email", "") or "").strip()

        learned_lesson_count = int(learned_lesson_count_map.get(user_bid, 0) or 0)
        follow_up_count = int(follow_up_count_map.get(user_bid, 0) or 0)
        last_learning_at = last_learning_map.get(user_bid)
        joined_at = joined_at_map.get(user_bid)
        resolved_learning_status = _resolve_dashboard_course_learning_status(
            learned_lesson_count=learned_lesson_count,
            total_lesson_count=total_lesson_count,
        )
        if not _dashboard_learner_keyword_matches(
            keyword=str(keyword or ""),
            nickname=nickname,
            mobile=mobile,
            email=email,
        ):
            continue
        if (
            normalized_learning_status
            and resolved_learning_status != normalized_learning_status
        ):
            continue
        if last_learning_start_dt is not None and (
            last_learning_at is None or last_learning_at < last_learning_start_dt
        ):
            continue
        if last_learning_end_dt_exclusive is not None and (
            last_learning_at is None
            or last_learning_at >= last_learning_end_dt_exclusive
        ):
            continue
        dto = DashboardCourseDetailLearnerItemDTO(
            user_bid=user_bid,
            mobile=mobile,
            email=email,
            nickname=nickname,
            learned_lesson_count=learned_lesson_count,
            total_lesson_count=total_lesson_count,
            learning_status=resolved_learning_status,
            follow_up_count=follow_up_count,
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
        items_with_sort_keys.append(
            (
                (
                    last_learning_at or datetime.min,
                    joined_at or datetime.min,
                    user_bid,
                ),
                dto,
            )
        )

    items_with_sort_keys.sort(key=lambda item: item[0], reverse=True)
    items = [item for _, item in items_with_sort_keys]
    total = len(items)
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
    paged_items = items[offset : offset + safe_page_size]
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

        course_meta = _load_dashboard_course_meta_map(user_id).get(normalized_shifu_bid)
        if course_meta is None:
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

        course_meta = _load_dashboard_course_meta_map(user_id).get(normalized_shifu_bid)
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

        course_meta = _load_dashboard_course_meta_map(user_id).get(normalized_shifu_bid)
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
        rating_rows = (
            LearnLessonFeedback.query.filter(
                LearnLessonFeedback.shifu_bid == normalized_shifu_bid,
                LearnLessonFeedback.deleted == 0,
            )
            .order_by(
                LearnLessonFeedback.updated_at.desc(),
                LearnLessonFeedback.id.desc(),
            )
            .all()
        )
        user_bids = sorted(
            {
                str(getattr(row, "user_bid", "") or "").strip()
                for row in rating_rows
                if str(getattr(row, "user_bid", "") or "").strip()
            }
        )
        user_map = _load_dashboard_course_user_map(user_bids)
        contact_map = _load_dashboard_course_user_contact_map(user_bids)
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
        full_latest_rated_at: Optional[datetime] = None
        full_total_score = 0
        full_user_bids: Set[str] = set()
        for row in rating_rows:
            row_user_bid = str(getattr(row, "user_bid", "") or "").strip()
            row_score = int(getattr(row, "score", 0) or 0)
            row_rated_at = getattr(row, "updated_at", None) or getattr(
                row, "created_at", None
            )
            if row_user_bid:
                full_user_bids.add(row_user_bid)
            full_total_score += row_score
            if row_rated_at is not None and (
                full_latest_rated_at is None or row_rated_at > full_latest_rated_at
            ):
                full_latest_rated_at = row_rated_at
        full_summary = DashboardCourseRatingSummaryDTO(
            average_score=(
                _format_average_score(
                    Decimal(full_total_score) / Decimal(len(rating_rows))
                )
                if rating_rows
                else ""
            ),
            rating_count=len(rating_rows),
            user_count=len(full_user_bids),
            latest_rated_at=_format_dashboard_datetime_display(
                app,
                full_latest_rated_at,
                timezone_name,
            ),
        )

        filtered_items: List[tuple[datetime, int, DashboardCourseRatingItemDTO]] = []
        total_score = 0
        latest_rated_at: Optional[datetime] = None

        for row in rating_rows:
            user_bid = str(getattr(row, "user_bid", "") or "").strip()
            outline_item_bid = str(getattr(row, "outline_item_bid", "") or "").strip()
            row_score = int(getattr(row, "score", 0) or 0)
            comment = str(getattr(row, "comment", "") or "")
            rated_at = getattr(row, "updated_at", None) or getattr(
                row, "created_at", None
            )
            user = user_map.get(user_bid)
            contact = contact_map.get(user_bid, {"mobile": "", "email": ""})
            context = outline_context_map.get(
                outline_item_bid,
                {
                    "chapter_title": "",
                    "lesson_title": "",
                },
            )

            if not _dashboard_learner_keyword_matches(
                keyword=str(keyword or ""),
                nickname=str(getattr(user, "nickname", "") or ""),
                mobile=str(contact.get("mobile", "") or ""),
                email=str(contact.get("email", "") or ""),
            ):
                continue

            if normalized_chapter_keyword:
                chapter_haystack = [
                    str(context.get("chapter_title", "") or "").lower(),
                    str(context.get("lesson_title", "") or "").lower(),
                ]
                if not any(
                    normalized_chapter_keyword in value
                    for value in chapter_haystack
                    if value
                ):
                    continue

            if normalized_score and row_score != int(normalized_score):
                continue
            if normalized_has_comment == "true" and not comment.strip():
                continue
            if start_dt is not None and (rated_at is None or rated_at < start_dt):
                continue
            if end_dt_exclusive is not None and (
                rated_at is None or rated_at >= end_dt_exclusive
            ):
                continue

            if rated_at is not None and (
                latest_rated_at is None or rated_at > latest_rated_at
            ):
                latest_rated_at = rated_at

            filtered_items.append(
                (
                    rated_at or datetime.min,
                    int(getattr(row, "id", 0) or 0),
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
                        score=row_score,
                        comment=comment,
                        rated_at=_format_dashboard_datetime_display(
                            app,
                            rated_at,
                            timezone_name,
                        ),
                    ),
                )
            )
            total_score += row_score

        filtered_items.sort(key=lambda item: (item[0], item[1]), reverse=True)
        rows = [item for _, _, item in filtered_items]
        total = len(rows)
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
        end = start + safe_page_size
        return DashboardCourseRatingListDTO(
            summary=full_summary,
            items=rows[start:end],
            page=resolved_page,
            page_size=safe_page_size,
            total=total,
            page_count=page_count,
        )


def build_dashboard_course_detail(
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
) -> DashboardCourseDetailDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        course_meta = _load_dashboard_course_meta_map(user_id).get(normalized_shifu_bid)
        if course_meta is None:
            raise_error("server.shifu.shifuNotFound")

        learner_bids = _load_course_learner_bids(normalized_shifu_bid)
        learner_count = len(learner_bids)
        leaf_outline_bids = _load_course_leaf_outline_bids(normalized_shifu_bid)
        sorted_learner_bids = sorted(learner_bids)
        learners = _build_dashboard_course_learners(
            app,
            shifu_bid=normalized_shifu_bid,
            learner_bids=sorted_learner_bids,
            leaf_outline_bids=leaf_outline_bids,
            page_index=page_index,
            page_size=page_size,
            keyword=keyword,
            learning_status=learning_status,
            last_learning_start_time=last_learning_start_time,
            last_learning_end_time=last_learning_end_time,
            timezone_name=timezone_name,
        )

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
            learners=learners,
        )
