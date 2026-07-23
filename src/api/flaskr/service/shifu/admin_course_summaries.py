"""Course summary and latest-version helpers for operator admin views.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from flaskr.util.datetime import now_utc
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional, Sequence, Set
from flask import current_app
from sqlalchemy import and_, case, literal, not_
from sqlalchemy.orm import defer
from flaskr.i18n import _
from flaskr.dao import db
from flaskr.service.common.models import (
    raise_error_with_args,
    raise_param_error,
)
from flaskr.service.shifu.admin_dtos_courses import (
    AdminOperationCourseSummaryDTO,
)
from flaskr.service.shifu.consts import (
    SHIFU_NAME_MAX_LENGTH,
)
from flaskr.service.shifu.course_activity import load_course_activity_map
from flaskr.service.shifu.demo_courses import (
    is_builtin_demo_course,
    load_builtin_demo_titles,
    load_demo_shifu_bids,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.common.i18n_utils import get_markdownflow_output_language
from markdown_flow import MarkdownFlow

from flaskr.service.shifu.admin_shared import (
    COURSE_QUICK_FILTER_VALUES,
    COURSE_STATUS_PUBLISHED,
    COURSE_STATUS_UNPUBLISHED,
    _format_decimal,
)


def _format_average_score(value: Optional[Decimal]) -> str:
    if value is None:
        return ""
    return "{0:.1f}".format(value)


def _resolve_course_rating_mode(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"read", "listen"}:
        return normalized
    return ""


def _resolve_course_rating_sort_by(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "latest_desc"}:
        return "latest_desc"
    if normalized == "score_asc":
        return normalized
    return ""


@dataclass
class OperatorCourseListSeed:
    id: int
    shifu_bid: str
    title: str
    price: Any
    llm: str
    created_user_bid: str
    updated_user_bid: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    has_course_prompt: Optional[bool] = None


@dataclass
class OperatorCourseListCandidate:
    id: int
    shifu_bid: str
    title: str
    price: Any
    llm: str
    created_user_bid: str
    updated_user_bid: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    selected_source: str
    course_status: str
    activity_updated_at: Optional[datetime] = None
    activity_updated_user_bid: str = ""
    has_course_prompt: Optional[bool] = None


def _build_operator_course_list_seed(row) -> OperatorCourseListSeed:
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


def _build_operator_course_list_candidate(row) -> OperatorCourseListCandidate:
    return OperatorCourseListCandidate(
        id=int(row.id),
        shifu_bid=str(row.shifu_bid or ""),
        title=str(row.title or ""),
        price=row.price,
        llm=str(row.llm or ""),
        created_user_bid=str(row.created_user_bid or ""),
        updated_user_bid=str(row.updated_user_bid or ""),
        created_at=row.created_at,
        updated_at=row.updated_at,
        selected_source=str(row.selected_source or "").strip(),
        course_status=str(row.course_status or "").strip(),
        activity_updated_at=getattr(row, "activity_updated_at", None),
        activity_updated_user_bid=str(
            getattr(row, "activity_updated_user_bid", "") or ""
        ).strip(),
    )


def _build_operator_visible_course_filter(
    shifu_bid_column,
    title_column,
    created_user_bid_column,
):
    normalized_shifu_bid = db.func.trim(db.func.coalesce(shifu_bid_column, ""))
    normalized_title = db.func.trim(db.func.coalesce(title_column, ""))
    normalized_created_user_bid = db.func.trim(
        db.func.coalesce(created_user_bid_column, "")
    )
    conditions = [
        db.func.length(normalized_shifu_bid) > 0,
        not_(
            and_(
                normalized_created_user_bid == "system",
                normalized_title.in_(sorted(load_builtin_demo_titles())),
            )
        ),
    ]
    demo_shifu_bids = sorted(load_demo_shifu_bids())
    if demo_shifu_bids:
        conditions.append(not_(normalized_shifu_bid.in_(demo_shifu_bids)))
    return and_(*conditions)


def _build_latest_operator_course_rows_query(
    model,
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: Optional[Set[str]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
):
    latest_subquery = db.session.query(db.func.max(model.id).label("max_id")).filter(
        model.deleted == 0
    )
    if shifu_bid:
        latest_subquery = latest_subquery.filter(model.shifu_bid == shifu_bid)
    latest_subquery = latest_subquery.group_by(model.shifu_bid).subquery()

    query = db.session.query(
        model.id.label("id"),
        model.shifu_bid.label("shifu_bid"),
        model.title.label("title"),
        model.price.label("price"),
        model.llm.label("llm"),
        model.created_user_bid.label("created_user_bid"),
        model.updated_user_bid.label("updated_user_bid"),
        model.created_at.label("created_at"),
        model.updated_at.label("updated_at"),
    ).join(latest_subquery, model.id == latest_subquery.c.max_id)

    if course_name:
        query = query.filter(model.title.ilike(f"%{course_name}%"))
    if creator_bids is not None:
        if not creator_bids:
            return None
        query = query.filter(model.created_user_bid.in_(creator_bids))
    if start_time:
        query = query.filter(model.created_at >= start_time)
    if end_time:
        query = query.filter(model.created_at <= end_time)
    return query


def _build_latest_operator_course_rows_subquery(
    model,
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: Optional[Set[str]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    alias_name: str,
):
    base_query = _build_latest_operator_course_rows_query(
        model,
        shifu_bid=shifu_bid,
        course_name=course_name,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
    )
    if base_query is None:
        return None
    return base_query.cte(alias_name)


def _build_operator_course_candidate_query(
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: Optional[Set[str]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    include_activity: bool = False,
):
    draft_rows_subquery = _build_latest_operator_course_rows_subquery(
        DraftShifu,
        shifu_bid=shifu_bid,
        course_name=course_name,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        alias_name="operator_course_draft_rows",
    )
    published_rows_subquery = _build_latest_operator_course_rows_subquery(
        PublishedShifu,
        shifu_bid=shifu_bid,
        course_name=course_name,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        alias_name="operator_course_published_rows",
    )
    if draft_rows_subquery is None or published_rows_subquery is None:
        return None

    draft_visible_subquery = (
        db.session.query(draft_rows_subquery)
        .filter(
            _build_operator_visible_course_filter(
                draft_rows_subquery.c.shifu_bid,
                draft_rows_subquery.c.title,
                draft_rows_subquery.c.created_user_bid,
            )
        )
        .cte("operator_course_draft_visible")
    )
    published_visible_subquery = (
        db.session.query(published_rows_subquery)
        .filter(
            _build_operator_visible_course_filter(
                published_rows_subquery.c.shifu_bid,
                published_rows_subquery.c.title,
                published_rows_subquery.c.created_user_bid,
            )
        )
        .cte("operator_course_published_visible")
    )

    candidate_bids_subquery = (
        db.session.query(draft_visible_subquery.c.shifu_bid.label("shifu_bid"))
        .union(
            db.session.query(published_visible_subquery.c.shifu_bid.label("shifu_bid"))
        )
        .cte("operator_course_candidate_bids")
    )
    latest_activity_subquery = (
        _build_operator_course_latest_activity_subquery(
            candidate_bids_subquery,
            draft_visible_subquery,
            published_visible_subquery,
        )
        if include_activity
        else None
    )

    selected_source_expr = case(
        (draft_visible_subquery.c.id.isnot(None), literal("draft")),
        else_=literal("published"),
    )
    course_status_expr = case(
        (published_visible_subquery.c.id.isnot(None), literal(COURSE_STATUS_PUBLISHED)),
        else_=literal(COURSE_STATUS_UNPUBLISHED),
    )
    selected_columns = [
        case(
            (draft_visible_subquery.c.id.isnot(None), draft_visible_subquery.c.id),
            else_=published_visible_subquery.c.id,
        ).label("id"),
        candidate_bids_subquery.c.shifu_bid.label("shifu_bid"),
        case(
            (
                draft_visible_subquery.c.id.isnot(None),
                draft_visible_subquery.c.title,
            ),
            else_=published_visible_subquery.c.title,
        ).label("title"),
        case(
            (
                draft_visible_subquery.c.id.isnot(None),
                draft_visible_subquery.c.price,
            ),
            else_=published_visible_subquery.c.price,
        ).label("price"),
        case(
            (draft_visible_subquery.c.id.isnot(None), draft_visible_subquery.c.llm),
            else_=published_visible_subquery.c.llm,
        ).label("llm"),
        case(
            (
                draft_visible_subquery.c.id.isnot(None),
                draft_visible_subquery.c.created_user_bid,
            ),
            else_=published_visible_subquery.c.created_user_bid,
        ).label("created_user_bid"),
        case(
            (
                draft_visible_subquery.c.id.isnot(None),
                draft_visible_subquery.c.updated_user_bid,
            ),
            else_=published_visible_subquery.c.updated_user_bid,
        ).label("updated_user_bid"),
        case(
            (
                draft_visible_subquery.c.id.isnot(None),
                draft_visible_subquery.c.created_at,
            ),
            else_=published_visible_subquery.c.created_at,
        ).label("created_at"),
        case(
            (
                draft_visible_subquery.c.id.isnot(None),
                draft_visible_subquery.c.updated_at,
            ),
            else_=published_visible_subquery.c.updated_at,
        ).label("updated_at"),
        selected_source_expr.label("selected_source"),
        course_status_expr.label("course_status"),
    ]
    if latest_activity_subquery is not None:
        selected_columns.extend(
            [
                latest_activity_subquery.c.updated_at.label("activity_updated_at"),
                latest_activity_subquery.c.updated_user_bid.label(
                    "activity_updated_user_bid"
                ),
            ]
        )
    candidate_query = (
        db.session.query(*selected_columns)
        .select_from(candidate_bids_subquery)
        .outerjoin(
            draft_visible_subquery,
            draft_visible_subquery.c.shifu_bid == candidate_bids_subquery.c.shifu_bid,
        )
        .outerjoin(
            published_visible_subquery,
            published_visible_subquery.c.shifu_bid
            == candidate_bids_subquery.c.shifu_bid,
        )
    )
    if latest_activity_subquery is not None:
        candidate_query = candidate_query.outerjoin(
            latest_activity_subquery,
            latest_activity_subquery.c.shifu_bid == candidate_bids_subquery.c.shifu_bid,
        )
    return candidate_query


def _build_latest_outline_activity_subquery(
    model,
    candidate_bids_subquery,
    *,
    alias_name: str,
):
    latest_outline_rows_subquery = (
        db.session.query(
            model.shifu_bid.label("shifu_bid"),
            model.outline_item_bid.label("outline_item_bid"),
            db.func.max(model.id).label("max_id"),
        )
        .join(
            candidate_bids_subquery,
            model.shifu_bid == candidate_bids_subquery.c.shifu_bid,
        )
        .group_by(model.shifu_bid, model.outline_item_bid)
        .cte(f"{alias_name}_latest_rows")
    )
    current_outline_rows_subquery = (
        db.session.query(
            model.shifu_bid.label("shifu_bid"),
            model.updated_at.label("updated_at"),
            model.updated_user_bid.label("updated_user_bid"),
            model.id.label("id"),
        )
        .join(
            latest_outline_rows_subquery,
            model.id == latest_outline_rows_subquery.c.max_id,
        )
        .filter(model.deleted == 0)
        .cte(f"{alias_name}_current_rows")
    )
    ranked_outline_activity_subquery = db.session.query(
        current_outline_rows_subquery.c.shifu_bid.label("shifu_bid"),
        current_outline_rows_subquery.c.updated_at.label("updated_at"),
        current_outline_rows_subquery.c.updated_user_bid.label("updated_user_bid"),
        db.func.row_number()
        .over(
            partition_by=current_outline_rows_subquery.c.shifu_bid,
            order_by=[
                current_outline_rows_subquery.c.updated_at.desc(),
                current_outline_rows_subquery.c.id.desc(),
            ],
        )
        .label("row_num"),
    ).cte(f"{alias_name}_ranked")
    return (
        db.session.query(
            ranked_outline_activity_subquery.c.shifu_bid.label("shifu_bid"),
            ranked_outline_activity_subquery.c.updated_at.label("updated_at"),
            ranked_outline_activity_subquery.c.updated_user_bid.label(
                "updated_user_bid"
            ),
        )
        .filter(ranked_outline_activity_subquery.c.row_num == 1)
        .cte(alias_name)
    )


def _build_operator_course_latest_activity_subquery(
    candidate_bids_subquery,
    draft_visible_subquery,
    published_visible_subquery,
):
    draft_outline_activity_subquery = _build_latest_outline_activity_subquery(
        DraftOutlineItem,
        candidate_bids_subquery,
        alias_name="operator_course_draft_outline_activity",
    )
    published_outline_activity_subquery = _build_latest_outline_activity_subquery(
        PublishedOutlineItem,
        candidate_bids_subquery,
        alias_name="operator_course_published_outline_activity",
    )

    activity_sources_subquery = (
        db.session.query(
            draft_visible_subquery.c.shifu_bid.label("shifu_bid"),
            draft_visible_subquery.c.updated_at.label("updated_at"),
            draft_visible_subquery.c.updated_user_bid.label("updated_user_bid"),
            literal(2).label("priority"),
        )
        .union_all(
            db.session.query(
                published_visible_subquery.c.shifu_bid.label("shifu_bid"),
                published_visible_subquery.c.updated_at.label("updated_at"),
                published_visible_subquery.c.updated_user_bid.label("updated_user_bid"),
                literal(1).label("priority"),
            ),
            db.session.query(
                draft_outline_activity_subquery.c.shifu_bid.label("shifu_bid"),
                draft_outline_activity_subquery.c.updated_at.label("updated_at"),
                draft_outline_activity_subquery.c.updated_user_bid.label(
                    "updated_user_bid"
                ),
                literal(3).label("priority"),
            ),
            db.session.query(
                published_outline_activity_subquery.c.shifu_bid.label("shifu_bid"),
                published_outline_activity_subquery.c.updated_at.label("updated_at"),
                published_outline_activity_subquery.c.updated_user_bid.label(
                    "updated_user_bid"
                ),
                literal(4).label("priority"),
            ),
        )
        .cte("operator_course_activity_sources")
    )
    ranked_activity_subquery = db.session.query(
        activity_sources_subquery.c.shifu_bid.label("shifu_bid"),
        activity_sources_subquery.c.updated_at.label("updated_at"),
        activity_sources_subquery.c.updated_user_bid.label("updated_user_bid"),
        db.func.row_number()
        .over(
            partition_by=activity_sources_subquery.c.shifu_bid,
            order_by=[
                activity_sources_subquery.c.updated_at.desc(),
                activity_sources_subquery.c.priority.desc(),
            ],
        )
        .label("row_num"),
    ).cte("operator_course_ranked_activity")
    return (
        db.session.query(
            ranked_activity_subquery.c.shifu_bid.label("shifu_bid"),
            ranked_activity_subquery.c.updated_at.label("updated_at"),
            ranked_activity_subquery.c.updated_user_bid.label("updated_user_bid"),
        )
        .filter(ranked_activity_subquery.c.row_num == 1)
        .cte("operator_course_latest_activity")
    )


def _build_latest_shifus_query(
    model,
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: Optional[Set[str]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    updated_start_time: Optional[datetime],
    updated_end_time: Optional[datetime],
    lightweight: bool = False,
):
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
    model,
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: Optional[Set[str]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    updated_start_time: Optional[datetime],
    updated_end_time: Optional[datetime],
    attach_prompt_flags: bool = False,
    lightweight: bool = False,
):
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


def _load_latest_shifu_seeds(
    model,
    *,
    shifu_bid: str,
    course_name: str,
    creator_bids: Optional[Set[str]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    updated_start_time: Optional[datetime],
    updated_end_time: Optional[datetime],
) -> list[OperatorCourseListSeed]:
    ordered_query = _build_latest_shifus_query(
        model,
        shifu_bid=shifu_bid,
        course_name=course_name,
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
        model.created_user_bid.label("created_user_bid"),
        model.updated_user_bid.label("updated_user_bid"),
        model.created_at.label("created_at"),
        model.updated_at.label("updated_at"),
    ).all()
    return [_build_operator_course_list_seed(row) for row in rows]


def _attach_course_prompt_flags(model, rows) -> None:
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
        setattr(
            row,
            "has_course_prompt",
            bool(has_course_prompt_map.get(getattr(row, "id", None), False)),
        )


def _build_course_summary(
    course,
    user_map: Dict[str, Dict[str, str]],
    course_status: str,
    activity: Optional[Dict[str, Any]] = None,
) -> AdminOperationCourseSummaryDTO:
    resolved_activity = activity or {}
    creator = user_map.get(course.created_user_bid or "", {})
    llm_model = str(course.llm or "").strip()
    if not llm_model:
        llm_model = str(current_app.config.get("DEFAULT_LLM_MODEL", "") or "").strip()
    updater_user_bid = str(
        resolved_activity.get("updated_user_bid") or course.updated_user_bid or ""
    ).strip()
    updater = user_map.get(updater_user_bid, {})
    updated_at = resolved_activity.get("updated_at") or course.updated_at
    has_course_prompt = getattr(course, "has_course_prompt", None)
    if has_course_prompt is None:
        has_course_prompt = bool(
            str(getattr(course, "llm_system_prompt", "") or "").strip()
        )
    return AdminOperationCourseSummaryDTO(
        shifu_bid=course.shifu_bid or "",
        course_name=course.title or "",
        course_status=course_status,
        price=_format_decimal(course.price),
        llm_model=llm_model,
        tts_model=str(getattr(course, "tts_model", "") or "").strip(),
        has_course_prompt=bool(has_course_prompt),
        creator_user_bid=course.created_user_bid or "",
        creator_mobile=creator.get("mobile", ""),
        creator_email=creator.get("email", ""),
        creator_nickname=creator.get("nickname", ""),
        updater_user_bid=updater_user_bid,
        updater_mobile=updater.get("mobile", ""),
        updater_email=updater.get("email", ""),
        updater_nickname=updater.get("nickname", ""),
        created_at=course.created_at,
        updated_at=updated_at,
    )


def _is_operator_visible_course(course) -> bool:
    return bool(course.shifu_bid) and not is_builtin_demo_course(
        shifu_bid=course.shifu_bid,
        title=course.title,
        created_user_bid=course.created_user_bid,
    )


def _resolve_course_status(shifu_bid: str, published_bids: Set[str]) -> str:
    if shifu_bid in published_bids:
        return COURSE_STATUS_PUBLISHED
    return COURSE_STATUS_UNPUBLISHED


def _resolve_course_quick_filter(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    if normalized not in COURSE_QUICK_FILTER_VALUES:
        raise_param_error("quick_filter")
    return normalized


def _resolve_created_last_7d_window(
    now: Optional[datetime] = None,
) -> tuple[datetime, datetime]:
    current = now or now_utc()
    start = (current - timedelta(days=6)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = current.replace(hour=23, minute=59, second=59, microsecond=0)
    return start, end


def _load_course_activity_map(
    drafts: Iterable[DraftShifu],
    published: Iterable[PublishedShifu],
) -> Dict[str, Dict[str, Any]]:
    return load_course_activity_map(drafts, published)


def _load_latest_course_for_transfer(shifu_bid: str):
    draft = (
        DraftShifu.query.filter(
            DraftShifu.shifu_bid == shifu_bid,
            DraftShifu.deleted == 0,
        )
        .order_by(DraftShifu.id.desc())
        .first()
    )
    if draft:
        return draft

    return (
        PublishedShifu.query.filter(
            PublishedShifu.shifu_bid == shifu_bid,
            PublishedShifu.deleted == 0,
        )
        .order_by(PublishedShifu.id.desc())
        .first()
    )


def _load_latest_active_draft_outlines(shifu_bid: str) -> list[DraftOutlineItem]:
    latest_outline_ids = (
        db.session.query(
            DraftOutlineItem.outline_item_bid.label("outline_item_bid"),
            db.func.max(DraftOutlineItem.id).label("max_id"),
        )
        .filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
        )
        .group_by(DraftOutlineItem.outline_item_bid)
        .subquery()
    )
    return (
        db.session.query(DraftOutlineItem)
        .join(latest_outline_ids, DraftOutlineItem.id == latest_outline_ids.c.max_id)
        .filter(DraftOutlineItem.deleted == 0)
        .order_by(DraftOutlineItem.position.asc(), DraftOutlineItem.id.asc())
        .all()
    )


def _build_course_copy_title(source_title: str) -> str:
    normalized_title = str(source_title or "").strip() or _(
        "server.shifu.copyCourseTitleFallback"
    )
    suffix = _("server.shifu.copyCourseTitleSuffix")
    if len(normalized_title) + len(suffix) <= SHIFU_NAME_MAX_LENGTH:
        return f"{normalized_title}{suffix}"
    return f"{normalized_title[: SHIFU_NAME_MAX_LENGTH - len(suffix)]}{suffix}"


def _resolve_course_copy_title(source_title: str, requested_title: str) -> str:
    normalized_requested_title = str(requested_title or "").strip()
    if normalized_requested_title:
        if len(normalized_requested_title) > SHIFU_NAME_MAX_LENGTH:
            raise_error_with_args(
                "server.shifu.shifuNameTooLong",
                max_length=SHIFU_NAME_MAX_LENGTH,
            )
        return normalized_requested_title
    return _build_course_copy_title(source_title)


def _build_outline_history_tree(
    outlines: Sequence[DraftOutlineItem],
) -> list[HistoryItem]:
    outline_children_map: Dict[str, list[DraftOutlineItem]] = {}
    for outline in outlines:
        parent_bid = str(outline.parent_bid or "").strip()
        outline_children_map.setdefault(parent_bid, []).append(outline)

    def _count_blocks(content: str) -> int:
        if not content:
            return 0
        mdflow = MarkdownFlow(content).set_output_language(
            get_markdownflow_output_language()
        )
        return len(mdflow.get_all_blocks())

    def _build(parent_bid: str) -> list[HistoryItem]:
        children = outline_children_map.get(parent_bid, [])
        children.sort(key=lambda item: (item.position or "", item.id))
        history_items: list[HistoryItem] = []
        for child in children:
            history_items.append(
                HistoryItem(
                    bid=str(child.outline_item_bid or "").strip(),
                    id=int(child.id),
                    type="outline",
                    children=_build(str(child.outline_item_bid or "").strip()),
                    child_count=_count_blocks(child.content or ""),
                )
            )
        return history_items

    return _build("")


def _merge_courses(
    drafts: Iterable[DraftShifu],
    published: Iterable[PublishedShifu],
):
    course_map = {}
    published_bids: Set[str] = set()
    selected_sources: Dict[str, str] = {}
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
                item.updated_at or datetime.min,
                item.created_at or datetime.min,
                item.shifu_bid or "",
            ),
            reverse=True,
        ),
        published_bids,
        selected_sources,
    )


def _load_latest_course_versions(
    shifu_bid: str,
) -> tuple[Optional[DraftShifu], Optional[PublishedShifu]]:
    draft = (
        DraftShifu.query.filter(
            DraftShifu.shifu_bid == shifu_bid,
            DraftShifu.deleted == 0,
        )
        .order_by(DraftShifu.id.desc())
        .first()
    )
    published = (
        PublishedShifu.query.filter(
            PublishedShifu.shifu_bid == shifu_bid,
            PublishedShifu.deleted == 0,
        )
        .order_by(PublishedShifu.id.desc())
        .first()
    )
    return draft, published


def _load_latest_courses_by_shifu_bids(
    model,
    shifu_bids: Sequence[str],
    *,
    lightweight: bool = False,
):
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
