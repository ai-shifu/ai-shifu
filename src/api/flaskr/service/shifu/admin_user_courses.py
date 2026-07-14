"""Operator user learning/created course map helpers.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Sequence, Set
from flaskr.dao import db
from flaskr.service.learn.const import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_RESET,
)
from flaskr.service.learn.models import (
    LearnProgressRecord,
)
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.shifu.admin_dtos_users import (
    AdminOperationUserCourseSummaryDTO,
)
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)

from flaskr.service.shifu.admin_course_summaries import (
    _load_latest_courses_by_shifu_bids,
    _load_latest_shifus,
    _merge_courses,
    _resolve_course_status,
)


def _build_operator_user_course_summary(
    course,
    published_bids: Set[str],
    *,
    completed_lesson_count: int = 0,
    total_lesson_count: int = 0,
) -> AdminOperationUserCourseSummaryDTO:
    return AdminOperationUserCourseSummaryDTO(
        shifu_bid=course.shifu_bid or "",
        course_name=course.title or "",
        course_status=_resolve_course_status(course.shifu_bid or "", published_bids),
        completed_lesson_count=max(int(completed_lesson_count or 0), 0),
        total_lesson_count=max(int(total_lesson_count or 0), 0),
    )


def _load_visible_published_leaf_outline_bids_by_shifu(
    shifu_bids: Sequence[str],
) -> Dict[str, list[str]]:
    normalized_shifu_bids = [
        str(shifu_bid or "").strip() for shifu_bid in shifu_bids if shifu_bid
    ]
    if not normalized_shifu_bids:
        return {}

    latest_outline_subquery = (
        db.session.query(db.func.max(PublishedOutlineItem.id).label("max_id"))
        .filter(PublishedOutlineItem.shifu_bid.in_(normalized_shifu_bids))
        .group_by(
            PublishedOutlineItem.shifu_bid,
            PublishedOutlineItem.outline_item_bid,
        )
        .subquery()
    )
    outline_rows = (
        db.session.query(
            PublishedOutlineItem.shifu_bid,
            PublishedOutlineItem.outline_item_bid,
            PublishedOutlineItem.parent_bid,
        )
        .filter(
            PublishedOutlineItem.id.in_(
                db.session.query(latest_outline_subquery.c.max_id)
            ),
            PublishedOutlineItem.deleted == 0,
            PublishedOutlineItem.hidden == 0,
        )
        .all()
    )

    visible_bids_by_shifu: Dict[str, Set[str]] = {}
    parent_bids_by_shifu: Dict[str, Set[str]] = {}
    for shifu_bid, outline_item_bid, parent_bid in outline_rows:
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_outline_item_bid = str(outline_item_bid or "").strip()
        normalized_parent_bid = str(parent_bid or "").strip()
        if not normalized_shifu_bid or not normalized_outline_item_bid:
            continue
        visible_bids_by_shifu.setdefault(normalized_shifu_bid, set()).add(
            normalized_outline_item_bid
        )
        if normalized_parent_bid:
            parent_bids_by_shifu.setdefault(normalized_shifu_bid, set()).add(
                normalized_parent_bid
            )

    return {
        shifu_bid: sorted(
            outline_item_bid
            for outline_item_bid in visible_bids
            if outline_item_bid not in parent_bids_by_shifu.get(shifu_bid, set())
        )
        for shifu_bid, visible_bids in visible_bids_by_shifu.items()
    }


def _is_completed_leaf_progress_statuses(record_statuses: Sequence[int]) -> bool:
    if not record_statuses:
        return False
    return int(record_statuses[-1] or 0) == LEARN_STATUS_COMPLETED


def _load_learning_progress_counts_by_user_and_course(
    user_bids: Sequence[str],
    shifu_bids: Sequence[str],
    leaf_outline_bids_by_shifu: Dict[str, list[str]],
) -> Dict[tuple[str, str], tuple[int, int]]:
    normalized_user_bids = [
        str(user_bid or "").strip() for user_bid in user_bids if user_bid
    ]
    normalized_shifu_bids = [
        str(shifu_bid or "").strip() for shifu_bid in shifu_bids if shifu_bid
    ]
    if not normalized_user_bids or not normalized_shifu_bids:
        return {}

    all_leaf_outline_bids = sorted(
        {
            outline_item_bid
            for outline_item_bids in leaf_outline_bids_by_shifu.values()
            for outline_item_bid in outline_item_bids
            if outline_item_bid
        }
    )
    if not all_leaf_outline_bids:
        return {}

    leaf_outline_bids_by_shifu_set = {
        shifu_bid: set(outline_item_bids)
        for shifu_bid, outline_item_bids in leaf_outline_bids_by_shifu.items()
    }

    progress_rows = (
        db.session.query(
            LearnProgressRecord.user_bid,
            LearnProgressRecord.shifu_bid,
            LearnProgressRecord.outline_item_bid,
            LearnProgressRecord.status,
        )
        .filter(
            LearnProgressRecord.user_bid.in_(normalized_user_bids),
            LearnProgressRecord.shifu_bid.in_(normalized_shifu_bids),
            LearnProgressRecord.outline_item_bid.in_(all_leaf_outline_bids),
            LearnProgressRecord.deleted == 0,
        )
        .order_by(
            LearnProgressRecord.user_bid.asc(),
            LearnProgressRecord.shifu_bid.asc(),
            LearnProgressRecord.outline_item_bid.asc(),
            LearnProgressRecord.created_at.asc(),
            LearnProgressRecord.id.asc(),
        )
        .all()
    )

    statuses_by_user_course_outline: Dict[tuple[str, str, str], list[int]] = {}
    for user_bid, shifu_bid, outline_item_bid, status in progress_rows:
        normalized_user_bid = str(user_bid or "").strip()
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_outline_item_bid = str(outline_item_bid or "").strip()
        if (
            not normalized_user_bid
            or not normalized_shifu_bid
            or not normalized_outline_item_bid
        ):
            continue
        if normalized_outline_item_bid not in leaf_outline_bids_by_shifu_set.get(
            normalized_shifu_bid, set()
        ):
            continue
        statuses_by_user_course_outline.setdefault(
            (
                normalized_user_bid,
                normalized_shifu_bid,
                normalized_outline_item_bid,
            ),
            [],
        ).append(int(status or 0))

    completed_counts_by_user_course: Dict[tuple[str, str], int] = {}
    for (
        user_bid,
        shifu_bid,
        _outline_item_bid,
    ), record_statuses in statuses_by_user_course_outline.items():
        if not _is_completed_leaf_progress_statuses(record_statuses):
            continue
        completed_counts_by_user_course[(user_bid, shifu_bid)] = (
            completed_counts_by_user_course.get((user_bid, shifu_bid), 0) + 1
        )

    progress_counts: Dict[tuple[str, str], tuple[int, int]] = {}
    for user_bid in normalized_user_bids:
        for shifu_bid in normalized_shifu_bids:
            total_lesson_count = len(leaf_outline_bids_by_shifu.get(shifu_bid, []))
            if total_lesson_count <= 0:
                continue
            progress_counts[(user_bid, shifu_bid)] = (
                completed_counts_by_user_course.get((user_bid, shifu_bid), 0),
                total_lesson_count,
            )
    return progress_counts


def _load_operator_user_course_maps(
    user_bids: Sequence[str],
) -> tuple[
    Dict[str, list[AdminOperationUserCourseSummaryDTO]],
    Dict[str, list[AdminOperationUserCourseSummaryDTO]],
]:
    normalized_user_bids = [
        str(user_bid or "").strip() for user_bid in user_bids if user_bid
    ]
    if not normalized_user_bids:
        return {}, {}

    created_courses_map: Dict[str, list[AdminOperationUserCourseSummaryDTO]] = {
        user_bid: [] for user_bid in normalized_user_bids
    }
    learning_courses_map: Dict[str, list[AdminOperationUserCourseSummaryDTO]] = {
        user_bid: [] for user_bid in normalized_user_bids
    }

    creator_bids = set(normalized_user_bids)
    created_drafts = _load_latest_shifus(
        DraftShifu,
        shifu_bid="",
        course_name="",
        creator_bids=creator_bids,
        start_time=None,
        end_time=None,
        updated_start_time=None,
        updated_end_time=None,
        lightweight=True,
    )
    created_published = _load_latest_shifus(
        PublishedShifu,
        shifu_bid="",
        course_name="",
        creator_bids=creator_bids,
        start_time=None,
        end_time=None,
        updated_start_time=None,
        updated_end_time=None,
        lightweight=True,
    )
    merged_created_courses, created_published_bids, _ = _merge_courses(
        created_drafts,
        created_published,
    )
    for course in merged_created_courses:
        creator_user_bid = str(course.created_user_bid or "").strip()
        if creator_user_bid not in created_courses_map:
            continue
        created_courses_map[creator_user_bid].append(
            _build_operator_user_course_summary(course, created_published_bids)
        )

    learned_activity_subquery = (
        db.session.query(
            Order.user_bid.label("user_bid"),
            Order.shifu_bid.label("shifu_bid"),
            Order.created_at.label("activity_at"),
        )
        .filter(
            Order.deleted == 0,
            Order.status == ORDER_STATUS_SUCCESS,
            Order.user_bid.in_(normalized_user_bids),
            Order.shifu_bid != "",
        )
        .union_all(
            db.session.query(
                LearnProgressRecord.user_bid.label("user_bid"),
                LearnProgressRecord.shifu_bid.label("shifu_bid"),
                LearnProgressRecord.updated_at.label("activity_at"),
            ).filter(
                LearnProgressRecord.deleted == 0,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
                LearnProgressRecord.user_bid.in_(normalized_user_bids),
                LearnProgressRecord.shifu_bid != "",
            ),
            db.session.query(
                AiCourseAuth.user_id.label("user_bid"),
                AiCourseAuth.course_id.label("shifu_bid"),
                db.func.coalesce(
                    AiCourseAuth.updated_at,
                    AiCourseAuth.created_at,
                ).label("activity_at"),
            ).filter(
                AiCourseAuth.status == 1,
                AiCourseAuth.user_id.in_(normalized_user_bids),
                AiCourseAuth.course_id != "",
            ),
        )
        .subquery()
    )
    learned_rows = (
        db.session.query(
            learned_activity_subquery.c.user_bid.label("user_bid"),
            learned_activity_subquery.c.shifu_bid.label("shifu_bid"),
            db.func.max(learned_activity_subquery.c.activity_at).label(
                "last_activity_at"
            ),
        )
        .group_by(
            learned_activity_subquery.c.user_bid,
            learned_activity_subquery.c.shifu_bid,
        )
        .all()
    )
    learned_shifu_bids = sorted(
        {
            str(row.shifu_bid or "").strip()
            for row in learned_rows
            if str(row.shifu_bid or "").strip()
        }
    )
    learned_drafts = _load_latest_courses_by_shifu_bids(
        DraftShifu,
        learned_shifu_bids,
        lightweight=True,
    )
    learned_published = _load_latest_courses_by_shifu_bids(
        PublishedShifu,
        learned_shifu_bids,
        lightweight=True,
    )
    merged_learned_courses, learned_published_bids, _ = _merge_courses(
        learned_drafts,
        learned_published,
    )
    learning_progress_counts = _load_learning_progress_counts_by_user_and_course(
        normalized_user_bids,
        learned_shifu_bids,
        _load_visible_published_leaf_outline_bids_by_shifu(learned_shifu_bids),
    )
    learned_course_map = {
        str(course.shifu_bid or "").strip(): course for course in merged_learned_courses
    }
    sorted_learned_rows = sorted(
        learned_rows,
        key=lambda row: (
            row.last_activity_at or datetime.min,
            str(row.shifu_bid or "").strip(),
        ),
        reverse=True,
    )
    for row in sorted_learned_rows:
        resolved_user_bid = str(row.user_bid or "").strip()
        resolved_shifu_bid = str(row.shifu_bid or "").strip()
        if not resolved_user_bid or not resolved_shifu_bid:
            continue
        course = learned_course_map.get(resolved_shifu_bid)
        if course is None:
            continue
        completed_lesson_count, total_lesson_count = learning_progress_counts.get(
            (resolved_user_bid, resolved_shifu_bid),
            (0, 0),
        )
        learning_courses_map[resolved_user_bid].append(
            _build_operator_user_course_summary(
                course,
                learned_published_bids,
                completed_lesson_count=completed_lesson_count,
                total_lesson_count=total_lesson_count,
            )
        )

    return created_courses_map, learning_courses_map


def _load_operator_user_course_count_maps(
    user_bids: Sequence[str],
) -> tuple[Dict[str, int], Dict[str, int]]:
    normalized_user_bids = [
        str(user_bid or "").strip() for user_bid in user_bids if user_bid
    ]
    if not normalized_user_bids:
        return {}, {}

    created_course_count_map = {user_bid: 0 for user_bid in normalized_user_bids}
    learning_course_count_map = {user_bid: 0 for user_bid in normalized_user_bids}

    creator_bids = set(normalized_user_bids)
    created_drafts = _load_latest_shifus(
        DraftShifu,
        shifu_bid="",
        course_name="",
        creator_bids=creator_bids,
        start_time=None,
        end_time=None,
        updated_start_time=None,
        updated_end_time=None,
        lightweight=True,
    )
    created_published = _load_latest_shifus(
        PublishedShifu,
        shifu_bid="",
        course_name="",
        creator_bids=creator_bids,
        start_time=None,
        end_time=None,
        updated_start_time=None,
        updated_end_time=None,
        lightweight=True,
    )
    merged_created_courses, _, _ = _merge_courses(created_drafts, created_published)
    for course in merged_created_courses:
        creator_user_bid = str(course.created_user_bid or "").strip()
        if creator_user_bid not in created_course_count_map:
            continue
        created_course_count_map[creator_user_bid] += 1

    learned_activity_subquery = (
        db.session.query(
            Order.user_bid.label("user_bid"),
            Order.shifu_bid.label("shifu_bid"),
            Order.created_at.label("activity_at"),
        )
        .filter(
            Order.deleted == 0,
            Order.status == ORDER_STATUS_SUCCESS,
            Order.user_bid.in_(normalized_user_bids),
            Order.shifu_bid != "",
        )
        .union_all(
            db.session.query(
                LearnProgressRecord.user_bid.label("user_bid"),
                LearnProgressRecord.shifu_bid.label("shifu_bid"),
                LearnProgressRecord.updated_at.label("activity_at"),
            ).filter(
                LearnProgressRecord.deleted == 0,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
                LearnProgressRecord.user_bid.in_(normalized_user_bids),
                LearnProgressRecord.shifu_bid != "",
            ),
            db.session.query(
                AiCourseAuth.user_id.label("user_bid"),
                AiCourseAuth.course_id.label("shifu_bid"),
                db.func.coalesce(
                    AiCourseAuth.updated_at,
                    AiCourseAuth.created_at,
                ).label("activity_at"),
            ).filter(
                AiCourseAuth.status == 1,
                AiCourseAuth.user_id.in_(normalized_user_bids),
                AiCourseAuth.course_id != "",
            ),
        )
        .subquery()
    )
    learned_rows = (
        db.session.query(
            learned_activity_subquery.c.user_bid.label("user_bid"),
            learned_activity_subquery.c.shifu_bid.label("shifu_bid"),
        )
        .group_by(
            learned_activity_subquery.c.user_bid,
            learned_activity_subquery.c.shifu_bid,
        )
        .all()
    )
    learned_shifu_bids = sorted(
        {
            str(row.shifu_bid or "").strip()
            for row in learned_rows
            if str(row.shifu_bid or "").strip()
        }
    )
    learned_drafts = _load_latest_courses_by_shifu_bids(
        DraftShifu,
        learned_shifu_bids,
        lightweight=True,
    )
    learned_published = _load_latest_courses_by_shifu_bids(
        PublishedShifu,
        learned_shifu_bids,
        lightweight=True,
    )
    merged_learned_courses, _, _ = _merge_courses(learned_drafts, learned_published)
    visible_learned_shifu_bids = {
        str(course.shifu_bid or "").strip()
        for course in merged_learned_courses
        if str(course.shifu_bid or "").strip()
    }
    for row in learned_rows:
        resolved_user_bid = str(row.user_bid or "").strip()
        resolved_shifu_bid = str(row.shifu_bid or "").strip()
        if (
            resolved_user_bid not in learning_course_count_map
            or resolved_shifu_bid not in visible_learned_shifu_bids
        ):
            continue
        learning_course_count_map[resolved_user_bid] += 1

    return created_course_count_map, learning_course_count_map
