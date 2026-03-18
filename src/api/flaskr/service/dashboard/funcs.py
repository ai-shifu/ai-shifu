"""Query helpers for the teacher-facing analytics dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.config.funcs import get_config as get_dynamic_config
from flaskr.service.dashboard.dtos import (
    DashboardCourseDetailBasicInfoDTO,
    DashboardCourseDetailDTO,
    DashboardCourseDetailAppliedRangeDTO,
    DashboardCourseDetailChartsDTO,
    DashboardCourseDetailLearnerItemDTO,
    DashboardCourseDetailLearnersDTO,
    DashboardCourseDetailMetricsDTO,
    DashboardCourseDetailQuestionsByChapterItemDTO,
    DashboardEntryCourseItemDTO,
    DashboardEntryDTO,
    DashboardEntrySummaryDTO,
)
from flaskr.service.learn.const import ROLE_STUDENT
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_RESET,
    ORDER_STATUS_SUCCESS,
)
from flaskr.service.order.models import Order
from flaskr.service.shifu.consts import BLOCK_TYPE_MDASK_VALUE
from flaskr.service.shifu.models import (
    DraftShifu,
    LogPublishedStruct,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.util.timezone import format_with_app_timezone, serialize_with_app_timezone

# Built-in demo course IDs observed in legacy environments.
_LEGACY_DEMO_SHIFU_BIDS: Set[str] = {
    "e867343eaab44488ad792ec54d8b82b5",  # AI 师傅教学引导
    "b5d7844387e940ed9480a6f945a6db6a",  # AI-Shifu Creation Guide
}
_BUILTIN_DEMO_TITLES: Set[str] = {
    "AI 师傅教学引导",
    "AI-Shifu Creation Guide",
}


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


@dataclass(frozen=True)
class _DashboardOutlineSummary:
    outline_item_bid: str
    title: str
    parent_bid: str
    hidden: bool
    position: str


@dataclass
class _DashboardCourseDetailAggregate:
    course_meta: _DashboardCourseMeta
    created_at: Optional[datetime]
    leaf_outlines: List[_DashboardOutlineSummary]
    learner_bids: Set[str] = field(default_factory=set)
    total_follow_up_count: int = 0
    follow_up_count_by_outline: Dict[str, int] = field(default_factory=dict)
    follow_up_count_by_user: Dict[str, int] = field(default_factory=dict)
    order_count: int = 0
    order_amount: Decimal = field(default_factory=lambda: Decimal("0"))
    completed_learner_count: int = 0
    active_learner_count_last_7_days: int = 0
    avg_learning_duration_seconds: int = 0
    progress_percent_by_user: Dict[str, str] = field(default_factory=dict)
    last_active_by_user: Dict[str, datetime] = field(default_factory=dict)
    nickname_by_user: Dict[str, str] = field(default_factory=dict)
    applied_start_date: str = ""
    applied_end_date: str = ""


def _format_money(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)
    return format(quantized, "f")


def _format_ratio(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.00"
    return _format_money(Decimal(numerator) / Decimal(denominator))


def _format_percentage(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.00"
    return _format_money((Decimal(numerator) * Decimal("100")) / Decimal(denominator))


def _parse_iso_date(raw: Optional[str]) -> Optional[date]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise_param_error(f"invalid date: {text}")


def _resolve_date_range(
    start_date: Optional[date],
    end_date: Optional[date],
    *,
    default_days: int = 14,
    max_days: int = 366,
) -> Tuple[date, date]:
    today = date.today()
    resolved_end = end_date or today
    resolved_start = start_date or (resolved_end - timedelta(days=default_days - 1))
    if resolved_start > resolved_end:
        raise_param_error("start_date must be <= end_date")
    if (resolved_end - resolved_start).days + 1 > max_days:
        raise_param_error(f"date range too large (max {max_days} days)")
    return resolved_start, resolved_end


def _resolve_optional_datetime_range(
    start_date: Optional[str],
    end_date: Optional[str],
) -> Tuple[Optional[datetime], Optional[datetime]]:
    parsed_start = _parse_iso_date(start_date)
    parsed_end = _parse_iso_date(end_date)
    if parsed_start is None and parsed_end is None:
        return None, None
    resolved_start, resolved_end = _resolve_date_range(parsed_start, parsed_end)
    start_dt = datetime.combine(resolved_start, datetime.min.time())
    end_dt_exclusive = datetime.combine(
        resolved_end + timedelta(days=1),
        datetime.min.time(),
    )
    return start_dt, end_dt_exclusive


def _load_demo_shifu_bids() -> Set[str]:
    demo_bids: Set[str] = set(_LEGACY_DEMO_SHIFU_BIDS)
    for key in ("DEMO_SHIFU_BID", "DEMO_EN_SHIFU_BID"):
        bid = str(get_dynamic_config(key, "") or "").strip()
        if bid:
            demo_bids.add(bid)
    return demo_bids


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
    all_bids = owned_bids.difference(_load_demo_shifu_bids())
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
    demo_bids = _load_demo_shifu_bids()
    course_map: Dict[str, _DashboardCourseMeta] = {}
    for row in published_rows:
        shifu_bid = str(row.shifu_bid or "").strip()
        if not shifu_bid:
            continue
        title = str(row.title or "").strip()
        created_user_bid = str(row.created_user_bid or "").strip()
        is_builtin_demo = shifu_bid in demo_bids or (
            created_user_bid == "system" and title in _BUILTIN_DEMO_TITLES
        )
        if is_builtin_demo:
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


def _position_sort_key(position: Optional[str]) -> Tuple[Tuple[int, object], ...]:
    normalized_position = str(position or "").strip()
    if not normalized_position:
        return ((1, ""),)

    result: List[Tuple[int, object]] = []
    for part in normalized_position.split("."):
        normalized_part = part.strip()
        if normalized_part.isdigit():
            result.append((0, int(normalized_part)))
        else:
            result.append((1, normalized_part))
    return tuple(result)


def _load_ordered_course_outlines(shifu_bid: str) -> List[_DashboardOutlineSummary]:
    outline_rows: List[PublishedOutlineItem] = (
        PublishedOutlineItem.query.filter(
            PublishedOutlineItem.shifu_bid == shifu_bid,
            PublishedOutlineItem.deleted == 0,
        )
        .order_by(PublishedOutlineItem.id.asc())
        .all()
    )
    if not outline_rows:
        return []

    outline_map: Dict[str, PublishedOutlineItem] = {}
    for row in outline_rows:
        outline_item_bid = str(row.outline_item_bid or "").strip()
        if not outline_item_bid:
            continue
        outline_map[outline_item_bid] = row

    ordered_bids: List[str] = []
    struct_row: Optional[LogPublishedStruct] = (
        LogPublishedStruct.query.filter(
            LogPublishedStruct.shifu_bid == shifu_bid,
            LogPublishedStruct.deleted == 0,
        )
        .order_by(LogPublishedStruct.id.desc())
        .first()
    )
    if struct_row and struct_row.struct:
        try:
            history = HistoryItem.from_json(struct_row.struct)

            def walk(item: HistoryItem) -> None:
                for child in item.children or []:
                    if child.type == "outline":
                        outline_bid = str(child.bid or "").strip()
                        if outline_bid:
                            ordered_bids.append(outline_bid)
                    walk(child)

            walk(history)
        except Exception:
            ordered_bids = []

    used_outline_bids: Set[str] = set()
    ordered_rows: List[PublishedOutlineItem] = []
    for outline_bid in ordered_bids:
        row = outline_map.get(outline_bid)
        if row is None or outline_bid in used_outline_bids:
            continue
        ordered_rows.append(row)
        used_outline_bids.add(outline_bid)

    remaining_rows = [
        row
        for outline_bid, row in outline_map.items()
        if outline_bid not in used_outline_bids
    ]
    remaining_rows.sort(
        key=lambda row: (
            _position_sort_key(row.position),
            str(row.outline_item_bid or "").strip(),
        )
    )
    ordered_rows.extend(remaining_rows)

    return [
        _DashboardOutlineSummary(
            outline_item_bid=str(row.outline_item_bid or "").strip(),
            title=str(row.title or "").strip(),
            parent_bid=str(row.parent_bid or "").strip(),
            hidden=bool(row.hidden),
            position=str(row.position or "").strip(),
        )
        for row in ordered_rows
        if str(row.outline_item_bid or "").strip()
    ]


def _extract_visible_leaf_outlines(
    outlines: List[_DashboardOutlineSummary],
) -> List[_DashboardOutlineSummary]:
    visible_outlines = [outline for outline in outlines if not outline.hidden]
    visible_parent_bids = {
        outline.parent_bid for outline in visible_outlines if outline.parent_bid
    }
    return [
        outline
        for outline in visible_outlines
        if outline.outline_item_bid not in visible_parent_bids
    ]


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


def _load_completed_leaf_outline_sets(
    shifu_bid: str,
    leaf_outline_bids: List[str],
) -> Dict[str, Set[str]]:
    if not leaf_outline_bids:
        return {}

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
    return completed_leaf_bids_by_user


def _count_completed_learners(shifu_bid: str, leaf_outline_bids: List[str]) -> int:
    if not leaf_outline_bids:
        return 0

    completed_leaf_bids_by_user = _load_completed_leaf_outline_sets(
        shifu_bid,
        leaf_outline_bids,
    )
    leaf_count = len(leaf_outline_bids)
    return sum(
        1
        for completed_outline_bids in completed_leaf_bids_by_user.values()
        if len(completed_outline_bids) >= leaf_count
    )


def _calculate_avg_learning_duration_seconds(
    shifu_bid: str,
    learner_count: int,
) -> int:
    if learner_count <= 0:
        return 0

    duration_rows = (
        db.session.query(
            LearnProgressRecord.user_bid,
            db.func.min(LearnProgressRecord.created_at).label("started_at"),
            db.func.max(LearnProgressRecord.updated_at).label("ended_at"),
        )
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .group_by(LearnProgressRecord.user_bid)
        .all()
    )

    total_duration_seconds = 0
    for user_bid, started_at, ended_at in duration_rows:
        if not str(user_bid or "").strip() or not started_at or not ended_at:
            continue
        duration_seconds = max(int((ended_at - started_at).total_seconds()), 0)
        total_duration_seconds += duration_seconds
    return int(total_duration_seconds / learner_count)


def _load_follow_up_aggregates(
    shifu_bid: str,
    *,
    start_dt: Optional[datetime],
    end_dt_exclusive: Optional[datetime],
) -> Tuple[int, Dict[str, int], Dict[str, int]]:
    query = db.session.query(
        LearnGeneratedBlock.outline_item_bid.label("outline_item_bid"),
        LearnGeneratedBlock.user_bid.label("user_bid"),
        db.func.count(LearnGeneratedBlock.id).label("ask_count"),
    ).filter(
        LearnGeneratedBlock.shifu_bid == shifu_bid,
        LearnGeneratedBlock.deleted == 0,
        LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
        LearnGeneratedBlock.role == ROLE_STUDENT,
    )
    if start_dt is not None:
        query = query.filter(LearnGeneratedBlock.created_at >= start_dt)
    if end_dt_exclusive is not None:
        query = query.filter(LearnGeneratedBlock.created_at < end_dt_exclusive)

    rows = query.group_by(
        LearnGeneratedBlock.outline_item_bid,
        LearnGeneratedBlock.user_bid,
    ).all()

    total_follow_up_count = 0
    follow_up_count_by_outline: Dict[str, int] = {}
    follow_up_count_by_user: Dict[str, int] = {}
    for outline_item_bid, user_bid, ask_count in rows:
        normalized_outline_item_bid = str(outline_item_bid or "").strip()
        normalized_user_bid = str(user_bid or "").strip()
        normalized_ask_count = int(ask_count or 0)
        if normalized_ask_count <= 0:
            continue

        total_follow_up_count += normalized_ask_count
        if normalized_outline_item_bid:
            follow_up_count_by_outline[normalized_outline_item_bid] = (
                follow_up_count_by_outline.get(normalized_outline_item_bid, 0)
                + normalized_ask_count
            )
        if normalized_user_bid:
            follow_up_count_by_user[normalized_user_bid] = (
                follow_up_count_by_user.get(normalized_user_bid, 0)
                + normalized_ask_count
            )
    return total_follow_up_count, follow_up_count_by_outline, follow_up_count_by_user


def _load_order_summary(
    shifu_bid: str,
    *,
    start_dt: Optional[datetime],
    end_dt_exclusive: Optional[datetime],
) -> Tuple[int, Decimal]:
    query = db.session.query(
        db.func.count(Order.id).label("order_count"),
        db.func.coalesce(db.func.sum(Order.paid_price), 0).label("order_amount"),
    ).filter(
        Order.shifu_bid == shifu_bid,
        Order.deleted == 0,
        Order.status == ORDER_STATUS_SUCCESS,
    )
    if start_dt is not None:
        query = query.filter(Order.created_at >= start_dt)
    if end_dt_exclusive is not None:
        query = query.filter(Order.created_at < end_dt_exclusive)

    row = query.first()
    return (
        int(getattr(row, "order_count", 0) or 0),
        Decimal(str(getattr(row, "order_amount", 0) or 0)),
    )


def _count_active_learners_last_7_days(
    shifu_bid: str,
    *,
    end_dt_exclusive: Optional[datetime],
) -> int:
    active_window_end = end_dt_exclusive or datetime.utcnow()
    active_window_start = active_window_end - timedelta(days=7)
    value = (
        db.session.query(db.func.count(db.distinct(LearnProgressRecord.user_bid)))
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.updated_at >= active_window_start,
            LearnProgressRecord.updated_at < active_window_end,
        )
        .scalar()
    )
    return int(value or 0)


def _load_last_active_by_user(
    shifu_bid: str,
    *,
    start_dt: Optional[datetime],
    end_dt_exclusive: Optional[datetime],
) -> Dict[str, datetime]:
    query = db.session.query(
        LearnProgressRecord.user_bid.label("user_bid"),
        db.func.max(LearnProgressRecord.updated_at).label("last_active_at"),
    ).filter(
        LearnProgressRecord.shifu_bid == shifu_bid,
        LearnProgressRecord.deleted == 0,
        LearnProgressRecord.status != LEARN_STATUS_RESET,
    )
    if start_dt is not None:
        query = query.filter(LearnProgressRecord.updated_at >= start_dt)
    if end_dt_exclusive is not None:
        query = query.filter(LearnProgressRecord.updated_at < end_dt_exclusive)

    rows = query.group_by(LearnProgressRecord.user_bid).all()
    result: Dict[str, datetime] = {}
    for user_bid, last_active_at in rows:
        normalized_user_bid = str(user_bid or "").strip()
        if not normalized_user_bid or last_active_at is None:
            continue
        result[normalized_user_bid] = last_active_at
    return result


def _load_user_nickname_map(user_bids: List[str]) -> Dict[str, str]:
    if not user_bids:
        return {}

    rows: List[UserEntity] = UserEntity.query.filter(
        UserEntity.user_bid.in_(user_bids),
        UserEntity.deleted == 0,
    ).all()
    return {
        str(row.user_bid or "").strip(): str(row.nickname or "").strip()
        for row in rows
        if str(row.user_bid or "").strip()
    }


def _build_progress_percent_by_user(
    learner_bids: Set[str],
    completed_leaf_bids_by_user: Dict[str, Set[str]],
    leaf_outline_count: int,
) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for learner_bid in learner_bids:
        completed_count = len(completed_leaf_bids_by_user.get(learner_bid, set()))
        result[learner_bid] = _format_percentage(completed_count, leaf_outline_count)
    return result


def _build_dashboard_course_detail_aggregate(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> _DashboardCourseDetailAggregate:
    normalized_shifu_bid = str(shifu_bid or "").strip()
    if not normalized_shifu_bid:
        raise_param_error("shifu_bid is required")

    course_meta = _load_dashboard_course_meta_map(user_id).get(normalized_shifu_bid)
    if course_meta is None:
        raise_error("server.shifu.shifuNotFound")

    start_dt, end_dt_exclusive = _resolve_optional_datetime_range(
        start_date,
        end_date,
    )
    applied_start_date = start_dt.date().isoformat() if start_dt is not None else ""
    applied_end_date = (
        (end_dt_exclusive - timedelta(days=1)).date().isoformat()
        if end_dt_exclusive is not None
        else ""
    )

    ordered_outlines = _load_ordered_course_outlines(normalized_shifu_bid)
    leaf_outlines = _extract_visible_leaf_outlines(ordered_outlines)
    leaf_outline_bids = [outline.outline_item_bid for outline in leaf_outlines]
    learner_bids = _load_course_learner_bids(normalized_shifu_bid)
    completed_leaf_bids_by_user = _load_completed_leaf_outline_sets(
        normalized_shifu_bid,
        leaf_outline_bids,
    )

    total_follow_up_count, follow_up_count_by_outline, follow_up_count_by_user = (
        _load_follow_up_aggregates(
            normalized_shifu_bid,
            start_dt=start_dt,
            end_dt_exclusive=end_dt_exclusive,
        )
    )
    order_count, order_amount = _load_order_summary(
        normalized_shifu_bid,
        start_dt=start_dt,
        end_dt_exclusive=end_dt_exclusive,
    )

    return _DashboardCourseDetailAggregate(
        course_meta=course_meta,
        created_at=_load_dashboard_course_created_at(normalized_shifu_bid),
        leaf_outlines=leaf_outlines,
        learner_bids=learner_bids,
        total_follow_up_count=total_follow_up_count,
        follow_up_count_by_outline=follow_up_count_by_outline,
        follow_up_count_by_user=follow_up_count_by_user,
        order_count=order_count,
        order_amount=order_amount,
        completed_learner_count=sum(
            1
            for learner_bid in learner_bids
            if len(completed_leaf_bids_by_user.get(learner_bid, set()))
            >= len(leaf_outline_bids)
            and len(leaf_outline_bids) > 0
        ),
        active_learner_count_last_7_days=_count_active_learners_last_7_days(
            normalized_shifu_bid,
            end_dt_exclusive=end_dt_exclusive,
        ),
        avg_learning_duration_seconds=_calculate_avg_learning_duration_seconds(
            normalized_shifu_bid,
            len(learner_bids),
        ),
        progress_percent_by_user=_build_progress_percent_by_user(
            learner_bids,
            completed_leaf_bids_by_user,
            len(leaf_outline_bids),
        ),
        last_active_by_user=_load_last_active_by_user(
            normalized_shifu_bid,
            start_dt=start_dt,
            end_dt_exclusive=end_dt_exclusive,
        ),
        nickname_by_user=_load_user_nickname_map(sorted(learner_bids)),
        applied_start_date=applied_start_date,
        applied_end_date=applied_end_date,
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
    with app.app_context():
        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = max(int(page_size or 20), 1)
        safe_page_size = min(safe_page_size, 100)

        start_dt, end_dt_exclusive = _resolve_optional_datetime_range(
            start_date,
            end_date,
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


def build_dashboard_course_detail(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    learner_page_index: int = 1,
    learner_page_size: int = 20,
    timezone_name: Optional[str] = None,
) -> DashboardCourseDetailDTO:
    with app.app_context():
        aggregate = _build_dashboard_course_detail_aggregate(
            app,
            user_id,
            shifu_bid,
            start_date=start_date,
            end_date=end_date,
        )
        safe_learner_page_index = max(int(learner_page_index or 1), 1)
        safe_learner_page_size = max(int(learner_page_size or 20), 1)
        safe_learner_page_size = min(safe_learner_page_size, 100)

        learner_bids = sorted(
            aggregate.learner_bids,
            key=lambda learner_bid: (
                1 if aggregate.last_active_by_user.get(learner_bid) is None else 0,
                -(
                    aggregate.last_active_by_user.get(learner_bid).timestamp()
                    if aggregate.last_active_by_user.get(learner_bid) is not None
                    else 0
                ),
                -aggregate.follow_up_count_by_user.get(learner_bid, 0),
                learner_bid,
            ),
        )
        learner_total = len(learner_bids)
        learner_offset = (safe_learner_page_index - 1) * safe_learner_page_size
        paged_learner_bids = learner_bids[
            learner_offset : learner_offset + safe_learner_page_size
        ]
        learner_items = [
            DashboardCourseDetailLearnerItemDTO(
                user_bid=learner_bid,
                nickname=aggregate.nickname_by_user.get(learner_bid, ""),
                progress_percent=aggregate.progress_percent_by_user.get(
                    learner_bid,
                    "0.00",
                ),
                follow_up_ask_count=aggregate.follow_up_count_by_user.get(
                    learner_bid,
                    0,
                ),
                last_active_at=serialize_with_app_timezone(
                    app,
                    aggregate.last_active_by_user.get(learner_bid),
                    timezone_name,
                )
                or "",
                last_active_at_display=format_with_app_timezone(
                    app,
                    aggregate.last_active_by_user.get(learner_bid),
                    "%Y-%m-%d %H:%M:%S",
                    timezone_name,
                )
                or "",
            )
            for learner_bid in paged_learner_bids
        ]
        questions_by_chapter = [
            DashboardCourseDetailQuestionsByChapterItemDTO(
                outline_item_bid=outline.outline_item_bid,
                title=outline.title,
                ask_count=aggregate.follow_up_count_by_outline.get(
                    outline.outline_item_bid,
                    0,
                ),
            )
            for outline in aggregate.leaf_outlines
        ]

        return DashboardCourseDetailDTO(
            basic_info=DashboardCourseDetailBasicInfoDTO(
                shifu_bid=aggregate.course_meta.shifu_bid,
                course_name=aggregate.course_meta.shifu_name,
                created_at=serialize_with_app_timezone(
                    app,
                    aggregate.created_at,
                    timezone_name,
                )
                or "",
                created_at_display=format_with_app_timezone(
                    app,
                    aggregate.created_at,
                    "%Y-%m-%d %H:%M:%S",
                    timezone_name,
                )
                or "",
                chapter_count=len(aggregate.leaf_outlines),
                learner_count=learner_total,
            ),
            metrics=DashboardCourseDetailMetricsDTO(
                order_count=aggregate.order_count,
                order_amount=_format_money(aggregate.order_amount),
                completed_learner_count=aggregate.completed_learner_count,
                completion_rate=_format_percentage(
                    aggregate.completed_learner_count,
                    learner_total,
                ),
                active_learner_count_last_7_days=(
                    aggregate.active_learner_count_last_7_days
                ),
                total_follow_up_count=aggregate.total_follow_up_count,
                avg_follow_up_count_per_learner=_format_ratio(
                    aggregate.total_follow_up_count,
                    learner_total,
                ),
                avg_learning_duration_seconds=(
                    aggregate.avg_learning_duration_seconds
                ),
            ),
            charts=DashboardCourseDetailChartsDTO(
                questions_by_chapter=questions_by_chapter,
                questions_by_time=[],
                learning_activity_trend=[],
                chapter_progress_distribution=[],
            ),
            learners=DashboardCourseDetailLearnersDTO(
                page=safe_learner_page_index,
                page_size=safe_learner_page_size,
                total=learner_total,
                items=learner_items,
            ),
            applied_range=DashboardCourseDetailAppliedRangeDTO(
                start_date=aggregate.applied_start_date,
                end_date=aggregate.applied_end_date,
            ),
        )
