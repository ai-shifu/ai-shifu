"""Query helpers for the teacher-facing analytics dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.dashboard.dtos import (
    DashboardCourseDetailBasicInfoDTO,
    DashboardCourseDetailChartsDTO,
    DashboardCourseDetailDTO,
    DashboardCourseDetailFollowUpCountBySectionDTO,
    DashboardCourseDetailMetricsDTO,
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
from flaskr.service.shifu.demo_courses import is_builtin_demo_course
from flaskr.service.shifu.models import (
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
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


def _outline_position_key(position: object) -> Tuple[Tuple[int, int | str], ...]:
    normalized_position = str(position or "").strip()
    if not normalized_position:
        return ()

    key_parts: List[Tuple[int, int | str]] = []
    for part in normalized_position.split("."):
        normalized_part = part.strip()
        if not normalized_part:
            continue
        if normalized_part.isdigit():
            key_parts.append((0, int(normalized_part)))
        else:
            key_parts.append((1, normalized_part))
    return tuple(key_parts)


def _build_follow_up_count_by_section_chart(
    shifu_bid: str,
) -> List[DashboardCourseDetailFollowUpCountBySectionDTO]:
    outline_items_query = (
        PublishedOutlineItem.query.filter(
            PublishedOutlineItem.shifu_bid == shifu_bid,
            PublishedOutlineItem.deleted == 0,
            PublishedOutlineItem.hidden == 0,
        )
        .order_by(PublishedOutlineItem.id.asc())
    )
    outline_item_map: Dict[str, PublishedOutlineItem] = {}
    visible_parent_bids: Set[str] = set()
    for item in outline_items_query.yield_per(1000):
        outline_item_bid = str(item.outline_item_bid or "").strip()
        parent_bid = str(item.parent_bid or "").strip()
        if not outline_item_bid:
            continue
        outline_item_map[outline_item_bid] = item
        if parent_bid:
            visible_parent_bids.add(parent_bid)

    visible_section_bids = {
        outline_item_bid
        for outline_item_bid in outline_item_map.keys()
        if outline_item_bid not in visible_parent_bids
    }
    ordered_sections = sorted(
        [
            outline_item_map[outline_item_bid]
            for outline_item_bid in visible_section_bids
        ],
        key=lambda item: (
            _outline_position_key(getattr(item, "position", "")),
            int(getattr(item, "id", 0) or 0),
        ),
    )

    follow_up_rows = (
        db.session.query(
            LearnGeneratedBlock.outline_item_bid,
            db.func.count(LearnGeneratedBlock.id),
        )
        .filter(
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.role == ROLE_STUDENT,
        )
        .group_by(LearnGeneratedBlock.outline_item_bid)
    )
    follow_up_count_map = {
        str(outline_item_bid or "").strip(): int(count or 0)
        for outline_item_bid, count in follow_up_rows.yield_per(1000)
    }

    chart_items: List[DashboardCourseDetailFollowUpCountBySectionDTO] = []
    assigned_follow_up_count = 0
    for section in ordered_sections:
        section_outline_item_bid = str(section.outline_item_bid or "").strip()
        section_follow_up_count = int(
            follow_up_count_map.get(section_outline_item_bid, 0) or 0
        )
        assigned_follow_up_count += section_follow_up_count

        chapter_outline_item_bid = section_outline_item_bid
        chapter_title = str(section.title or "").strip()
        current_item: Optional[PublishedOutlineItem] = section
        visited_bids = {section_outline_item_bid}
        while current_item is not None:
            parent_bid = str(getattr(current_item, "parent_bid", "") or "").strip()
            if not parent_bid or parent_bid in visited_bids:
                break
            visited_bids.add(parent_bid)
            parent_item = outline_item_map.get(parent_bid)
            if parent_item is None:
                break
            chapter_outline_item_bid = parent_bid
            chapter_title = str(parent_item.title or "").strip()
            current_item = parent_item

        chart_items.append(
            DashboardCourseDetailFollowUpCountBySectionDTO(
                chapter_outline_item_bid=chapter_outline_item_bid,
                chapter_title=chapter_title,
                section_outline_item_bid=section_outline_item_bid,
                section_title=str(section.title or "").strip(),
                position=str(section.position or "").strip(),
                follow_up_count=section_follow_up_count,
            )
        )

    unassigned_follow_up_count = (
        sum(int(count or 0) for count in follow_up_count_map.values())
        - assigned_follow_up_count
    )
    if unassigned_follow_up_count > 0:
        chart_items.append(
            DashboardCourseDetailFollowUpCountBySectionDTO(
                chapter_outline_item_bid="",
                chapter_title="",
                section_outline_item_bid="__unassigned__",
                section_title="",
                position="",
                follow_up_count=unassigned_follow_up_count,
                is_unassigned=True,
            )
        )

    return chart_items


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

        course_meta = _load_dashboard_course_meta_map(user_id).get(normalized_shifu_bid)
        if course_meta is None:
            raise_error("server.shifu.shifuNotFound")

        learner_bids = _load_course_learner_bids(normalized_shifu_bid)
        learner_count = len(learner_bids)
        leaf_outline_bids = _load_course_leaf_outline_bids(normalized_shifu_bid)

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

        created_at = _load_dashboard_course_created_at(normalized_shifu_bid)
        avg_learning_duration_seconds = _calculate_avg_learning_duration_seconds(
            normalized_shifu_bid,
            learner_count,
        )
        follow_up_count_by_section = _build_follow_up_count_by_section_chart(
            normalized_shifu_bid,
        )

        return DashboardCourseDetailDTO(
            basic_info=DashboardCourseDetailBasicInfoDTO(
                shifu_bid=normalized_shifu_bid,
                course_name=course_meta.shifu_name,
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
                completed_learner_count=completed_learner_count,
                completion_rate=_format_percentage(
                    completed_learner_count,
                    learner_count,
                ),
                active_learner_count_last_7_days=int(active_learner_count_last_7_days),
                total_follow_up_count=int(total_follow_up_count),
                avg_follow_up_count_per_learner=_format_ratio(
                    int(total_follow_up_count),
                    learner_count,
                ),
                avg_learning_duration_seconds=avg_learning_duration_seconds,
            ),
            charts=DashboardCourseDetailChartsDTO(
                follow_up_count_by_section=follow_up_count_by_section,
            ),
        )
