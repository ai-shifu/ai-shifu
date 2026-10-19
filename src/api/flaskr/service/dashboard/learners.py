"""Build the paginated learner table for the dashboard course detail."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.dashboard.common import (
    DASHBOARD_COURSE_LEARNER_PAGE_SIZE_MAX,
    _build_dashboard_learner_keyword_filter,
    _parse_dashboard_date_boundary,
    _validate_dashboard_date_range,
)
from flaskr.service.dashboard.dtos import (
    DashboardCourseDetailLearnerItemDTO,
    DashboardCourseDetailLearnersDTO,
)
from flaskr.service.dashboard.loaders import (
    _load_dashboard_course_user_contact_map,
)
from flaskr.service.learn.const import ROLE_STUDENT
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnProgressRecord,
)
from flaskr.service.order.consts import (
    LEARN_STATUS_RESET,
    ORDER_STATUS_SUCCESS,
)
from flaskr.service.order.models import Order
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDASK_VALUE,
)
from flaskr.service.shifu.models import (
    AiCourseAuth,
)
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.util.timezone import _coerce_datetime
from sqlalchemy import and_, case

if TYPE_CHECKING:
    from collections.abc import Sequence

    from flask import Flask
    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.sql.selectable import Subquery


def _build_learner_source_subquery(
    normalized_shifu_bid: str,
    normalized_learner_bids: list[str],
) -> Subquery:
    """Union learners with progress or a successful manual import order."""
    return (
        db.session.query(
            LearnProgressRecord.user_bid.label("user_bid"),
        )
        .filter(
            LearnProgressRecord.shifu_bid == normalized_shifu_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.user_bid.in_(normalized_learner_bids),
        )
        .distinct()
        .union(
            db.session.query(
                Order.user_bid.label("user_bid"),
            )
            .filter(
                Order.shifu_bid == normalized_shifu_bid,
                Order.deleted == 0,
                Order.payment_channel == "manual",
                Order.status == ORDER_STATUS_SUCCESS,
                Order.user_bid.in_(normalized_learner_bids),
            )
            .distinct()
        )
        .subquery()
    )


def _build_learner_joined_at_subquery(
    normalized_shifu_bid: str,
    normalized_learner_bids: list[str],
    learner_source: Subquery,
) -> Subquery:
    """Collect order, course-auth, and progress join times for each learner."""
    order_joined_at_subquery = (
        db.session.query(
            Order.user_bid.label("user_bid"),
            db.func.min(Order.created_at).label("joined_at"),
        )
        .filter(
            Order.shifu_bid == normalized_shifu_bid,
            Order.deleted == 0,
            Order.status == ORDER_STATUS_SUCCESS,
            Order.user_bid.in_(normalized_learner_bids),
        )
        .group_by(Order.user_bid)
        .subquery()
    )
    auth_joined_at_subquery = (
        db.session.query(
            AiCourseAuth.user_id.label("user_bid"),
            db.func.min(
                db.func.coalesce(AiCourseAuth.updated_at, AiCourseAuth.created_at)
            ).label("joined_at"),
        )
        .filter(
            AiCourseAuth.course_id == normalized_shifu_bid,
            AiCourseAuth.user_id.in_(normalized_learner_bids),
            AiCourseAuth.status == 1,
        )
        .group_by(AiCourseAuth.user_id)
        .subquery()
    )
    progress_joined_at_subquery = (
        db.session.query(
            LearnProgressRecord.user_bid.label("user_bid"),
            db.func.min(LearnProgressRecord.created_at).label("joined_at"),
        )
        .filter(
            LearnProgressRecord.shifu_bid == normalized_shifu_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.user_bid.in_(normalized_learner_bids),
        )
        .group_by(LearnProgressRecord.user_bid)
        .subquery()
    )
    return (
        db.session.query(
            learner_source.c.user_bid.label("user_bid"),
            order_joined_at_subquery.c.joined_at.label("order_joined_at"),
            auth_joined_at_subquery.c.joined_at.label("auth_joined_at"),
            progress_joined_at_subquery.c.joined_at.label("progress_joined_at"),
        )
        .select_from(learner_source)
        .outerjoin(
            order_joined_at_subquery,
            order_joined_at_subquery.c.user_bid == learner_source.c.user_bid,
        )
        .outerjoin(
            auth_joined_at_subquery,
            auth_joined_at_subquery.c.user_bid == learner_source.c.user_bid,
        )
        .outerjoin(
            progress_joined_at_subquery,
            progress_joined_at_subquery.c.user_bid == learner_source.c.user_bid,
        )
        .subquery()
    )


def _build_learning_status_expression(
    learned_lesson_count_expression: ColumnElement[int],
    total_lesson_count: int,
) -> ColumnElement[str]:
    if total_lesson_count > 0:
        learning_status_expression = case(
            (learned_lesson_count_expression >= total_lesson_count, "completed"),
            (learned_lesson_count_expression > 0, "learning"),
            else_="not_started",
        )
    else:
        learning_status_expression = case(
            (learned_lesson_count_expression > 0, "learning"),
            else_="not_started",
        )
    return learning_status_expression


def _build_learner_joined_at_expression(
    joined_at_subquery: Subquery,
) -> ColumnElement[datetime]:
    """Pick the earliest known join time, or NULL when none is recorded."""
    joined_at_missing_filter = and_(
        joined_at_subquery.c.order_joined_at.is_(None),
        joined_at_subquery.c.auth_joined_at.is_(None),
        joined_at_subquery.c.progress_joined_at.is_(None),
    )
    joined_at_sentinel = datetime(9999, 12, 31, 23, 59, 59)
    order_joined_at_expression = db.func.coalesce(
        joined_at_subquery.c.order_joined_at,
        joined_at_sentinel,
    )
    auth_joined_at_expression = db.func.coalesce(
        joined_at_subquery.c.auth_joined_at,
        joined_at_sentinel,
    )
    progress_joined_at_expression = db.func.coalesce(
        joined_at_subquery.c.progress_joined_at,
        joined_at_sentinel,
    )
    earliest_order_or_auth_expression = case(
        (
            order_joined_at_expression <= auth_joined_at_expression,
            order_joined_at_expression,
        ),
        else_=auth_joined_at_expression,
    )
    return case(
        (joined_at_missing_filter, None),
        (
            earliest_order_or_auth_expression <= progress_joined_at_expression,
            earliest_order_or_auth_expression,
        ),
        else_=progress_joined_at_expression,
    )


def _build_learner_items(
    app: Flask,
    page_rows: Sequence[object],
    contact_map: dict[str, dict[str, str]],
    total_lesson_count: int,
) -> list[DashboardCourseDetailLearnerItemDTO]:
    paged_items = []
    for row in page_rows:
        user_bid = str(getattr(row, "user_bid", "") or "").strip()
        contact = contact_map.get(user_bid, {"mobile": "", "email": ""})
        last_learning_at = _coerce_datetime(
            app,
            getattr(row, "last_learning_at", None),
        )
        joined_at = _coerce_datetime(app, getattr(row, "joined_at", None))
        paged_items.append(
            DashboardCourseDetailLearnerItemDTO(
                user_bid=user_bid,
                mobile=str(contact.get("mobile", "") or "").strip(),
                email=str(contact.get("email", "") or "").strip(),
                nickname=str(getattr(row, "nickname", "") or "").strip(),
                learned_lesson_count=int(getattr(row, "learned_lesson_count", 0) or 0),
                total_lesson_count=total_lesson_count,
                learning_status=str(getattr(row, "learning_status", "") or ""),
                follow_up_count=int(getattr(row, "follow_up_count", 0) or 0),
                last_learning_at=last_learning_at,
                joined_at=joined_at,
            )
        )
    return paged_items


def _build_learner_activity_subqueries(
    normalized_shifu_bid: str,
    normalized_learner_bids: list[str],
    normalized_leaf_outline_bids: list[str],
) -> tuple[Subquery, Subquery, Subquery]:
    """Return last-learning, learned-lesson-count, and follow-up-count subqueries."""
    last_learning_subquery = (
        db.session.query(
            LearnProgressRecord.user_bid.label("user_bid"),
            db.func.max(LearnProgressRecord.updated_at).label("last_learning_at"),
        )
        .filter(
            LearnProgressRecord.shifu_bid == normalized_shifu_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.user_bid.in_(normalized_learner_bids),
        )
        .group_by(LearnProgressRecord.user_bid)
        .subquery()
    )

    learned_lesson_count_subquery = (
        db.session.query(
            LearnProgressRecord.user_bid.label("user_bid"),
            db.func.count(db.func.distinct(LearnProgressRecord.outline_item_bid)).label(
                "learned_lesson_count"
            ),
        )
        .filter(
            LearnProgressRecord.shifu_bid == normalized_shifu_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.user_bid.in_(normalized_learner_bids),
            LearnProgressRecord.outline_item_bid.in_(normalized_leaf_outline_bids)
            if normalized_leaf_outline_bids
            else False,
        )
        .group_by(LearnProgressRecord.user_bid)
        .subquery()
    )
    follow_up_count_subquery = (
        db.session.query(
            LearnGeneratedBlock.user_bid.label("user_bid"),
            db.func.count(LearnGeneratedBlock.id).label("follow_up_count"),
        )
        .filter(
            LearnGeneratedBlock.shifu_bid == normalized_shifu_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.role == ROLE_STUDENT,
            LearnGeneratedBlock.user_bid.in_(normalized_learner_bids),
        )
        .group_by(LearnGeneratedBlock.user_bid)
        .subquery()
    )

    return (
        last_learning_subquery,
        learned_lesson_count_subquery,
        follow_up_count_subquery,
    )


def _build_dashboard_course_learners(
    app: Flask,
    *,
    shifu_bid: str,
    learner_bids: Sequence[str],
    leaf_outline_bids: Sequence[str],
    page_index: int,
    page_size: int,
    keyword: str | None,
    learning_status: str | None,
    last_learning_start_time: str | None,
    last_learning_end_time: str | None,
    timezone_name: str | None,
) -> DashboardCourseDetailLearnersDTO:
    _ = timezone_name
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
    normalized_shifu_bid = str(shifu_bid or "").strip()
    normalized_learner_bids = sorted(
        {
            str(user_bid or "").strip()
            for user_bid in learner_bids
            if str(user_bid or "").strip()
        }
    )
    normalized_leaf_outline_bids = sorted(
        {
            str(outline_item_bid or "").strip()
            for outline_item_bid in leaf_outline_bids
            if str(outline_item_bid or "").strip()
        }
    )
    if not normalized_shifu_bid or not normalized_learner_bids:
        return DashboardCourseDetailLearnersDTO(
            page=1,
            page_size=safe_page_size,
            page_count=0,
            total=0,
            items=[],
        )

    total_lesson_count = len(normalized_leaf_outline_bids)
    normalized_learning_status = str(learning_status or "").strip().lower()
    if normalized_learning_status not in {"", "not_started", "learning", "completed"}:
        normalized_learning_status = ""

    learner_source = _build_learner_source_subquery(
        normalized_shifu_bid, normalized_learner_bids
    )
    (
        last_learning_subquery,
        learned_lesson_count_subquery,
        follow_up_count_subquery,
    ) = _build_learner_activity_subqueries(
        normalized_shifu_bid, normalized_learner_bids, normalized_leaf_outline_bids
    )
    joined_at_subquery = _build_learner_joined_at_subquery(
        normalized_shifu_bid, normalized_learner_bids, learner_source
    )

    learned_lesson_count_expression = db.func.coalesce(
        learned_lesson_count_subquery.c.learned_lesson_count,
        0,
    )
    learning_status_expression = _build_learning_status_expression(
        learned_lesson_count_expression, total_lesson_count
    )
    joined_at_expression = _build_learner_joined_at_expression(joined_at_subquery)
    filtered_query = (
        db.session.query(
            learner_source.c.user_bid.label("user_bid"),
            UserEntity.nickname.label("nickname"),
            last_learning_subquery.c.last_learning_at.label("last_learning_at"),
            joined_at_expression.label("joined_at"),
            learned_lesson_count_expression.label("learned_lesson_count"),
            db.func.coalesce(
                follow_up_count_subquery.c.follow_up_count,
                0,
            ).label("follow_up_count"),
            learning_status_expression.label("learning_status"),
        )
        .select_from(learner_source)
        .outerjoin(
            UserEntity,
            and_(
                UserEntity.user_bid == learner_source.c.user_bid,
                UserEntity.deleted == 0,
            ),
        )
        .outerjoin(
            last_learning_subquery,
            last_learning_subquery.c.user_bid == learner_source.c.user_bid,
        )
        .outerjoin(
            joined_at_subquery,
            joined_at_subquery.c.user_bid == learner_source.c.user_bid,
        )
        .outerjoin(
            follow_up_count_subquery,
            follow_up_count_subquery.c.user_bid == learner_source.c.user_bid,
        )
        .outerjoin(
            learned_lesson_count_subquery,
            learned_lesson_count_subquery.c.user_bid == learner_source.c.user_bid,
        )
    )
    keyword_filter = _build_dashboard_learner_keyword_filter(
        learner_source.c.user_bid,
        str(keyword or ""),
    )
    if keyword_filter is not None:
        filtered_query = filtered_query.filter(keyword_filter)
    if normalized_learning_status:
        filtered_query = filtered_query.filter(
            learning_status_expression == normalized_learning_status
        )
    if last_learning_start_dt is not None:
        filtered_query = filtered_query.filter(
            last_learning_subquery.c.last_learning_at >= last_learning_start_dt
        )
    if last_learning_end_dt_exclusive is not None:
        filtered_query = filtered_query.filter(
            last_learning_subquery.c.last_learning_at < last_learning_end_dt_exclusive
        )

    total = (
        db.session.query(db.func.count())
        .select_from(filtered_query.subquery())
        .scalar()
        or 0
    )
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
    page_rows = (
        filtered_query.order_by(
            last_learning_subquery.c.last_learning_at.is_(None),
            last_learning_subquery.c.last_learning_at.desc(),
            joined_at_expression.is_(None),
            joined_at_expression.desc(),
            learner_source.c.user_bid.desc(),
        )
        .offset(offset)
        .limit(safe_page_size)
        .all()
    )
    page_user_bids = [
        str(getattr(row, "user_bid", "") or "").strip()
        for row in page_rows
        if str(getattr(row, "user_bid", "") or "").strip()
    ]
    contact_map = _load_dashboard_course_user_contact_map(page_user_bids)
    paged_items = _build_learner_items(app, page_rows, contact_map, total_lesson_count)
    return DashboardCourseDetailLearnersDTO(
        page=resolved_page,
        page_size=safe_page_size,
        page_count=page_count,
        total=total,
        items=paged_items,
    )
