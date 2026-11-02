"""Course summary and latest-version helpers for operator admin views.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flaskr.dao import db
from flaskr.service.shifu.admin_shared import (
    COURSE_STATUS_PUBLISHED,
    COURSE_STATUS_UNPUBLISHED,
)
from flaskr.service.shifu.demo_courses import (
    is_builtin_demo_course,
)
from flaskr.util.datetime import NAIVE_DATETIME_MIN
from sqlalchemy import case
from sqlalchemy.orm import defer

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import datetime

    from flask_sqlalchemy.query import Query
    from flaskr.service.shifu.models import DraftShifu, PublishedShifu


@dataclass
class OperatorCourseListSeed:
    """Carry seed data for operator course list."""

    id: int
    shifu_bid: str
    title: str
    price: Any
    llm: str
    created_user_bid: str
    updated_user_bid: str
    created_at: datetime | None
    updated_at: datetime | None
    has_course_prompt: bool | None = None


def _build_operator_course_list_seed(row: object) -> OperatorCourseListSeed:
    return OperatorCourseListSeed(
        id=int(row.id),
        shifu_bid=str(row.shifu_bid or ""),
        title=str(row.title or ""),
        price=row.price,
        llm=str(row.llm or ""),
        created_user_bid=str(row.created_user_bid or ""),
        updated_user_bid=str(row.updated_user_bid or ""),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _build_latest_shifus_query(
    model: object,
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: set[str] | None,
    start_time: datetime | None,
    end_time: datetime | None,
    updated_start_time: datetime | None,
    updated_end_time: datetime | None,
    lightweight: bool = False,
) -> Query | list[DraftShifu | PublishedShifu]:
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


def _load_latest_shifus(
    model: object,
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: set[str] | None,
    start_time: datetime | None,
    end_time: datetime | None,
    updated_start_time: datetime | None,
    updated_end_time: datetime | None,
    attach_prompt_flags: bool = False,
    lightweight: bool = False,
) -> list[DraftShifu | PublishedShifu | OperatorCourseListSeed]:
    ordered_query = _build_latest_shifus_query(
        model,
        shifu_bid=shifu_bid,
        course_name=course_name,
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
            model.created_user_bid.label("created_user_bid"),
            model.updated_user_bid.label("updated_user_bid"),
            model.created_at.label("created_at"),
            model.updated_at.label("updated_at"),
        ).all()
        return [_build_operator_course_list_seed(row) for row in rows]

    rows = ordered_query.all()
    if hasattr(model, "__mapper__") and attach_prompt_flags:
        _attach_course_prompt_flags(model, rows)
    return rows


def _attach_course_prompt_flags(model: object, rows: object) -> None:
    course_ids = [getattr(row, "id", None) for row in rows if getattr(row, "id", None)]
    if not course_ids:
        return

    has_course_prompt_rows = (
        db.session.query(
            model.id,
            case(
                (
                    db.func.length(
                        db.func.trim(db.func.coalesce(model.llm_system_prompt, ""))
                    )
                    > 0,
                    True,
                ),
                else_=False,
            ).label("has_course_prompt"),
        )
        .filter(model.id.in_(course_ids))
        .all()
    )
    has_course_prompt_map = {
        row_id: bool(has_course_prompt)
        for row_id, has_course_prompt in has_course_prompt_rows
    }
    for row in rows:
        row.has_course_prompt = bool(
            has_course_prompt_map.get(getattr(row, "id", None), False)
        )


def _is_operator_visible_course(course: object) -> bool:
    return bool(course.shifu_bid) and not is_builtin_demo_course(
        shifu_bid=course.shifu_bid,
        title=course.title,
        created_user_bid=course.created_user_bid,
    )


def _resolve_course_status(shifu_bid: str, published_bids: set[str]) -> str:
    if shifu_bid in published_bids:
        return COURSE_STATUS_PUBLISHED
    return COURSE_STATUS_UNPUBLISHED


def _merge_courses(
    drafts: Iterable[DraftShifu | PublishedShifu | OperatorCourseListSeed],
    published: Iterable[DraftShifu | PublishedShifu | OperatorCourseListSeed],
) -> tuple[
    list[DraftShifu | PublishedShifu | OperatorCourseListSeed],
    set[str],
    dict[str, str],
]:
    course_map = {}
    published_bids: set[str] = set()
    selected_sources: dict[str, str] = {}
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
                item.updated_at or NAIVE_DATETIME_MIN,
                item.created_at or NAIVE_DATETIME_MIN,
                item.shifu_bid or "",
            ),
            reverse=True,
        ),
        published_bids,
        selected_sources,
    )


def _load_latest_courses_by_shifu_bids(
    model: type[DraftShifu | PublishedShifu],
    shifu_bids: Sequence[str],
    *,
    lightweight: bool = False,
) -> list[DraftShifu | PublishedShifu | OperatorCourseListSeed]:
    normalized_shifu_bids = [
        str(shifu_bid or "").strip() for shifu_bid in shifu_bids if shifu_bid
    ]
    if not normalized_shifu_bids:
        return []

    latest_subquery = (
        db.session.query(db.func.max(model.id).label("max_id"))
        .filter(
            model.deleted == 0,
            model.shifu_bid.in_(normalized_shifu_bids),
        )
        .group_by(model.shifu_bid)
        .subquery()
    )
    query = db.session.query(model).filter(
        model.id.in_(db.session.query(latest_subquery.c.max_id))
    )
    if lightweight and hasattr(model, "__mapper__"):
        rows = query.with_entities(
            model.id.label("id"),
            model.shifu_bid.label("shifu_bid"),
            model.title.label("title"),
            model.price.label("price"),
            model.llm.label("llm"),
            model.created_user_bid.label("created_user_bid"),
            model.updated_user_bid.label("updated_user_bid"),
            model.created_at.label("created_at"),
            model.updated_at.label("updated_at"),
        ).all()
        return [_build_operator_course_list_seed(row) for row in rows]
    return query.all()
