"""Operator course listing, overview, and quick-filter queries.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from flaskr.util.datetime import now_utc
from flaskr.service.common.pagination import MAX_PAGE_SIZE
from typing import Any, Dict, Iterable, Optional, Sequence, Set
from flask import Flask, current_app
from sqlalchemy import and_, case, literal, not_, or_
from sqlalchemy.orm import defer
from flaskr.dao import db
from flaskr.service.billing.models import (
    BillingOrder,
)
from flaskr.service.learn.const import (
    LEARN_STATUS_RESET,
)
from flaskr.service.learn.models import (
    LearnProgressRecord,
)
from flaskr.service.common.models import (
    raise_param_error,
)
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.shifu.admin_dtos_courses import (
    AdminOperationCourseListDTO,
    AdminOperationCourseOverviewDTO,
    AdminOperationCourseSummaryDTO,
)
from flaskr.service.shifu.admin_course_summary_mapper import (
    build_admin_operation_course_summary,
)
from flaskr.service.shifu.course_activity import load_course_activity_map
from flaskr.service.shifu.demo_courses import (
    load_builtin_demo_titles,
    load_demo_shifu_bids,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)

from flaskr.service.shifu.admin_operations.courses_shared import (
    COURSE_QUICK_FILTER_CREATED_LAST_7D,
    COURSE_QUICK_FILTER_DRAFT,
    COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D,
    COURSE_QUICK_FILTER_PUBLISHED,
    COURSE_QUICK_FILTER_VALUES,
    COURSE_STATUS_PUBLISHED,
    COURSE_STATUS_UNPUBLISHED,
    _find_matching_creator_bids,
    _load_user_map,
    _merge_courses,
)


@dataclass
class OperatorCourseListSeed:
    id: int
    shifu_bid: str
    title: str
    price: Any
    llm: str
    tts_model: str
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
    tts_model: str
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
        tts_model=str(getattr(row, "tts_model", "") or ""),
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
        tts_model=str(getattr(row, "tts_model", "") or ""),
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

    latest_nonempty_llm_subquery = (
        db.session.query(
            model.shifu_bid.label("shifu_bid"),
            model.llm.label("llm"),
            db.func.row_number()
            .over(partition_by=model.shifu_bid, order_by=model.id.desc())
            .label("row_num"),
        )
        .filter(model.deleted == 0, db.func.coalesce(model.llm, "") != "")
        .cte(f"{model.__tablename__}_latest_nonempty_llm")
    )
    latest_nonempty_tts_subquery = (
        db.session.query(
            model.shifu_bid.label("shifu_bid"),
            model.tts_model.label("tts_model"),
            db.func.row_number()
            .over(partition_by=model.shifu_bid, order_by=model.id.desc())
            .label("row_num"),
        )
        .filter(model.deleted == 0, db.func.coalesce(model.tts_model, "") != "")
        .cte(f"{model.__tablename__}_latest_nonempty_tts")
    )

    query = db.session.query(
        model.id.label("id"),
        model.shifu_bid.label("shifu_bid"),
        model.title.label("title"),
        model.price.label("price"),
        db.func.coalesce(
            db.func.nullif(model.llm, ""),
            latest_nonempty_llm_subquery.c.llm,
            "",
        ).label("llm"),
        db.func.coalesce(
            db.func.nullif(model.tts_model, ""),
            latest_nonempty_tts_subquery.c.tts_model,
            "",
        ).label("tts_model"),
        model.created_user_bid.label("created_user_bid"),
        model.updated_user_bid.label("updated_user_bid"),
        model.created_at.label("created_at"),
        model.updated_at.label("updated_at"),
    ).join(latest_subquery, model.id == latest_subquery.c.max_id)
    query = query.outerjoin(
        latest_nonempty_llm_subquery,
        and_(
            latest_nonempty_llm_subquery.c.shifu_bid == model.shifu_bid,
            latest_nonempty_llm_subquery.c.row_num == 1,
        ),
    ).outerjoin(
        latest_nonempty_tts_subquery,
        and_(
            latest_nonempty_tts_subquery.c.shifu_bid == model.shifu_bid,
            latest_nonempty_tts_subquery.c.row_num == 1,
        ),
    )

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
            (
                draft_visible_subquery.c.id.isnot(None),
                db.func.coalesce(
                    db.func.nullif(draft_visible_subquery.c.llm, ""),
                    published_visible_subquery.c.llm,
                    "",
                ),
            ),
            else_=db.func.coalesce(published_visible_subquery.c.llm, ""),
        ).label("llm"),
        case(
            (
                draft_visible_subquery.c.id.isnot(None),
                db.func.coalesce(
                    db.func.nullif(draft_visible_subquery.c.tts_model, ""),
                    published_visible_subquery.c.tts_model,
                    "",
                ),
            ),
            else_=db.func.coalesce(published_visible_subquery.c.tts_model, ""),
        ).label("tts_model"),
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


def _apply_latest_nonempty_model_fields(model, rows) -> None:
    if not rows:
        return

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
            model.llm.label("llm"),
            model.tts_model.label("tts_model"),
            db.func.row_number()
            .over(partition_by=model.shifu_bid, order_by=model.id.desc())
            .label("row_num"),
        )
        .filter(
            model.deleted == 0,
            model.shifu_bid.in_(shifu_bids),
            or_(
                db.func.coalesce(model.llm, "") != "",
                db.func.coalesce(model.tts_model, "") != "",
            ),
        )
        .subquery()
    )
    fallback_rows = (
        db.session.query(
            latest_nonempty_rows.c.shifu_bid,
            latest_nonempty_rows.c.llm,
            latest_nonempty_rows.c.tts_model,
        )
        .filter(latest_nonempty_rows.c.row_num == 1)
        .all()
    )
    fallback_map = {
        str(row.shifu_bid or ""): {
            "llm": str(getattr(row, "llm", "") or ""),
            "tts_model": str(getattr(row, "tts_model", "") or ""),
        }
        for row in fallback_rows
    }
    for row in rows:
        fallback = fallback_map.get(str(getattr(row, "shifu_bid", "") or ""))
        if not fallback:
            continue
        if not str(getattr(row, "llm", "") or "").strip():
            setattr(row, "llm", fallback["llm"])
        if not str(getattr(row, "tts_model", "") or "").strip():
            setattr(row, "tts_model", fallback["tts_model"])


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
            model.tts_model.label("tts_model"),
            model.created_user_bid.label("created_user_bid"),
            model.updated_user_bid.label("updated_user_bid"),
            model.created_at.label("created_at"),
            model.updated_at.label("updated_at"),
        ).all()
        _apply_latest_nonempty_model_fields(model, rows)
        return [_build_operator_course_list_seed(row) for row in rows]

    rows = ordered_query.all()
    if hasattr(model, "__mapper__"):
        _apply_latest_nonempty_model_fields(model, rows)
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
        model.tts_model.label("tts_model"),
        model.created_user_bid.label("created_user_bid"),
        model.updated_user_bid.label("updated_user_bid"),
        model.created_at.label("created_at"),
        model.updated_at.label("updated_at"),
    ).all()
    _apply_latest_nonempty_model_fields(model, rows)
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
    return build_admin_operation_course_summary(
        course,
        user_map=user_map,
        course_status=course_status,
        activity=activity,
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


def _apply_operator_course_list_filters(
    query,
    candidate_subquery,
    *,
    course_status: str,
    quick_filter: str,
    updated_start_time: Optional[datetime],
    updated_end_time: Optional[datetime],
    apply_updated_filters: bool,
):
    if course_status in {COURSE_STATUS_PUBLISHED, COURSE_STATUS_UNPUBLISHED}:
        query = query.filter(candidate_subquery.c.course_status == course_status)
    if quick_filter:
        if quick_filter == COURSE_QUICK_FILTER_DRAFT:
            query = query.filter(
                candidate_subquery.c.course_status == COURSE_STATUS_UNPUBLISHED
            )
        elif quick_filter == COURSE_QUICK_FILTER_PUBLISHED:
            query = query.filter(
                candidate_subquery.c.course_status == COURSE_STATUS_PUBLISHED
            )
        elif quick_filter == COURSE_QUICK_FILTER_CREATED_LAST_7D:
            created_window_start, created_window_end = _resolve_created_last_7d_window(
                now_utc()
            )
            query = query.filter(
                candidate_subquery.c.created_at >= created_window_start,
                candidate_subquery.c.created_at <= created_window_end,
            )
        else:
            if quick_filter == COURSE_QUICK_FILTER_LEARNING_ACTIVE_30D:
                matched_course_query = db.session.query(
                    LearnProgressRecord.shifu_bid
                ).filter(
                    LearnProgressRecord.deleted == 0,
                    LearnProgressRecord.status != LEARN_STATUS_RESET,
                    LearnProgressRecord.created_at >= now_utc() - timedelta(days=30),
                )
            else:
                matched_course_query = db.session.query(Order.shifu_bid).filter(
                    Order.deleted == 0,
                    Order.status == ORDER_STATUS_SUCCESS,
                    Order.created_at >= now_utc() - timedelta(days=30),
                )
            query = query.filter(
                candidate_subquery.c.shifu_bid.in_(matched_course_query)
            )

    if apply_updated_filters:
        if updated_start_time:
            query = query.filter(
                candidate_subquery.c.activity_updated_at >= updated_start_time
            )
        if updated_end_time:
            query = query.filter(
                or_(
                    candidate_subquery.c.activity_updated_at.is_(None),
                    candidate_subquery.c.activity_updated_at <= updated_end_time,
                )
            )
    return query


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


def _load_recent_learning_active_course_bids(
    *,
    since: datetime,
    shifu_bids: Optional[Sequence[str]] = None,
) -> Set[str]:
    query = db.session.query(LearnProgressRecord.shifu_bid).filter(
        LearnProgressRecord.deleted == 0,
        LearnProgressRecord.status != LEARN_STATUS_RESET,
        LearnProgressRecord.created_at >= since,
    )
    if shifu_bids is not None:
        normalized_shifu_bids = [
            str(shifu_bid or "").strip() for shifu_bid in shifu_bids if shifu_bid
        ]
        if not normalized_shifu_bids:
            return set()
        query = query.filter(LearnProgressRecord.shifu_bid.in_(normalized_shifu_bids))
    rows = query.distinct().all()
    return {
        str(shifu_bid or "").strip()
        for (shifu_bid,) in rows
        if str(shifu_bid or "").strip()
    }


def _load_recent_paid_order_course_bids(
    *,
    since: datetime,
    shifu_bids: Optional[Sequence[str]] = None,
) -> Set[str]:
    query = db.session.query(Order.shifu_bid).filter(
        Order.deleted == 0,
        Order.status == ORDER_STATUS_SUCCESS,
        Order.created_at >= since,
    )
    if shifu_bids is not None:
        normalized_shifu_bids = [
            str(shifu_bid or "").strip() for shifu_bid in shifu_bids if shifu_bid
        ]
        if not normalized_shifu_bids:
            return set()
        query = query.filter(Order.shifu_bid.in_(normalized_shifu_bids))
    rows = query.distinct().all()
    return {
        str(shifu_bid or "").strip()
        for (shifu_bid,) in rows
        if str(shifu_bid or "").strip()
    }


def _build_latest_billing_order_subquery(*, creator_bid: str):
    normalized_creator_bid = str(creator_bid or "").strip()
    return (
        db.session.query(
            BillingOrder.bill_order_bid.label("bill_order_bid"),
            db.func.max(BillingOrder.id).label("max_id"),
        )
        .filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == normalized_creator_bid,
        )
        .group_by(BillingOrder.bill_order_bid)
        .subquery()
    )


def _find_operator_course_bids_by_name(course_name: str) -> Set[str]:
    normalized_course_name = str(course_name or "").strip().lower()
    if not normalized_course_name:
        return set()

    def _load_matching_bids(model) -> Set[str]:
        latest_subquery = (
            db.session.query(db.func.max(model.id).label("max_id"))
            .filter(model.deleted == 0)
            .group_by(model.shifu_bid)
            .subquery()
        )
        rows = (
            db.session.query(model.shifu_bid)
            .join(latest_subquery, latest_subquery.c.max_id == model.id)
            .filter(model.title.ilike(f"%{normalized_course_name}%"))
            .all()
        )
        return {
            str(shifu_bid or "").strip()
            for (shifu_bid,) in rows
            if str(shifu_bid or "").strip()
        }

    matching_bids: Set[str] = set()
    matching_bids.update(_load_matching_bids(DraftShifu))
    matching_bids.update(_load_matching_bids(PublishedShifu))
    return matching_bids


def _build_operator_course_query_filter(
    shifu_bid_column: Any,
    course_query: str,
) -> Any | None:
    normalized_course_query = str(course_query or "").strip()
    if not normalized_course_query:
        return None

    course_filters = [shifu_bid_column == normalized_course_query]
    matching_course_bids = _find_operator_course_bids_by_name(normalized_course_query)
    if matching_course_bids:
        course_filters.append(shifu_bid_column.in_(sorted(matching_course_bids)))
    return or_(*course_filters)


def _build_operator_course_overview(app: Flask) -> AdminOperationCourseOverviewDTO:
    if not _can_use_operator_course_sql_optimization(app):
        return _build_operator_course_overview_legacy(app)

    candidate_query = _build_operator_course_candidate_query(
        shifu_bid="",
        course_name="",
        creator_bids=None,
        start_time=None,
        end_time=None,
    )
    if candidate_query is None:
        return AdminOperationCourseOverviewDTO()
    candidate_subquery = candidate_query.subquery("operator_course_overview_candidates")
    now = now_utc()
    created_window_start, created_window_end = _resolve_created_last_7d_window(now)
    recent_activity_window_start = now - timedelta(days=30)
    aggregate_row = db.session.query(
        db.func.count(candidate_subquery.c.shifu_bid).label("total_course_count"),
        db.func.sum(
            case(
                (candidate_subquery.c.course_status == COURSE_STATUS_UNPUBLISHED, 1),
                else_=0,
            )
        ).label("draft_course_count"),
        db.func.sum(
            case(
                (candidate_subquery.c.course_status == COURSE_STATUS_PUBLISHED, 1),
                else_=0,
            )
        ).label("published_course_count"),
        db.func.sum(
            case(
                (
                    and_(
                        candidate_subquery.c.created_at >= created_window_start,
                        candidate_subquery.c.created_at <= created_window_end,
                    ),
                    1,
                ),
                else_=0,
            )
        ).label("created_last_7d_course_count"),
    ).one()
    total_course_count = int(aggregate_row.total_course_count or 0)
    if total_course_count == 0:
        return AdminOperationCourseOverviewDTO()
    learning_active_30d_course_count = (
        db.session.query(db.func.count(db.distinct(candidate_subquery.c.shifu_bid)))
        .select_from(candidate_subquery)
        .join(
            LearnProgressRecord,
            and_(
                LearnProgressRecord.shifu_bid == candidate_subquery.c.shifu_bid,
                LearnProgressRecord.deleted == 0,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
                LearnProgressRecord.created_at >= recent_activity_window_start,
            ),
        )
        .scalar()
        or 0
    )
    paid_order_30d_course_count = (
        db.session.query(db.func.count(db.distinct(candidate_subquery.c.shifu_bid)))
        .select_from(candidate_subquery)
        .join(
            Order,
            and_(
                Order.shifu_bid == candidate_subquery.c.shifu_bid,
                Order.deleted == 0,
                Order.status == ORDER_STATUS_SUCCESS,
                Order.created_at >= recent_activity_window_start,
            ),
        )
        .scalar()
        or 0
    )

    return AdminOperationCourseOverviewDTO(
        total_course_count=total_course_count,
        draft_course_count=int(aggregate_row.draft_course_count or 0),
        published_course_count=int(aggregate_row.published_course_count or 0),
        created_last_7d_course_count=int(
            aggregate_row.created_last_7d_course_count or 0
        ),
        learning_active_30d_course_count=int(learning_active_30d_course_count or 0),
        paid_order_30d_course_count=int(paid_order_30d_course_count or 0),
    )


def get_operator_course_overview(app: Flask) -> AdminOperationCourseOverviewDTO:
    with app.app_context():
        return _build_operator_course_overview(app)


def _can_use_operator_course_sql_optimization(app: Flask) -> bool:
    try:
        return current_app._get_current_object() is app and db.engine is not None
    except (RuntimeError, KeyError):
        return False


def _build_operator_course_overview_legacy(
    app: Flask,
) -> AdminOperationCourseOverviewDTO:
    draft_rows = _load_latest_shifus(
        DraftShifu,
        shifu_bid="",
        course_name="",
        creator_bids=None,
        start_time=None,
        end_time=None,
        updated_start_time=None,
        updated_end_time=None,
    )
    published_rows = _load_latest_shifus(
        PublishedShifu,
        shifu_bid="",
        course_name="",
        creator_bids=None,
        start_time=None,
        end_time=None,
        updated_start_time=None,
        updated_end_time=None,
    )
    merged_courses, published_bids, _ = _merge_courses(draft_rows, published_rows)
    total_course_count = len(merged_courses)
    if total_course_count == 0:
        return AdminOperationCourseOverviewDTO()

    now = now_utc()
    created_window_start, created_window_end = _resolve_created_last_7d_window(now)
    recent_activity_window_start = now - timedelta(days=30)
    visible_shifu_bids = [
        str(course.shifu_bid or "").strip()
        for course in merged_courses
        if str(course.shifu_bid or "").strip()
    ]
    learning_active_30d_course_count = len(
        _load_recent_learning_active_course_bids(
            since=recent_activity_window_start,
            shifu_bids=visible_shifu_bids,
        )
    )
    paid_order_30d_course_count = len(
        _load_recent_paid_order_course_bids(
            since=recent_activity_window_start,
            shifu_bids=visible_shifu_bids,
        )
    )

    return AdminOperationCourseOverviewDTO(
        total_course_count=total_course_count,
        draft_course_count=sum(
            1
            for course in merged_courses
            if _resolve_course_status(course.shifu_bid or "", published_bids)
            == COURSE_STATUS_UNPUBLISHED
        ),
        published_course_count=sum(
            1
            for course in merged_courses
            if _resolve_course_status(course.shifu_bid or "", published_bids)
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
    filters: Optional[dict] = None,
) -> AdminOperationCourseListDTO:
    safe_page_index = max(int(page_index or 1), 1)
    safe_page_size = min(max(int(page_size or 20), 1), MAX_PAGE_SIZE)
    filters = filters or {}

    shifu_bid = str(filters.get("shifu_bid", "") or "").strip()
    course_name = str(filters.get("course_name", "") or "").strip()
    course_status = str(filters.get("course_status", "") or "").strip().lower()
    quick_filter = _resolve_course_quick_filter(filters.get("quick_filter", ""))
    creator_keyword = str(filters.get("creator_keyword", "") or "").strip()
    start_time = filters.get("start_time")
    end_time = filters.get("end_time")
    updated_start_time = filters.get("updated_start_time")
    updated_end_time = filters.get("updated_end_time")

    creator_bids = _find_matching_creator_bids(creator_keyword)
    draft_rows = _load_latest_shifu_seeds(
        DraftShifu,
        shifu_bid=shifu_bid,
        course_name=course_name,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        updated_start_time=None,
        updated_end_time=None,
    )
    published_rows = _load_latest_shifu_seeds(
        PublishedShifu,
        shifu_bid=shifu_bid,
        course_name=course_name,
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        updated_start_time=None,
        updated_end_time=None,
    )

    merged_courses, published_bids, selected_sources = _merge_courses(
        draft_rows, published_rows
    )
    activity_map = _load_course_activity_map(draft_rows, published_rows)

    def resolve_activity(course) -> Dict[str, Any]:
        return activity_map.get(str(course.shifu_bid or "").strip(), {})

    def resolve_updated_at(course) -> Optional[datetime]:
        activity = resolve_activity(course)
        return activity.get("updated_at") or course.updated_at

    if course_status in {COURSE_STATUS_PUBLISHED, COURSE_STATUS_UNPUBLISHED}:
        merged_courses = [
            course
            for course in merged_courses
            if _resolve_course_status(course.shifu_bid or "", published_bids)
            == course_status
        ]
    if updated_start_time:
        merged_courses = [
            course
            for course in merged_courses
            if (resolve_updated_at(course) or datetime.min) >= updated_start_time
        ]
    if updated_end_time:
        merged_courses = [
            course
            for course in merged_courses
            if (resolve_updated_at(course) or datetime.min) <= updated_end_time
        ]
    if quick_filter:
        if quick_filter == COURSE_QUICK_FILTER_DRAFT:
            merged_courses = [
                course
                for course in merged_courses
                if _resolve_course_status(course.shifu_bid or "", published_bids)
                == COURSE_STATUS_UNPUBLISHED
            ]
        elif quick_filter == COURSE_QUICK_FILTER_PUBLISHED:
            merged_courses = [
                course
                for course in merged_courses
                if _resolve_course_status(course.shifu_bid or "", published_bids)
                == COURSE_STATUS_PUBLISHED
            ]
        elif quick_filter == COURSE_QUICK_FILTER_CREATED_LAST_7D:
            created_window_start, created_window_end = _resolve_created_last_7d_window(
                now_utc()
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
                matched_shifu_bids = _load_recent_learning_active_course_bids(
                    since=now_utc() - timedelta(days=30),
                    shifu_bids=visible_shifu_bids,
                )
            else:
                matched_shifu_bids = _load_recent_paid_order_course_bids(
                    since=now_utc() - timedelta(days=30),
                    shifu_bids=visible_shifu_bids,
                )
            merged_courses = [
                course
                for course in merged_courses
                if str(course.shifu_bid or "").strip() in matched_shifu_bids
            ]
    merged_courses = sorted(
        merged_courses,
        key=lambda item: (
            resolve_updated_at(item) or datetime.min,
            item.created_at or datetime.min,
            item.shifu_bid or "",
        ),
        reverse=True,
    )
    total = len(merged_courses)
    page_offset = (safe_page_index - 1) * safe_page_size
    page_items = merged_courses[page_offset : page_offset + safe_page_size]
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
    _attach_course_prompt_flags(DraftShifu, draft_page_items)
    _attach_course_prompt_flags(PublishedShifu, published_page_items)

    user_bids = {
        user_bid
        for course in page_items
        for user_bid in [
            course.created_user_bid,
            resolve_activity(course).get("updated_user_bid") or course.updated_user_bid,
        ]
        if user_bid and user_bid != "system"
    }
    user_map = _load_user_map(list(user_bids))
    items = [
        _build_course_summary(
            course,
            user_map,
            _resolve_course_status(course.shifu_bid or "", published_bids),
            resolve_activity(course),
        )
        for course in page_items
    ]
    return AdminOperationCourseListDTO(
        items=items,
        page=safe_page_index,
        page_size=safe_page_size,
        total=total,
        page_count=((total + safe_page_size - 1) // safe_page_size) if total else 0,
    )


def list_operator_courses(
    app: Flask,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
) -> AdminOperationCourseListDTO:
    with app.app_context():
        if not _can_use_operator_course_sql_optimization(app):
            return _list_operator_courses_legacy(app, page_index, page_size, filters)

        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(max(int(page_size or 20), 1), MAX_PAGE_SIZE)
        filters = filters or {}

        shifu_bid = str(filters.get("shifu_bid", "") or "").strip()
        course_name = str(filters.get("course_name", "") or "").strip()
        course_status = str(filters.get("course_status", "") or "").strip().lower()
        quick_filter = _resolve_course_quick_filter(filters.get("quick_filter", ""))
        creator_keyword = str(filters.get("creator_keyword", "") or "").strip()
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")
        updated_start_time = filters.get("updated_start_time")
        updated_end_time = filters.get("updated_end_time")

        creator_bids = _find_matching_creator_bids(creator_keyword)
        needs_activity_filters = bool(updated_start_time or updated_end_time)
        count_candidate_query = _build_operator_course_candidate_query(
            shifu_bid=shifu_bid,
            course_name=course_name,
            creator_bids=creator_bids,
            start_time=start_time,
            end_time=end_time,
            include_activity=needs_activity_filters,
        )
        if count_candidate_query is None:
            return AdminOperationCourseListDTO(
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )
        count_candidate_subquery = count_candidate_query.subquery(
            "operator_course_count_candidates"
        )
        count_query = _apply_operator_course_list_filters(
            db.session.query(count_candidate_subquery),
            count_candidate_subquery,
            course_status=course_status,
            quick_filter=quick_filter,
            updated_start_time=updated_start_time,
            updated_end_time=updated_end_time,
            apply_updated_filters=needs_activity_filters,
        )
        total = int(count_query.count() or 0)

        page_candidate_query = _build_operator_course_candidate_query(
            shifu_bid=shifu_bid,
            course_name=course_name,
            creator_bids=creator_bids,
            start_time=start_time,
            end_time=end_time,
            include_activity=True,
        )
        if page_candidate_query is None:
            return AdminOperationCourseListDTO(
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )
        candidate_subquery = page_candidate_query.subquery("operator_course_candidates")
        query = _apply_operator_course_list_filters(
            db.session.query(candidate_subquery),
            candidate_subquery,
            course_status=course_status,
            quick_filter=quick_filter,
            updated_start_time=updated_start_time,
            updated_end_time=updated_end_time,
            apply_updated_filters=True,
        )

        page_offset = (safe_page_index - 1) * safe_page_size
        page_rows = (
            query.order_by(
                candidate_subquery.c.activity_updated_at.desc(),
                candidate_subquery.c.created_at.desc(),
                candidate_subquery.c.shifu_bid.desc(),
            )
            .offset(page_offset)
            .limit(safe_page_size)
            .all()
        )
        page_items = [_build_operator_course_list_candidate(row) for row in page_rows]

        draft_page_items = [
            course for course in page_items if course.selected_source == "draft"
        ]
        published_page_items = [
            course for course in page_items if course.selected_source == "published"
        ]
        _attach_course_prompt_flags(DraftShifu, draft_page_items)
        _attach_course_prompt_flags(PublishedShifu, published_page_items)

        def resolve_activity(course) -> Dict[str, Any]:
            return {
                "updated_at": course.activity_updated_at or course.updated_at,
                "updated_user_bid": course.activity_updated_user_bid
                or course.updated_user_bid,
            }

        user_bids = {
            user_bid
            for course in page_items
            for user_bid in [
                course.created_user_bid,
                resolve_activity(course).get("updated_user_bid")
                or course.activity_updated_user_bid
                or course.updated_user_bid,
            ]
            if user_bid and user_bid != "system"
        }
        user_map = _load_user_map(list(user_bids))
        items = [
            _build_course_summary(
                course,
                user_map,
                course.course_status,
                resolve_activity(course),
            )
            for course in page_items
        ]
        return AdminOperationCourseListDTO(
            items=items,
            page=safe_page_index,
            page_size=safe_page_size,
            total=total,
            page_count=((total + safe_page_size - 1) // safe_page_size) if total else 0,
        )
