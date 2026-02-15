"""Query helpers for the teacher-facing analytics dashboard.

Hard constraint: do not use database join queries. Load parent records first, then
load child records via `IN (...)` and merge in Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from flask import Flask
from sqlalchemy import or_

from flaskr.dao import db
from flaskr.service.common.dtos import PageNationDTO
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.dashboard.dtos import (
    DashboardEntryCourseItemDTO,
    DashboardEntryDTO,
    DashboardEntrySummaryDTO,
    DashboardFollowUpItemDTO,
    DashboardLearnerDetailDTO,
    DashboardLearnerFollowUpSummaryDTO,
    DashboardLearnerOutlineProgressDTO,
    DashboardLearnerSummaryDTO,
    DashboardLearnerVariableDTO,
    DashboardOutlineDTO,
    DashboardOverviewDTO,
    DashboardOverviewKpiDTO,
    DashboardSeriesPointDTO,
    DashboardTopLearnerDTO,
    DashboardTopOutlineDTO,
)
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_LOCKED,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_RESET,
)
from flaskr.service.order.models import Order
from flaskr.service.profile.funcs import get_user_profiles
from flaskr.service.shifu.consts import (
    UNIT_TYPE_VALUE_GUEST,
    UNIT_TYPE_VALUE_NORMAL,
    UNIT_TYPE_VALUE_TRIAL,
)
from flaskr.service.shifu.funcs import shifu_permission_verification
from flaskr.service.shifu.models import (
    AiCourseAuth,
    LogPublishedStruct,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.permissions import (
    _auth_types_to_permissions,
    _normalize_auth_types,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
)
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity


def dashboard_healthcheck(app: Flask) -> bool:
    """Small helper to verify the dashboard module is loaded."""
    with app.app_context():
        return True


def require_shifu_view_permission(app: Flask, user_id: str, shifu_bid: str) -> None:
    """Raise if the user does not have view permission for this shifu."""
    with app.app_context():
        allowed = shifu_permission_verification(app, user_id, shifu_bid, "view")
        if not allowed:
            raise_error("server.shifu.noPermission")


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


@dataclass(frozen=True)
class _DashboardEntryCourse:
    shifu_bid: str
    shifu_name: str


@dataclass
class _DashboardEntryMetrics:
    learner_total: int = 0
    learner_count_map: Dict[str, int] = field(default_factory=dict)
    order_count_map: Dict[str, int] = field(default_factory=dict)
    generation_count_map: Dict[str, int] = field(default_factory=dict)
    last_active_map: Dict[str, datetime] = field(default_factory=dict)
    active_course_bids: Set[str] = field(default_factory=set)


def _load_dashboard_entry_courses(
    user_id: str,
    *,
    keyword: Optional[str] = None,
) -> List[_DashboardEntryCourse]:
    shared_rows = (
        db.session.query(AiCourseAuth.course_id, AiCourseAuth.auth_type)
        .filter(
            AiCourseAuth.user_id == user_id,
            AiCourseAuth.status == 1,
        )
        .all()
    )

    def _is_view_only_auth_type(raw_auth_type: object) -> bool:
        auth_types = _normalize_auth_types(raw_auth_type)
        permissions = _auth_types_to_permissions(auth_types) or {
            str(item).strip().lower() for item in auth_types if str(item).strip()
        }
        return permissions == {"view"}

    shared_bids = {
        str(course_id).strip()
        for course_id, auth_type in shared_rows
        if str(course_id).strip() and _is_view_only_auth_type(auth_type)
    }

    owned_rows = (
        db.session.query(PublishedShifu.shifu_bid)
        .filter(
            PublishedShifu.created_user_bid == user_id,
            PublishedShifu.deleted == 0,
        )
        .distinct()
        .all()
    )
    owned_bids = {
        str(row[0]).strip()
        for row in owned_rows
        if row and str(row[0]).strip() and str(row[0]).strip() not in shared_bids
    }
    all_bids = shared_bids.union(owned_bids)
    if not all_bids:
        return []

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
    title_map: Dict[str, str] = {}
    for row in published_rows:
        shifu_bid = str(row.shifu_bid or "").strip()
        if not shifu_bid:
            continue
        title_map[shifu_bid] = str(row.title or "").strip()

    courses = [
        _DashboardEntryCourse(
            shifu_bid=shifu_bid,
            shifu_name=title_map.get(shifu_bid) or shifu_bid,
        )
        for shifu_bid in all_bids
    ]
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


def _collect_dashboard_entry_metrics(
    shifu_bids: List[str],
    *,
    start_dt: Optional[datetime],
    end_dt_exclusive: Optional[datetime],
) -> _DashboardEntryMetrics:
    if not shifu_bids:
        return _DashboardEntryMetrics()

    learner_total_query = db.session.query(
        db.func.count(db.distinct(LearnProgressRecord.user_bid))
    ).filter(
        LearnProgressRecord.shifu_bid.in_(shifu_bids),
        LearnProgressRecord.deleted == 0,
        LearnProgressRecord.status != LEARN_STATUS_RESET,
    )
    if start_dt is not None:
        learner_total_query = learner_total_query.filter(
            LearnProgressRecord.created_at >= start_dt
        )
    if end_dt_exclusive is not None:
        learner_total_query = learner_total_query.filter(
            LearnProgressRecord.created_at < end_dt_exclusive
        )
    learner_total = int(learner_total_query.scalar() or 0)

    learner_by_course_query = db.session.query(
        LearnProgressRecord.shifu_bid.label("shifu_bid"),
        db.func.count(db.distinct(LearnProgressRecord.user_bid)).label("c"),
    ).filter(
        LearnProgressRecord.shifu_bid.in_(shifu_bids),
        LearnProgressRecord.deleted == 0,
        LearnProgressRecord.status != LEARN_STATUS_RESET,
    )
    if start_dt is not None:
        learner_by_course_query = learner_by_course_query.filter(
            LearnProgressRecord.created_at >= start_dt
        )
    if end_dt_exclusive is not None:
        learner_by_course_query = learner_by_course_query.filter(
            LearnProgressRecord.created_at < end_dt_exclusive
        )
    learner_rows = learner_by_course_query.group_by(LearnProgressRecord.shifu_bid).all()
    learner_count_map: Dict[str, int] = {}
    for shifu_bid, c in learner_rows:
        if not shifu_bid:
            continue
        learner_count_map[str(shifu_bid)] = int(c or 0)

    order_query = db.session.query(
        Order.shifu_bid.label("shifu_bid"),
        db.func.count(Order.id).label("c"),
    ).filter(
        Order.shifu_bid.in_(shifu_bids),
        Order.deleted == 0,
    )
    if start_dt is not None:
        order_query = order_query.filter(Order.created_at >= start_dt)
    if end_dt_exclusive is not None:
        order_query = order_query.filter(Order.created_at < end_dt_exclusive)
    order_rows = order_query.group_by(Order.shifu_bid).all()
    order_count_map: Dict[str, int] = {}
    for shifu_bid, c in order_rows:
        if not shifu_bid:
            continue
        order_count_map[str(shifu_bid)] = int(c or 0)

    generation_query = db.session.query(
        LearnGeneratedBlock.shifu_bid.label("shifu_bid"),
        db.func.count(LearnGeneratedBlock.id).label("c"),
    ).filter(
        LearnGeneratedBlock.shifu_bid.in_(shifu_bids),
        LearnGeneratedBlock.deleted == 0,
    )
    if start_dt is not None:
        generation_query = generation_query.filter(
            LearnGeneratedBlock.created_at >= start_dt
        )
    if end_dt_exclusive is not None:
        generation_query = generation_query.filter(
            LearnGeneratedBlock.created_at < end_dt_exclusive
        )
    generation_rows = generation_query.group_by(LearnGeneratedBlock.shifu_bid).all()
    generation_count_map: Dict[str, int] = {}
    for shifu_bid, c in generation_rows:
        if not shifu_bid:
            continue
        generation_count_map[str(shifu_bid)] = int(c or 0)

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
        .union(generation_count_map.keys())
    )
    return _DashboardEntryMetrics(
        learner_total=learner_total,
        learner_count_map=learner_count_map,
        order_count_map=order_count_map,
        generation_count_map=generation_count_map,
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
                    generation_count=0,
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
                        generation_count=0,
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
                    generation_count=metrics.generation_count_map.get(shifu_bid, 0),
                    last_active_at=last_active.isoformat() if last_active else "",
                )
            )

        return DashboardEntryDTO(
            summary=DashboardEntrySummaryDTO(
                course_count=total,
                learner_count=metrics.learner_total,
                order_count=sum(metrics.order_count_map.values()),
                generation_count=sum(metrics.generation_count_map.values()),
            ),
            page=resolved_page,
            page_size=safe_page_size,
            page_count=page_count,
            total=total,
            items=items,
        )


def _collect_outline_nodes_in_order(struct: HistoryItem) -> List[HistoryItem]:
    nodes: List[HistoryItem] = []

    def walk(item: HistoryItem) -> None:
        if item.type == "outline":
            nodes.append(item)
        for child in item.children or []:
            walk(child)

    for child in struct.children or []:
        walk(child)
    return nodes


def load_published_outlines(app: Flask, shifu_bid: str) -> List[DashboardOutlineDTO]:
    """Load published outline items for a shifu in the struct order."""
    with app.app_context():
        struct_row: LogPublishedStruct | None = (
            LogPublishedStruct.query.filter(
                LogPublishedStruct.shifu_bid == shifu_bid,
                LogPublishedStruct.deleted == 0,
            )
            .order_by(LogPublishedStruct.id.desc())
            .first()
        )
        if not struct_row or not struct_row.struct:
            raise_error("server.shifu.shifuStructNotFound")

        struct = HistoryItem.from_json(struct_row.struct)
        outline_nodes = _collect_outline_nodes_in_order(struct)
        outline_ids = [node.id for node in outline_nodes if node.id]
        if not outline_ids:
            return []

        outline_rows: List[PublishedOutlineItem] = (
            PublishedOutlineItem.query.filter(
                PublishedOutlineItem.id.in_(outline_ids),
                PublishedOutlineItem.shifu_bid == shifu_bid,
                PublishedOutlineItem.deleted == 0,
            )
            .order_by(PublishedOutlineItem.id.asc())
            .all()
        )
        outline_by_id: Dict[int, PublishedOutlineItem] = {
            row.id: row for row in outline_rows
        }

        result: List[DashboardOutlineDTO] = []
        for node in outline_nodes:
            row = outline_by_id.get(node.id)
            if not row:
                continue
            result.append(
                DashboardOutlineDTO(
                    outline_item_bid=row.outline_item_bid or node.bid,
                    title=row.title or "",
                    type=int(row.type or 0),
                    hidden=bool(row.hidden),
                    parent_bid=row.parent_bid or "",
                    position=row.position or "",
                )
            )
        return result


def _parse_bool(raw: object, default: bool = False) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


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


def _iter_days(start: date, end: date) -> Iterable[date]:
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)


def _chunked(seq: Sequence[str], size: int = 800) -> Iterable[List[str]]:
    for idx in range(0, len(seq), size):
        yield list(seq[idx : idx + size])


def _load_latest_progress_records(
    shifu_bid: str,
    *,
    outline_item_bids: Optional[List[str]] = None,
    user_bids: Optional[List[str]] = None,
) -> List[LearnProgressRecord]:
    base = db.session.query(db.func.max(LearnProgressRecord.id).label("max_id")).filter(
        LearnProgressRecord.shifu_bid == shifu_bid,
        LearnProgressRecord.deleted == 0,
        LearnProgressRecord.status != LEARN_STATUS_RESET,
    )
    if outline_item_bids:
        base = base.filter(LearnProgressRecord.outline_item_bid.in_(outline_item_bids))
    if user_bids:
        base = base.filter(LearnProgressRecord.user_bid.in_(user_bids))
    subquery = base.group_by(
        LearnProgressRecord.user_bid, LearnProgressRecord.outline_item_bid
    ).subquery()

    # id IN (SELECT max_id ...) keeps it join-free.
    return (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.id.in_(db.session.query(subquery.c.max_id))
        )
        .order_by(LearnProgressRecord.id.asc())
        .all()
    )


def _load_learner_bids(shifu_bid: str) -> List[str]:
    rows = (
        db.session.query(LearnProgressRecord.user_bid)
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .distinct()
        .all()
    )
    return [row[0] for row in rows if row and row[0]]


def _required_outline_bids(
    outlines: List[DashboardOutlineDTO],
    *,
    include_trial: bool,
    include_guest: bool,
) -> List[str]:
    allowed_types = {UNIT_TYPE_VALUE_NORMAL}
    if include_trial:
        allowed_types.add(UNIT_TYPE_VALUE_TRIAL)
    if include_guest:
        allowed_types.add(UNIT_TYPE_VALUE_GUEST)
    return [
        item.outline_item_bid
        for item in outlines
        if not item.hidden and int(item.type) in allowed_types
    ]


def _count_follow_ups_by_day(
    shifu_bid: str,
    *,
    start_dt: datetime,
    end_dt_exclusive: datetime,
) -> Dict[str, int]:
    rows = (
        db.session.query(
            db.func.date(LearnGeneratedBlock.created_at).label("d"),
            db.func.count(LearnGeneratedBlock.id).label("c"),
        )
        .filter(
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.created_at >= start_dt,
            LearnGeneratedBlock.created_at < end_dt_exclusive,
        )
        .group_by(db.func.date(LearnGeneratedBlock.created_at))
        .order_by(db.func.date(LearnGeneratedBlock.created_at).asc())
        .all()
    )
    result: Dict[str, int] = {}
    for d, c in rows:
        if not d:
            continue
        result[str(d)] = int(c or 0)
    return result


def _count_follow_ups_total(
    shifu_bid: str,
    *,
    start_dt: datetime,
    end_dt_exclusive: datetime,
) -> int:
    return int(
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.created_at >= start_dt,
            LearnGeneratedBlock.created_at < end_dt_exclusive,
        ).count()
    )


def _top_outlines_by_follow_ups(
    shifu_bid: str,
    *,
    start_dt: datetime,
    end_dt_exclusive: datetime,
    limit: int = 10,
) -> List[Tuple[str, int]]:
    rows = (
        db.session.query(
            LearnGeneratedBlock.outline_item_bid.label("outline_bid"),
            db.func.count(LearnGeneratedBlock.id).label("c"),
        )
        .filter(
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.created_at >= start_dt,
            LearnGeneratedBlock.created_at < end_dt_exclusive,
        )
        .group_by(LearnGeneratedBlock.outline_item_bid)
        .order_by(db.func.count(LearnGeneratedBlock.id).desc())
        .limit(limit)
        .all()
    )
    return [(str(outline_bid or ""), int(c or 0)) for outline_bid, c in rows]


def _top_learners_by_follow_ups(
    shifu_bid: str,
    *,
    start_dt: datetime,
    end_dt_exclusive: datetime,
    limit: int = 10,
) -> List[Tuple[str, int]]:
    rows = (
        db.session.query(
            LearnGeneratedBlock.user_bid.label("user_bid"),
            db.func.count(LearnGeneratedBlock.id).label("c"),
        )
        .filter(
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.created_at >= start_dt,
            LearnGeneratedBlock.created_at < end_dt_exclusive,
        )
        .group_by(LearnGeneratedBlock.user_bid)
        .order_by(db.func.count(LearnGeneratedBlock.id).desc())
        .limit(limit)
        .all()
    )
    return [(str(user_bid or ""), int(c or 0)) for user_bid, c in rows]


def _load_user_contact_map(user_bids: List[str]) -> Dict[str, Dict[str, str]]:
    if not user_bids:
        return {}

    users = UserEntity.query.filter(
        UserEntity.user_bid.in_(user_bids),
        UserEntity.deleted == 0,
    ).all()
    nickname_map: Dict[str, str] = {
        u.user_bid: (u.nickname or "") for u in users if u and u.user_bid
    }
    identify_map: Dict[str, str] = {
        u.user_bid: (u.user_identify or "") for u in users if u and u.user_bid
    }

    credentials = (
        AuthCredential.query.filter(
            AuthCredential.user_bid.in_(user_bids),
            AuthCredential.deleted == 0,
            AuthCredential.provider_name == "phone",
        )
        .order_by(AuthCredential.id.desc())
        .all()
    )
    phone_map: Dict[str, str] = {}
    for credential in credentials:
        if not credential.user_bid or credential.user_bid in phone_map:
            continue
        phone_map[credential.user_bid] = credential.identifier or ""

    result: Dict[str, Dict[str, str]] = {}
    for user_bid in user_bids:
        identify = identify_map.get(user_bid, "")
        mobile = phone_map.get(user_bid, "")
        if not mobile and identify.isdigit():
            mobile = identify
        result[user_bid] = {
            "nickname": nickname_map.get(user_bid, ""),
            "mobile": mobile or "",
        }
    return result


def build_dashboard_overview(
    app: Flask,
    shifu_bid: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    include_trial: bool = False,
    include_guest: bool = False,
) -> DashboardOverviewDTO:
    """Build an overview payload for a shifu."""
    with app.app_context():
        parsed_start = _parse_iso_date(start_date)
        parsed_end = _parse_iso_date(end_date)
        resolved_start, resolved_end = _resolve_date_range(parsed_start, parsed_end)

        start_dt = datetime.combine(resolved_start, datetime.min.time())
        end_dt_exclusive = datetime.combine(
            resolved_end + timedelta(days=1), datetime.min.time()
        )

        published_outlines = load_published_outlines(app, shifu_bid)
        outline_title_map = {
            item.outline_item_bid: item.title for item in published_outlines
        }
        required_bids = _required_outline_bids(
            published_outlines,
            include_trial=include_trial,
            include_guest=include_guest,
        )
        required_total = len(required_bids)

        learner_bids = _load_learner_bids(shifu_bid)
        learner_count = len(learner_bids)

        completed_by_user: Dict[str, int] = {}
        if required_bids and learner_bids:
            completed_by_user = {bid: 0 for bid in learner_bids}
            latest_rows: List[LearnProgressRecord] = []
            for chunk in _chunked(required_bids):
                latest_rows.extend(
                    _load_latest_progress_records(
                        shifu_bid,
                        outline_item_bids=chunk,
                    )
                )

            required_set = set(required_bids)
            for row in latest_rows:
                if not row.user_bid or row.user_bid not in completed_by_user:
                    continue
                if row.outline_item_bid not in required_set:
                    continue
                status = int(row.status or 0)
                if status == LEARN_STATUS_LOCKED:
                    status = 0
                if status == LEARN_STATUS_COMPLETED:
                    completed_by_user[row.user_bid] += 1

        completion_count = 0
        distribution = {
            "0%": 0,
            "1-25%": 0,
            "26-50%": 0,
            "51-75%": 0,
            "76-99%": 0,
            "100%": 0,
        }
        if learner_bids:
            for user_bid in learner_bids:
                completed = completed_by_user.get(user_bid, 0)
                if required_total > 0 and completed >= required_total:
                    completion_count += 1
                percent = 0.0 if required_total == 0 else (completed / required_total)
                if percent <= 0:
                    distribution["0%"] += 1
                elif percent < 0.26:
                    distribution["1-25%"] += 1
                elif percent < 0.51:
                    distribution["26-50%"] += 1
                elif percent < 0.76:
                    distribution["51-75%"] += 1
                elif percent < 1.0:
                    distribution["76-99%"] += 1
                else:
                    distribution["100%"] += 1

        completion_rate = (
            0.0 if learner_count == 0 else completion_count / learner_count
        )
        follow_up_total = _count_follow_ups_total(
            shifu_bid, start_dt=start_dt, end_dt_exclusive=end_dt_exclusive
        )

        trend_map = _count_follow_ups_by_day(
            shifu_bid, start_dt=start_dt, end_dt_exclusive=end_dt_exclusive
        )
        trend_points = [
            DashboardSeriesPointDTO(label=str(d), value=int(trend_map.get(str(d), 0)))
            for d in _iter_days(resolved_start, resolved_end)
        ]

        top_outlines_raw = _top_outlines_by_follow_ups(
            shifu_bid, start_dt=start_dt, end_dt_exclusive=end_dt_exclusive
        )
        top_outlines = [
            DashboardTopOutlineDTO(
                outline_item_bid=outline_bid,
                title=outline_title_map.get(outline_bid, ""),
                ask_count=count,
            )
            for outline_bid, count in top_outlines_raw
            if outline_bid
        ]

        top_learners_raw = _top_learners_by_follow_ups(
            shifu_bid, start_dt=start_dt, end_dt_exclusive=end_dt_exclusive
        )
        top_learner_bids = [user_bid for user_bid, _ in top_learners_raw if user_bid]
        user_contact_map = _load_user_contact_map(top_learner_bids)
        top_learners = [
            DashboardTopLearnerDTO(
                user_bid=user_bid,
                nickname=user_contact_map.get(user_bid, {}).get("nickname", ""),
                mobile=user_contact_map.get(user_bid, {}).get("mobile", ""),
                ask_count=count,
            )
            for user_bid, count in top_learners_raw
            if user_bid
        ]

        return DashboardOverviewDTO(
            kpis=DashboardOverviewKpiDTO(
                learner_count=learner_count,
                completion_count=completion_count,
                completion_rate=float(completion_rate),
                required_outline_total=required_total,
                follow_up_ask_total=follow_up_total,
            ),
            progress_distribution=[
                DashboardSeriesPointDTO(label=label, value=value)
                for label, value in distribution.items()
            ],
            follow_up_trend=trend_points,
            top_outlines_by_follow_ups=top_outlines,
            top_learners_by_follow_ups=top_learners,
            start_date=str(resolved_start),
            end_date=str(resolved_end),
        )


def _search_user_bids(keyword: str) -> List[str]:
    normalized = str(keyword or "").strip()
    if not normalized:
        return []

    like_pattern = f"%{normalized}%"
    user_bids: set[str] = set()

    users = (
        UserEntity.query.filter(
            UserEntity.deleted == 0,
            or_(
                UserEntity.user_bid.like(like_pattern),
                UserEntity.nickname.like(like_pattern),
                UserEntity.user_identify.like(like_pattern),
            ),
        )
        .order_by(UserEntity.id.desc())
        .all()
    )
    for user in users:
        if user and user.user_bid:
            user_bids.add(user.user_bid)

    credentials = (
        AuthCredential.query.filter(
            AuthCredential.deleted == 0,
            AuthCredential.provider_name == "phone",
            AuthCredential.identifier.like(like_pattern),
        )
        .order_by(AuthCredential.id.desc())
        .all()
    )
    for credential in credentials:
        if credential and credential.user_bid:
            user_bids.add(credential.user_bid)

    return list(user_bids)


def _load_last_active_map(shifu_bid: str, user_bids: List[str]) -> Dict[str, datetime]:
    if not user_bids:
        return {}
    result: Dict[str, datetime] = {}
    for chunk in _chunked(user_bids):
        rows = (
            db.session.query(
                LearnProgressRecord.user_bid.label("user_bid"),
                db.func.max(LearnProgressRecord.updated_at).label("last_active"),
            )
            .filter(
                LearnProgressRecord.shifu_bid == shifu_bid,
                LearnProgressRecord.deleted == 0,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
                LearnProgressRecord.user_bid.in_(chunk),
            )
            .group_by(LearnProgressRecord.user_bid)
            .all()
        )
        for user_bid, last_active in rows:
            if not user_bid or not last_active:
                continue
            result[str(user_bid)] = last_active
    return result


def _load_follow_up_count_map(
    shifu_bid: str,
    user_bids: List[str],
) -> Dict[str, int]:
    if not user_bids:
        return {}
    result: Dict[str, int] = {}
    for chunk in _chunked(user_bids):
        rows = (
            db.session.query(
                LearnGeneratedBlock.user_bid.label("user_bid"),
                db.func.count(LearnGeneratedBlock.id).label("c"),
            )
            .filter(
                LearnGeneratedBlock.shifu_bid == shifu_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
                LearnGeneratedBlock.user_bid.in_(chunk),
            )
            .group_by(LearnGeneratedBlock.user_bid)
            .all()
        )
        for user_bid, c in rows:
            if not user_bid:
                continue
            result[str(user_bid)] = int(c or 0)
    return result


def _load_completed_count_map(
    shifu_bid: str,
    required_outline_bids: List[str],
    user_bids: List[str],
) -> Dict[str, int]:
    if not required_outline_bids or not user_bids:
        return {}

    completed: Dict[str, int] = {bid: 0 for bid in user_bids}

    outline_chunks = (
        list(_chunked(required_outline_bids))
        if len(required_outline_bids) > 800
        else [required_outline_bids]
    )
    for outline_chunk in outline_chunks:
        for user_chunk in _chunked(user_bids):
            rows = _load_latest_progress_records(
                shifu_bid,
                outline_item_bids=outline_chunk,
                user_bids=user_chunk,
            )
            for row in rows:
                if not row.user_bid:
                    continue
                if int(row.status or 0) == LEARN_STATUS_COMPLETED:
                    completed[row.user_bid] = completed.get(row.user_bid, 0) + 1
    return completed


def list_dashboard_learners(
    app: Flask,
    shifu_bid: str,
    *,
    page_index: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    sort: Optional[str] = None,
) -> PageNationDTO:
    with app.app_context():
        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = max(int(page_size or 20), 1)
        safe_page_size = min(safe_page_size, 100)

        published_outlines = load_published_outlines(app, shifu_bid)
        required_bids = _required_outline_bids(
            published_outlines, include_trial=False, include_guest=False
        )
        required_total = len(required_bids)

        learner_bids_all = _load_learner_bids(shifu_bid)
        if keyword and str(keyword).strip():
            matched_bids = set(_search_user_bids(str(keyword)))
            learner_bids = [bid for bid in learner_bids_all if bid in matched_bids]
        else:
            learner_bids = learner_bids_all

        total = len(learner_bids)
        if total == 0:
            return PageNationDTO(safe_page_index, safe_page_size, 0, [])

        page_count = (total + safe_page_size - 1) // safe_page_size
        safe_page_index = min(safe_page_index, max(page_count, 1))

        last_active_map = _load_last_active_map(shifu_bid, learner_bids)
        follow_up_count_map = _load_follow_up_count_map(shifu_bid, learner_bids)
        completed_count_map = _load_completed_count_map(
            shifu_bid, required_bids, learner_bids
        )
        user_contact_map = _load_user_contact_map(learner_bids)

        items: List[DashboardLearnerSummaryDTO] = []
        for user_bid in learner_bids:
            contact = user_contact_map.get(user_bid, {})
            completed = completed_count_map.get(user_bid, 0)
            percent = 0.0 if required_total == 0 else completed / required_total
            last_active_dt = last_active_map.get(user_bid)
            items.append(
                DashboardLearnerSummaryDTO(
                    user_bid=user_bid,
                    nickname=contact.get("nickname", ""),
                    mobile=contact.get("mobile", ""),
                    required_outline_total=required_total,
                    completed_outline_count=completed,
                    progress_percent=float(percent),
                    last_active_at=last_active_dt.isoformat() if last_active_dt else "",
                    follow_up_ask_count=follow_up_count_map.get(user_bid, 0),
                )
            )

        normalized_sort = str(sort or "").strip()
        if normalized_sort == "progress_desc":
            items.sort(
                key=lambda item: (item.progress_percent, item.last_active_at),
                reverse=True,
            )
        elif normalized_sort == "followups_desc":
            items.sort(
                key=lambda item: (item.follow_up_ask_count, item.last_active_at),
                reverse=True,
            )
        else:
            items.sort(key=lambda item: item.last_active_at, reverse=True)

        start = (safe_page_index - 1) * safe_page_size
        page_items = items[start : start + safe_page_size]
        return PageNationDTO(safe_page_index, safe_page_size, total, page_items)


def build_dashboard_learner_detail(
    app: Flask,
    shifu_bid: str,
    user_bid: str,
) -> DashboardLearnerDetailDTO:
    with app.app_context():
        published_outlines = load_published_outlines(app, shifu_bid)
        outline_bids = [item.outline_item_bid for item in published_outlines]
        outline_title_map = {
            item.outline_item_bid: item.title for item in published_outlines
        }

        progress_map: Dict[str, LearnProgressRecord] = {}
        if outline_bids:
            latest_rows = _load_latest_progress_records(
                shifu_bid,
                outline_item_bids=outline_bids,
                user_bids=[user_bid],
            )
            progress_map = {
                row.outline_item_bid: row
                for row in latest_rows
                if row and row.outline_item_bid
            }

        outline_progress: List[DashboardLearnerOutlineProgressDTO] = []
        for outline in published_outlines:
            row = progress_map.get(outline.outline_item_bid)
            status = LEARN_STATUS_NOT_STARTED
            block_position = 0
            updated_at = ""
            if row:
                raw_status = int(row.status or LEARN_STATUS_NOT_STARTED)
                status = (
                    LEARN_STATUS_NOT_STARTED
                    if raw_status == LEARN_STATUS_LOCKED
                    else raw_status
                )
                block_position = int(row.block_position or 0)
                updated_at = row.updated_at.isoformat() if row.updated_at else ""
            outline_progress.append(
                DashboardLearnerOutlineProgressDTO(
                    outline_item_bid=outline.outline_item_bid,
                    title=outline.title,
                    type=int(outline.type),
                    hidden=bool(outline.hidden),
                    status=int(status),
                    block_position=block_position,
                    updated_at=updated_at,
                )
            )

        contact_map = _load_user_contact_map([user_bid])
        contact = contact_map.get(user_bid, {})

        variables_dict = get_user_profiles(app, user_bid, shifu_bid) or {}
        variables = [
            DashboardLearnerVariableDTO(key=str(key), value=str(value))
            for key, value in sorted(variables_dict.items(), key=lambda item: item[0])
        ]

        follow_up_rows = (
            db.session.query(
                LearnGeneratedBlock.outline_item_bid.label("outline_bid"),
                db.func.count(LearnGeneratedBlock.id).label("c"),
            )
            .filter(
                LearnGeneratedBlock.shifu_bid == shifu_bid,
                LearnGeneratedBlock.user_bid == user_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            )
            .group_by(LearnGeneratedBlock.outline_item_bid)
            .order_by(db.func.count(LearnGeneratedBlock.id).desc())
            .all()
        )
        by_outline: List[DashboardTopOutlineDTO] = []
        total_asks = 0
        for outline_bid, c in follow_up_rows:
            outline_bid_str = str(outline_bid or "")
            if not outline_bid_str:
                continue
            count = int(c or 0)
            total_asks += count
            by_outline.append(
                DashboardTopOutlineDTO(
                    outline_item_bid=outline_bid_str,
                    title=outline_title_map.get(outline_bid_str, ""),
                    ask_count=count,
                )
            )

        return DashboardLearnerDetailDTO(
            user_bid=user_bid,
            nickname=contact.get("nickname", ""),
            mobile=contact.get("mobile", ""),
            outlines=outline_progress,
            variables=variables,
            followups=DashboardLearnerFollowUpSummaryDTO(
                total_ask_count=total_asks, by_outline=by_outline
            ),
        )


def _parse_datetime_value(
    raw: Optional[str], *, is_end: bool = False
) -> Optional[datetime]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt == "%Y-%m-%d":
                if is_end:
                    parsed = parsed.replace(hour=23, minute=59, second=59)
                else:
                    parsed = parsed.replace(hour=0, minute=0, second=0)
            return parsed
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text)
        if (
            is_end
            and parsed.time() == datetime.min.time()
            and "T" not in text
            and " " not in text
        ):
            parsed = parsed.replace(hour=23, minute=59, second=59)
        return parsed
    except ValueError:
        raise_param_error(f"invalid datetime: {text}")


def list_dashboard_followups(
    app: Flask,
    shifu_bid: str,
    user_bid: str,
    *,
    outline_item_bid: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    page_index: int = 1,
    page_size: int = 20,
) -> PageNationDTO:
    with app.app_context():
        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = max(int(page_size or 20), 1)
        safe_page_size = min(safe_page_size, 100)

        start_dt = _parse_datetime_value(start_time, is_end=False)
        end_dt = _parse_datetime_value(end_time, is_end=True)
        if start_dt and end_dt and start_dt > end_dt:
            raise_param_error("start_time must be <= end_time")

        if start_dt is None and end_dt is None:
            resolved_start, resolved_end = _resolve_date_range(
                None, None, default_days=30
            )
            start_dt = datetime.combine(resolved_start, datetime.min.time())
            end_dt = datetime.combine(
                resolved_end, datetime.max.time().replace(microsecond=0)
            )

        published_outlines = load_published_outlines(app, shifu_bid)
        outline_title_map = {
            item.outline_item_bid: item.title for item in published_outlines
        }

        ask_query = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.user_bid == user_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
        )
        if outline_item_bid:
            ask_query = ask_query.filter(
                LearnGeneratedBlock.outline_item_bid == outline_item_bid
            )
        if start_dt:
            ask_query = ask_query.filter(LearnGeneratedBlock.created_at >= start_dt)
        if end_dt:
            ask_query = ask_query.filter(LearnGeneratedBlock.created_at <= end_dt)

        total = int(ask_query.count())
        if total == 0:
            return PageNationDTO(safe_page_index, safe_page_size, 0, [])

        page_count = (total + safe_page_size - 1) // safe_page_size
        safe_page_index = min(safe_page_index, max(page_count, 1))
        offset = (safe_page_index - 1) * safe_page_size

        asks: List[LearnGeneratedBlock] = (
            ask_query.order_by(
                LearnGeneratedBlock.created_at.desc(), LearnGeneratedBlock.id.desc()
            )
            .offset(offset)
            .limit(safe_page_size)
            .all()
        )

        progress_record_bids = sorted(
            {a.progress_record_bid for a in asks if a and a.progress_record_bid}
        )
        positions = sorted({int(a.position or 0) for a in asks})

        answer_map: Dict[Tuple[str, int], List[LearnGeneratedBlock]] = {}
        if progress_record_bids:
            answer_query = LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.shifu_bid == shifu_bid,
                LearnGeneratedBlock.user_bid == user_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.type == BLOCK_TYPE_MDANSWER_VALUE,
                LearnGeneratedBlock.progress_record_bid.in_(progress_record_bids),
                LearnGeneratedBlock.position.in_(positions),
            )
            if outline_item_bid:
                answer_query = answer_query.filter(
                    LearnGeneratedBlock.outline_item_bid == outline_item_bid
                )
            if start_dt:
                answer_query = answer_query.filter(
                    LearnGeneratedBlock.created_at >= start_dt
                )
            if end_dt:
                answer_query = answer_query.filter(
                    LearnGeneratedBlock.created_at <= end_dt
                )

            answers: List[LearnGeneratedBlock] = answer_query.order_by(
                LearnGeneratedBlock.created_at.asc(), LearnGeneratedBlock.id.asc()
            ).all()
            for answer in answers:
                key = (answer.progress_record_bid or "", int(answer.position or 0))
                if not key[0]:
                    continue
                answer_map.setdefault(key, []).append(answer)

        items: List[DashboardFollowUpItemDTO] = []
        for ask in asks:
            outline_bid = ask.outline_item_bid or ""
            key = (ask.progress_record_bid or "", int(ask.position or 0))
            matched_answer = None
            candidates = answer_map.get(key, [])
            if candidates:
                for candidate in candidates:
                    if not candidate.created_at or not ask.created_at:
                        matched_answer = candidate
                        break
                    if candidate.created_at >= ask.created_at:
                        matched_answer = candidate
                        break

            items.append(
                DashboardFollowUpItemDTO(
                    outline_item_bid=outline_bid,
                    outline_title=outline_title_map.get(outline_bid, ""),
                    position=int(ask.position or 0),
                    asked_at=ask.created_at.isoformat() if ask.created_at else "",
                    question=ask.generated_content or "",
                    answered_at=matched_answer.created_at.isoformat()
                    if matched_answer and matched_answer.created_at
                    else "",
                    answer=matched_answer.generated_content if matched_answer else "",
                )
            )

        return PageNationDTO(safe_page_index, safe_page_size, total, items)
