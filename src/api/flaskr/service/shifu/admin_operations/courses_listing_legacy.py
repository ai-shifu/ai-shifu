"""In-memory operator course listing used when the SQL path is unavailable.

These loaders and the legacy list/overview builders were split out of
``courses_listing``. They resolve every listing helper through that module at
call time, so a patch on ``courses_listing`` (or one forwarded to it from
``admin_operations.courses`` / ``shifu.admin``) keeps reaching this code.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from flaskr.service.common.pagination import MAX_PAGE_SIZE
from flaskr.service.shifu.admin_dtos_courses import (
    AdminOperationCourseListDTO,
    AdminOperationCourseOverviewDTO,
    AdminOperationCourseSummaryDTO,
)
from flaskr.service.shifu.admin_operations.courses_shared import (
    COURSE_QUICK_FILTER_CREATED_LAST_7D,
    COURSE_QUICK_FILTER_DRAFT,
    COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D,
    COURSE_QUICK_FILTER_PUBLISHED,
    COURSE_STATUS_PUBLISHED,
    COURSE_STATUS_UNPUBLISHED,
)
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.util.datetime import NAIVE_DATETIME_MIN
from sqlalchemy.orm import defer

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

    from flask import Flask
    from flask_sqlalchemy.query import Query
    from flaskr.service.shifu.admin_operations.courses_listing import (
        OperatorCourseListSeed,
    )


def _listing() -> ModuleType:
    """Return ``courses_listing`` so patched helpers resolve at call time."""
    from flaskr.service.shifu.admin_operations import courses_listing

    return courses_listing


def _build_latest_shifus_query(
    model: object,
    *,
    shifu_bid: str,
    course_name: str,
    course_query: str = "",
    matching_course_bids: set[str] | None = None,
    creator_bids: set[str] | None,
    start_time: datetime | None,
    end_time: datetime | None,
    updated_start_time: datetime | None,
    updated_end_time: datetime | None,
    lightweight: bool = False,
) -> Query | list[DraftShifu | PublishedShifu]:
    listing = _listing()
    db = listing.db
    is_mapped_model = hasattr(model, "__mapper__")
    latest_subquery = db.session.query(db.func.max(model.id).label("max_id")).filter(
        model.deleted == 0
    )
    if shifu_bid:
        latest_subquery = latest_subquery.filter(model.shifu_bid == shifu_bid)
    latest_subquery = latest_subquery.group_by(model.shifu_bid).subquery()
    latest_rows = db.session.query(model).filter(
        model.id.in_(db.session.query(latest_subquery.c.max_id))
    )
    if is_mapped_model and not lightweight:
        latest_rows = latest_rows.options(defer(model.llm_system_prompt))
    if course_name:
        latest_rows = latest_rows.filter(model.title.ilike(f"%{course_name}%"))
    course_query_filter = listing._build_operator_course_query_filter(
        model.shifu_bid,
        course_query,
        matching_course_bids=matching_course_bids,
    )
    if course_query_filter is not None:
        latest_rows = latest_rows.filter(course_query_filter)
    if creator_bids is not None:
        if not creator_bids:
            return []
        latest_rows = latest_rows.filter(model.created_user_bid.in_(creator_bids))
    if start_time:
        latest_rows = latest_rows.filter(model.created_at >= start_time)
    if end_time:
        latest_rows = latest_rows.filter(model.created_at <= end_time)
    if updated_start_time:
        latest_rows = latest_rows.filter(model.updated_at >= updated_start_time)
    if updated_end_time:
        latest_rows = latest_rows.filter(model.updated_at <= updated_end_time)
    return latest_rows.order_by(model.updated_at.desc(), model.id.desc())


def _apply_latest_nonempty_model_fields(model: object, rows: object) -> None:
    if not rows:
        return
    db = _listing().db

    shifu_bids = sorted(
        {
            str(getattr(row, "shifu_bid", "") or "").strip()
            for row in rows
            if str(getattr(row, "shifu_bid", "") or "").strip()
        }
    )
    if not shifu_bids:
        return

    latest_nonempty_rows = (
        db.session.query(
            model.shifu_bid.label("shifu_bid"),
            model.tts_model.label("tts_model"),
            db.func.row_number()
            .over(partition_by=model.shifu_bid, order_by=model.id.desc())
            .label("row_num"),
        )
        .filter(
            model.deleted == 0,
            model.shifu_bid.in_(shifu_bids),
            db.func.coalesce(model.tts_model, "") != "",
        )
        .subquery()
    )
    fallback_rows = (
        db.session.query(
            latest_nonempty_rows.c.shifu_bid,
            latest_nonempty_rows.c.tts_model,
        )
        .filter(latest_nonempty_rows.c.row_num == 1)
        .all()
    )
    fallback_map = {
        str(row.shifu_bid or ""): {
            "tts_model": str(getattr(row, "tts_model", "") or ""),
        }
        for row in fallback_rows
    }
    for row in rows:
        fallback = fallback_map.get(str(getattr(row, "shifu_bid", "") or ""))
        if not fallback:
            continue
        if not str(getattr(row, "tts_model", "") or "").strip():
            row.tts_model = fallback["tts_model"]


def _load_latest_shifus(
    model: object,
    *,
    shifu_bid: str,
    course_name: str,
    course_query: str = "",
    matching_course_bids: set[str] | None = None,
    creator_bids: set[str] | None,
    start_time: datetime | None,
    end_time: datetime | None,
    updated_start_time: datetime | None,
    updated_end_time: datetime | None,
    attach_prompt_flags: bool = False,
    lightweight: bool = False,
) -> list[DraftShifu | PublishedShifu | OperatorCourseListSeed]:
    listing = _listing()
    ordered_query = listing._build_latest_shifus_query(
        model,
        shifu_bid=shifu_bid,
        course_name=course_name,
        course_query=course_query,
        matching_course_bids=matching_course_bids,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        updated_start_time=updated_start_time,
        updated_end_time=updated_end_time,
        lightweight=lightweight,
    )
    if isinstance(ordered_query, list):
        return []

    if lightweight and hasattr(model, "__mapper__"):
        rows = ordered_query.with_entities(
            model.id.label("id"),
            model.shifu_bid.label("shifu_bid"),
            model.title.label("title"),
            model.price.label("price"),
            model.llm.label("llm"),
            model.tts_model.label("tts_model"),
            model.created_user_bid.label("created_user_bid"),
            model.updated_user_bid.label("updated_user_bid"),
            model.created_at.label("created_at"),
            model.updated_at.label("updated_at"),
        ).all()
        seeds = [listing._build_operator_course_list_seed(row) for row in rows]
        listing._apply_latest_nonempty_model_fields(model, seeds)
        return seeds

    rows = ordered_query.all()
    if hasattr(model, "__mapper__"):
        listing._apply_latest_nonempty_model_fields(model, rows)
    if hasattr(model, "__mapper__") and attach_prompt_flags:
        listing._attach_course_prompt_flags(model, rows)
    return rows


def _load_latest_shifu_seeds(
    model: object,
    *,
    shifu_bid: str,
    course_name: str,
    course_query: str = "",
    matching_course_bids: set[str] | None = None,
    creator_bids: set[str] | None,
    start_time: datetime | None,
    end_time: datetime | None,
    updated_start_time: datetime | None,
    updated_end_time: datetime | None,
) -> list[OperatorCourseListSeed]:
    listing = _listing()
    ordered_query = listing._build_latest_shifus_query(
        model,
        shifu_bid=shifu_bid,
        course_name=course_name,
        course_query=course_query,
        matching_course_bids=matching_course_bids,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        updated_start_time=updated_start_time,
        updated_end_time=updated_end_time,
        lightweight=True,
    )
    if isinstance(ordered_query, list):
        return []

    rows = ordered_query.with_entities(
        model.id.label("id"),
        model.shifu_bid.label("shifu_bid"),
        model.title.label("title"),
        model.price.label("price"),
        model.llm.label("llm"),
        model.tts_model.label("tts_model"),
        model.created_user_bid.label("created_user_bid"),
        model.updated_user_bid.label("updated_user_bid"),
        model.created_at.label("created_at"),
        model.updated_at.label("updated_at"),
    ).all()
    seeds = [listing._build_operator_course_list_seed(row) for row in rows]
    listing._apply_latest_nonempty_model_fields(model, seeds)
    return seeds


def _build_operator_course_overview_legacy(
    app: Flask,
) -> AdminOperationCourseOverviewDTO:
    listing = _listing()
    _ = app
    draft_rows = listing._load_latest_shifus(
        DraftShifu,
        shifu_bid="",
        course_name="",
        course_query="",
        creator_bids=None,
        start_time=None,
        end_time=None,
        updated_start_time=None,
        updated_end_time=None,
    )
    published_rows = listing._load_latest_shifus(
        PublishedShifu,
        shifu_bid="",
        course_name="",
        course_query="",
        creator_bids=None,
        start_time=None,
        end_time=None,
        updated_start_time=None,
        updated_end_time=None,
    )
    merged_courses, published_bids, _ = listing._merge_courses(
        draft_rows, published_rows
    )
    total_course_count = len(merged_courses)
    if total_course_count == 0:
        return AdminOperationCourseOverviewDTO()

    now = listing.now_utc()
    created_window_start, created_window_end = listing._resolve_created_last_7d_window(
        now
    )
    recent_activity_window_start = now - timedelta(days=30)
    visible_shifu_bids = [
        str(course.shifu_bid or "").strip()
        for course in merged_courses
        if str(course.shifu_bid or "").strip()
    ]
    learning_active_30d_course_count = len(
        listing._load_recent_learning_active_course_bids(
            since=recent_activity_window_start,
            shifu_bids=visible_shifu_bids,
        )
    )
    paid_order_30d_course_count = len(
        listing._load_recent_paid_order_course_bids(
            since=recent_activity_window_start,
            shifu_bids=visible_shifu_bids,
        )
    )

    return AdminOperationCourseOverviewDTO(
        total_course_count=total_course_count,
        draft_course_count=sum(
            1
            for course in merged_courses
            if listing._resolve_course_status(course.shifu_bid or "", published_bids)
            == COURSE_STATUS_UNPUBLISHED
        ),
        published_course_count=sum(
            1
            for course in merged_courses
            if listing._resolve_course_status(course.shifu_bid or "", published_bids)
            == COURSE_STATUS_PUBLISHED
        ),
        created_last_7d_course_count=sum(
            1
            for course in merged_courses
            if course.created_at
            and created_window_start <= course.created_at <= created_window_end
        ),
        learning_active_30d_course_count=learning_active_30d_course_count,
        paid_order_30d_course_count=paid_order_30d_course_count,
    )


def _list_operator_courses_legacy(
    app: Flask,
    page_index: int,
    page_size: int,
    filters: dict | None = None,
) -> AdminOperationCourseListDTO:
    listing = _listing()
    _ = app
    safe_page_index = max(int(page_index or 1), 1)
    safe_page_size = min(max(int(page_size or 20), 1), MAX_PAGE_SIZE)
    filters = filters or {}

    shifu_bid = str(filters.get("shifu_bid", "") or "").strip()
    course_name = str(filters.get("course_name", "") or "").strip()
    course_query = str(filters.get("course_query", "") or "").strip()
    matching_course_bids = (
        listing._find_operator_course_bids_by_name(course_query)
        if course_query
        else None
    )
    course_status = str(filters.get("course_status", "") or "").strip().lower()
    quick_filter = listing._resolve_course_quick_filter(filters.get("quick_filter", ""))
    creator_keyword = str(filters.get("creator_keyword", "") or "").strip()
    start_time = filters.get("start_time")
    end_time = filters.get("end_time")
    updated_start_time = filters.get("updated_start_time")
    updated_end_time = filters.get("updated_end_time")

    creator_bids = listing._find_matching_creator_bids(creator_keyword)
    draft_rows, published_rows = _load_legacy_course_seeds(
        shifu_bid=shifu_bid,
        course_name=course_name,
        course_query=course_query,
        matching_course_bids=matching_course_bids,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
    )

    merged_courses, published_bids, selected_sources = listing._merge_courses(
        draft_rows, published_rows
    )
    activity_map = listing._load_course_activity_map(draft_rows, published_rows)

    def resolve_activity(course: object) -> dict[str, object]:
        return activity_map.get(str(course.shifu_bid or "").strip(), {})

    def resolve_updated_at(course: object) -> datetime | None:
        activity = resolve_activity(course)
        return activity.get("updated_at") or course.updated_at

    if course_status in {COURSE_STATUS_PUBLISHED, COURSE_STATUS_UNPUBLISHED}:
        merged_courses = [
            course
            for course in merged_courses
            if listing._resolve_course_status(course.shifu_bid or "", published_bids)
            == course_status
        ]
    if updated_start_time:
        merged_courses = [
            course
            for course in merged_courses
            if (resolve_updated_at(course) or NAIVE_DATETIME_MIN) >= updated_start_time
        ]
    if updated_end_time:
        merged_courses = [
            course
            for course in merged_courses
            if (resolve_updated_at(course) or NAIVE_DATETIME_MIN) <= updated_end_time
        ]
    if quick_filter:
        merged_courses = _apply_legacy_course_quick_filter(
            merged_courses, quick_filter, published_bids
        )
    merged_courses = sorted(
        merged_courses,
        key=lambda item: (
            resolve_updated_at(item) or NAIVE_DATETIME_MIN,
            item.created_at or NAIVE_DATETIME_MIN,
            item.shifu_bid or "",
        ),
        reverse=True,
    )
    total = len(merged_courses)
    page_offset = (safe_page_index - 1) * safe_page_size
    page_items = merged_courses[page_offset : page_offset + safe_page_size]
    items = _build_legacy_course_page_items(
        page_items, selected_sources, published_bids, resolve_activity
    )
    return AdminOperationCourseListDTO(
        items=items,
        page=safe_page_index,
        page_size=safe_page_size,
        total=total,
        page_count=((total + safe_page_size - 1) // safe_page_size) if total else 0,
    )


def _load_legacy_course_seeds(
    *,
    shifu_bid: str,
    course_name: str,
    course_query: str,
    matching_course_bids: set[str] | None,
    creator_bids: set[str] | None,
    start_time: datetime | None,
    end_time: datetime | None,
) -> tuple[list[OperatorCourseListSeed], list[OperatorCourseListSeed]]:
    """Load the latest draft and published course seeds for the legacy list."""
    listing = _listing()
    draft_rows = listing._load_latest_shifu_seeds(
        DraftShifu,
        shifu_bid=shifu_bid,
        course_name=course_name,
        course_query=course_query,
        matching_course_bids=matching_course_bids,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        updated_start_time=None,
        updated_end_time=None,
    )
    published_rows = listing._load_latest_shifu_seeds(
        PublishedShifu,
        shifu_bid=shifu_bid,
        course_name=course_name,
        course_query=course_query,
        matching_course_bids=matching_course_bids,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        updated_start_time=None,
        updated_end_time=None,
    )
    return draft_rows, published_rows


def _apply_legacy_course_quick_filter(
    merged_courses: list[OperatorCourseListSeed],
    quick_filter: str,
    published_bids: set[str],
) -> list[OperatorCourseListSeed]:
    """Keep the merged courses that match a non-empty quick filter."""
    listing = _listing()
    if quick_filter == COURSE_QUICK_FILTER_DRAFT:
        merged_courses = [
            course
            for course in merged_courses
            if listing._resolve_course_status(course.shifu_bid or "", published_bids)
            == COURSE_STATUS_UNPUBLISHED
        ]
    elif quick_filter == COURSE_QUICK_FILTER_PUBLISHED:
        merged_courses = [
            course
            for course in merged_courses
            if listing._resolve_course_status(course.shifu_bid or "", published_bids)
            == COURSE_STATUS_PUBLISHED
        ]
    elif quick_filter == COURSE_QUICK_FILTER_CREATED_LAST_7D:
        created_window_start, created_window_end = (
            listing._resolve_created_last_7d_window(listing.now_utc())
        )
        merged_courses = [
            course
            for course in merged_courses
            if course.created_at
            and created_window_start <= course.created_at <= created_window_end
        ]
    else:
        visible_shifu_bids = [
            str(course.shifu_bid or "").strip()
            for course in merged_courses
            if str(course.shifu_bid or "").strip()
        ]
        if quick_filter == COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D:
            matched_shifu_bids = listing._load_recent_learning_active_course_bids(
                since=listing.now_utc() - timedelta(days=30),
                shifu_bids=visible_shifu_bids,
            )
        else:
            matched_shifu_bids = listing._load_recent_paid_order_course_bids(
                since=listing.now_utc() - timedelta(days=30),
                shifu_bids=visible_shifu_bids,
            )
        merged_courses = [
            course
            for course in merged_courses
            if str(course.shifu_bid or "").strip() in matched_shifu_bids
        ]
    return merged_courses


def _build_legacy_course_page_items(
    page_items: list[OperatorCourseListSeed],
    selected_sources: dict[str, str],
    published_bids: set[str],
    resolve_activity: Callable[[object], dict[str, object]],
) -> list[AdminOperationCourseSummaryDTO]:
    """Attach prompt flags and user names, then build the page summaries."""
    listing = _listing()
    draft_page_items = [
        course
        for course in page_items
        if selected_sources.get(str(course.shifu_bid or "").strip()) == "draft"
    ]
    published_page_items = [
        course
        for course in page_items
        if selected_sources.get(str(course.shifu_bid or "").strip()) == "published"
    ]
    listing._attach_course_prompt_flags(DraftShifu, draft_page_items)
    listing._attach_course_prompt_flags(PublishedShifu, published_page_items)

    user_bids = {
        user_bid
        for course in page_items
        for user_bid in [
            course.created_user_bid,
            resolve_activity(course).get("updated_user_bid") or course.updated_user_bid,
        ]
        if user_bid and user_bid != "system"
    }
    user_map = listing._load_user_map(list(user_bids))
    return [
        listing._build_course_summary(
            course,
            user_map,
            listing._resolve_course_status(course.shifu_bid or "", published_bids),
            resolve_activity(course),
        )
        for course in page_items
    ]
