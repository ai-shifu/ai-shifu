"""Load course, learner, and progress aggregates for dashboard reporting."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.dashboard.common import (
    COURSE_STATUS_PUBLISHED,
    COURSE_STATUS_UNPUBLISHED,
    _DashboardCourseMeta,
    _DashboardEntryMetrics,
)
from flaskr.service.learn.const import ROLE_STUDENT
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnProgressRecord,
)
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_RESET,
    ORDER_STATUS_SUCCESS,
)
from flaskr.service.order.models import Order
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDASK_VALUE,
)
from flaskr.service.shifu.demo_courses import is_builtin_demo_course
from flaskr.service.shifu.models import (
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime


def _load_dashboard_course_user_contact_map(
    user_bids: Sequence[str],
) -> dict[str, dict[str, str]]:
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
    contact_map: dict[str, dict[str, str]] = {
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


def _load_dashboard_course_meta_map(user_id: str) -> dict[str, _DashboardCourseMeta]:
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

    published_rows: list[PublishedShifu] = (
        db.session.query(PublishedShifu)
        .filter(PublishedShifu.id.in_(db.session.query(latest_subquery.c.max_id)))
        .all()
    )
    course_map: dict[str, _DashboardCourseMeta] = {}
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
) -> _DashboardCourseMeta | None:
    normalized_user_id = str(user_id or "").strip()
    normalized_shifu_bid = str(shifu_bid or "").strip()
    if not normalized_user_id or not normalized_shifu_bid:
        return None

    latest_row: PublishedShifu | None = (
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
    keyword: str | None = None,
) -> list[_DashboardCourseMeta]:
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


def _load_dashboard_course_created_at(shifu_bid: str) -> datetime | None:
    latest_draft: DraftShifu | None = (
        DraftShifu.query.filter(
            DraftShifu.shifu_bid == shifu_bid,
            DraftShifu.deleted == 0,
        )
        .order_by(DraftShifu.id.desc())
        .first()
    )
    if latest_draft and latest_draft.created_at:
        return latest_draft.created_at

    return (
        db.session.query(db.func.min(PublishedShifu.created_at))
        .filter(PublishedShifu.shifu_bid == shifu_bid)
        .scalar()
    )


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
) -> list[PublishedOutlineItem]:
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


def _load_course_leaf_outline_bids(shifu_bid: str) -> list[str]:
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

    visible_bids: set[str] = set()
    visible_parent_bids: set[str] = set()
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


def _load_course_learner_bids(shifu_bid: str) -> set[str]:
    learner_bids: set[str] = set()

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
) -> dict[str, UserEntity]:
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
) -> dict[str, datetime]:
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


def _load_dashboard_course_learned_lesson_count_map(
    shifu_bid: str,
    user_bids: Sequence[str],
    leaf_outline_bids: Sequence[str],
) -> dict[str, int]:
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
) -> dict[str, int]:
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


def _load_dashboard_course_completed_learner_bids(
    shifu_bid: str,
    leaf_outline_bids: list[str],
) -> set[str]:
    if not leaf_outline_bids:
        return set()

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

    completed_leaf_bids_by_user: dict[str, set[str]] = {}
    records_by_user_and_outline: dict[tuple[str, str], list[int]] = {}

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
    return {
        user_bid
        for user_bid, completed_outline_bids in completed_leaf_bids_by_user.items()
        if len(completed_outline_bids) >= leaf_count
    }


def _collect_dashboard_entry_metrics(
    shifu_bids: list[str],
    *,
    start_dt: datetime | None,
    end_dt_exclusive: datetime | None,
) -> _DashboardEntryMetrics:
    if not shifu_bids:
        return _DashboardEntryMetrics()

    learner_users_by_course: dict[str, set[str]] = {}

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

    learner_count_map: dict[str, int] = {}
    learner_total_users: set[str] = set()
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
    order_count_map: dict[str, int] = {}
    order_amount_map: dict[str, Decimal] = {}
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
    last_active_map: dict[str, datetime] = {}
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
