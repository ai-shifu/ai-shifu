"""Query helpers for the teacher-facing analytics dashboard."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.billing.consts import (
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.models import CreditLedgerEntry
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.dashboard.common import (
    COURSE_STATUS_PUBLISHED,  # noqa: F401  # re-exported public API
    COURSE_STATUS_UNPUBLISHED,  # noqa: F401  # re-exported public API
    DASHBOARD_COURSE_FOLLOW_UP_PAGE_SIZE_MAX,
    DASHBOARD_COURSE_LEARNER_PAGE_SIZE_MAX,  # noqa: F401  # re-exported public API
    DASHBOARD_COURSE_RATING_PAGE_SIZE_MAX,
    DASHBOARD_LEARNING_MODE_ORDER,
    FOLLOW_UP_ELEMENT_TYPE_ANSWER,  # noqa: F401  # re-exported public API
    FOLLOW_UP_ELEMENT_TYPE_ASK,  # noqa: F401  # re-exported public API
    LEARNING_MODE_CLASSROOM,  # noqa: F401  # re-exported public API
    LEARNING_MODE_LISTEN,
    LEARNING_MODE_READ,
    _build_course_outline_context_map,
    _build_dashboard_learner_keyword_filter,
    _dashboard_learner_keyword_matches,  # noqa: F401  # imported by tests from this module
    _format_average_score,
    _format_credit_value,
    _format_money,
    _format_percentage,
    _parse_dashboard_date_boundary,
    _resolve_dashboard_outline_keyword_match_bids,
    _validate_dashboard_date_range,
)
from flaskr.service.dashboard.dtos import (
    DashboardCourseDetailBasicInfoDTO,
    DashboardCourseDetailDTO,
    DashboardCourseDetailLearnerItemDTO,  # noqa: F401  # re-exported public API
    DashboardCourseDetailLearnersDTO,
    DashboardCourseDetailMetricsDTO,
    DashboardCourseFollowUpCurrentRecordDTO,
    DashboardCourseFollowUpDetailBasicInfoDTO,
    DashboardCourseFollowUpDetailDTO,
    DashboardCourseFollowUpItemDTO,
    DashboardCourseFollowUpListDTO,
    DashboardCourseFollowUpSummaryDTO,
    DashboardCourseFollowUpTimelineItemDTO,
    DashboardCourseLearningModeMetricDTO,
    DashboardCourseRatingItemDTO,
    DashboardCourseRatingListDTO,
    DashboardCourseRatingSummaryDTO,
    DashboardEntryCourseItemDTO,
    DashboardEntryDTO,
    DashboardEntrySummaryDTO,
)
from flaskr.service.dashboard.follow_up_sources import (
    _build_course_follow_up_base_subquery,
    _build_follow_up_source_status_map,
    _build_follow_up_user_keyword_filter,
    _load_follow_up_groups_for_progress_record,
    _resolve_follow_up_answer_content,
    _resolve_follow_up_matching_outline_bids,
    _resolve_follow_up_source_from_blocks,  # noqa: F401  # imported by tests from this module
    _resolve_follow_up_source_from_element,  # noqa: F401  # imported by tests from this module
)
from flaskr.service.dashboard.learners import (
    _build_dashboard_course_learners,
)
from flaskr.service.dashboard.loaders import (
    _collect_dashboard_entry_metrics,
    _load_course_leaf_outline_bids,
    _load_course_learner_bids,
    _load_dashboard_course_completed_learner_bids,
    _load_dashboard_course_created_at,
    _load_dashboard_course_follow_up_count_map,  # noqa: F401  # imported by tests from this module
    _load_dashboard_course_last_learning_map,  # noqa: F401  # imported by tests from this module
    _load_dashboard_course_learned_lesson_count_map,
    _load_dashboard_course_meta,
    _load_dashboard_course_outline_items,
    _load_dashboard_course_user_contact_map,
    _load_dashboard_course_user_map,
    _load_dashboard_entry_courses,
    _resolve_dashboard_course_status,
)
from flaskr.service.learn.const import (  # noqa: F401  # re-exported public API
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,  # noqa: F401  # re-exported public API
    LearnLessonFeedback,
    LearnProgressRecord,  # noqa: F401  # re-exported public API
)
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,  # noqa: F401  # re-exported public API
    LEARN_STATUS_RESET,  # noqa: F401  # re-exported public API
    ORDER_STATUS_SUCCESS,
)
from flaskr.service.order.models import Order
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,  # noqa: F401  # re-exported public API
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,  # noqa: F401  # re-exported public API
    BLOCK_TYPE_MDINTERACTION_VALUE,  # noqa: F401  # re-exported public API
)
from flaskr.service.shifu.demo_courses import (
    is_builtin_demo_course,  # noqa: F401  # re-exported public API
)
from flaskr.service.shifu.models import (
    AiCourseAuth,  # noqa: F401  # re-exported public API
    DraftShifu,  # noqa: F401  # re-exported public API
    PublishedOutlineItem,  # noqa: F401  # re-exported public API
    PublishedShifu,  # noqa: F401  # re-exported public API
)
from flaskr.service.user.models import (
    AuthCredential,  # noqa: F401  # re-exported public API
)
from flaskr.service.user.models import (
    UserInfo as UserEntity,  # noqa: TC002  # re-exported public API
)
from flaskr.util.datetime import now_utc
from sqlalchemy import case, false

if TYPE_CHECKING:
    from collections.abc import Sequence

    from flask import Flask
    from sqlalchemy.orm import Query
    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.sql.selectable import Subquery


def build_dashboard_entry(
    app: Flask,
    user_id: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    keyword: str | None = None,
    page_index: int = 1,
    page_size: int = 20,
    timezone_name: str | None = None,
) -> DashboardEntryDTO:
    """Build dashboard entry."""
    _ = timezone_name

    def _parse_optional_date(raw: str | None) -> date | None:
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
            resolved_end = parsed_end or now_utc().date()
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

        items: list[DashboardEntryCourseItemDTO] = []
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
                        metrics.order_amount_map.get(shifu_bid, Decimal(0))
                    ),
                    last_active_at=last_active,
                )
            )

        total_order_amount = Decimal(0)
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


def _summarize_course_follow_ups(
    follow_up_base: Subquery,
) -> DashboardCourseFollowUpSummaryDTO:
    """Summarize every follow-up of the course before list filters apply."""
    full_summary_row = db.session.query(
        db.func.count(follow_up_base.c.id).label("follow_up_count"),
        db.func.count(
            db.func.distinct(db.func.nullif(follow_up_base.c.user_bid, ""))
        ).label("user_count"),
        db.func.count(
            db.func.distinct(db.func.nullif(follow_up_base.c.outline_item_bid, ""))
        ).label("lesson_count"),
        db.func.max(follow_up_base.c.created_at).label("latest_follow_up_at"),
    ).one()
    return DashboardCourseFollowUpSummaryDTO(
        follow_up_count=int(getattr(full_summary_row, "follow_up_count", 0) or 0),
        user_count=int(getattr(full_summary_row, "user_count", 0) or 0),
        lesson_count=int(getattr(full_summary_row, "lesson_count", 0) or 0),
        latest_follow_up_at=getattr(full_summary_row, "latest_follow_up_at", None),
    )


def _filter_course_follow_ups(
    follow_up_base: Subquery,
    *,
    user_bid: str | None,
    user_keyword_filter: ColumnElement[bool] | None,
    matching_outline_item_bids: set[str] | None,
    start_dt: datetime | None,
    end_dt_exclusive: datetime | None,
) -> Query:
    """Apply learner, keyword, chapter, and date filters to course follow-ups."""
    filtered_query = db.session.query(follow_up_base)
    normalized_user_bid = str(user_bid or "").strip()
    if normalized_user_bid:
        filtered_query = filtered_query.filter(
            follow_up_base.c.user_bid == normalized_user_bid
        )
    if user_keyword_filter is not None:
        filtered_query = filtered_query.filter(user_keyword_filter)
    if matching_outline_item_bids is not None:
        filtered_query = filtered_query.filter(
            follow_up_base.c.outline_item_bid.in_(sorted(matching_outline_item_bids))
        )
    if start_dt is not None:
        filtered_query = filtered_query.filter(follow_up_base.c.created_at >= start_dt)
    if end_dt_exclusive is not None:
        filtered_query = filtered_query.filter(
            follow_up_base.c.created_at < end_dt_exclusive
        )
    return filtered_query


def _build_course_follow_up_items(
    paged_rows: Sequence[object],
    *,
    outline_context_map: dict[str, dict[str, str]],
    user_map: dict[str, UserEntity],
    contact_map: dict[str, dict[str, str]],
    source_status_map: dict[str, bool],
) -> list[DashboardCourseFollowUpItemDTO]:
    items: list[DashboardCourseFollowUpItemDTO] = []
    for row in paged_rows:
        generated_block_bid = str(getattr(row, "generated_block_bid", "") or "").strip()
        outline_item_bid = str(getattr(row, "outline_item_bid", "") or "").strip()
        user_bid = str(getattr(row, "user_bid", "") or "").strip()
        context = outline_context_map.get(
            outline_item_bid,
            {
                "chapter_title": "",
                "lesson_title": "",
            },
        )
        user = user_map.get(user_bid)
        contact = contact_map.get(user_bid, {})
        items.append(
            DashboardCourseFollowUpItemDTO(
                generated_block_bid=generated_block_bid,
                progress_record_bid=str(getattr(row, "progress_record_bid", "") or ""),
                user_bid=user_bid,
                mobile=str(contact.get("mobile", "") or ""),
                email=str(contact.get("email", "") or ""),
                nickname=str(getattr(user, "nickname", "") or ""),
                chapter_title=str(context.get("chapter_title", "") or ""),
                lesson_title=str(context.get("lesson_title", "") or ""),
                follow_up_content=str(getattr(row, "follow_up_content", "") or ""),
                has_source_output=bool(
                    source_status_map.get(generated_block_bid, False)
                ),
                turn_index=int(getattr(row, "turn_index", 0) or 0),
                created_at=getattr(row, "created_at", None),
            )
        )
    return items


def _filter_follow_up_rows_by_source_status(
    filtered_query: Query,
    follow_up_base: Subquery,
    *,
    shifu_bid: str,
    source_status: str,
) -> tuple[list[object], dict[str, bool]]:
    """Keep follow-ups whose source output matches the requested status."""
    filtered_rows = filtered_query.order_by(
        follow_up_base.c.created_at.desc(),
        follow_up_base.c.id.desc(),
    ).all()
    filtered_source_status_map = _build_follow_up_source_status_map(
        shifu_bid=shifu_bid,
        generated_block_bids=[
            str(getattr(row, "generated_block_bid", "") or "") for row in filtered_rows
        ],
    )
    filtered_rows = [
        row
        for row in filtered_rows
        if filtered_source_status_map.get(
            str(getattr(row, "generated_block_bid", "") or "").strip(), False
        )
        == (source_status == "resolved")
    ]
    return filtered_rows, filtered_source_status_map


def _build_paged_follow_up_items(
    paged_rows: Sequence[object],
    *,
    shifu_bid: str,
    outline_context_map: dict[str, dict[str, str]],
    source_status: str,
    filtered_source_status_map: dict[str, bool] | None,
) -> list[DashboardCourseFollowUpItemDTO]:
    """Load learner contacts and source status, then build page items."""
    user_bids = sorted(
        {
            str(getattr(row, "user_bid", "") or "").strip()
            for row in paged_rows
            if str(getattr(row, "user_bid", "") or "").strip()
        }
    )
    user_map = _load_dashboard_course_user_map(user_bids)
    contact_map = _load_dashboard_course_user_contact_map(user_bids)
    if source_status and filtered_source_status_map is not None:
        source_status_map = filtered_source_status_map
    else:
        source_status_map = _build_follow_up_source_status_map(
            shifu_bid=shifu_bid,
            generated_block_bids=[
                str(getattr(row, "generated_block_bid", "") or "") for row in paged_rows
            ],
        )

    return _build_course_follow_up_items(
        paged_rows,
        outline_context_map=outline_context_map,
        user_map=user_map,
        contact_map=contact_map,
        source_status_map=source_status_map,
    )


def build_dashboard_course_follow_ups(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    *,
    page_index: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    user_bid: str | None = None,
    chapter_keyword: str | None = None,
    source_status: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    timezone_name: str | None = None,
) -> DashboardCourseFollowUpListDTO:
    """Build dashboard course follow ups."""
    _ = timezone_name
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        if _load_dashboard_course_meta(user_id, normalized_shifu_bid) is None:
            raise_error("server.shifu.shifuNotFound")

        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            DASHBOARD_COURSE_FOLLOW_UP_PAGE_SIZE_MAX,
        )
        outline_items = _load_dashboard_course_outline_items(normalized_shifu_bid)
        outline_context_map = _build_course_outline_context_map(outline_items)

        follow_up_base = _build_course_follow_up_base_subquery(normalized_shifu_bid)
        full_summary = _summarize_course_follow_ups(follow_up_base)
        user_keyword_filter = _build_follow_up_user_keyword_filter(
            follow_up_base.c.user_bid,
            str(keyword or "").strip(),
        )
        matching_outline_item_bids = _resolve_follow_up_matching_outline_bids(
            outline_context_map,
            str(chapter_keyword or "").strip().lower(),
        )
        normalized_source_status = str(source_status or "").strip().lower()
        if normalized_source_status not in {"", "resolved", "missing"}:
            raise_param_error("source_status")

        if chapter_keyword and not matching_outline_item_bids:
            return DashboardCourseFollowUpListDTO(
                summary=full_summary,
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )

        start_dt = _parse_dashboard_date_boundary(
            start_time,
            param_name="start_time",
        )
        end_dt_exclusive = _parse_dashboard_date_boundary(
            end_time,
            param_name="end_time",
            end_of_day=True,
        )
        _validate_dashboard_date_range(
            start_dt=start_dt,
            end_dt_exclusive=end_dt_exclusive,
            start_param_name="start_time",
            end_param_name="end_time",
        )

        filtered_query = _filter_course_follow_ups(
            follow_up_base,
            user_bid=user_bid,
            user_keyword_filter=user_keyword_filter,
            matching_outline_item_bids=matching_outline_item_bids,
            start_dt=start_dt,
            end_dt_exclusive=end_dt_exclusive,
        )

        filtered_source_status_map: dict[str, bool] | None = None
        if normalized_source_status:
            filtered_rows, filtered_source_status_map = (
                _filter_follow_up_rows_by_source_status(
                    filtered_query,
                    follow_up_base,
                    shifu_bid=normalized_shifu_bid,
                    source_status=normalized_source_status,
                )
            )
            total = len(filtered_rows)
        else:
            filtered_follow_ups = filtered_query.subquery()
            total = (
                db.session.query(db.func.count(filtered_follow_ups.c.id)).scalar() or 0
            )
        if total == 0:
            return DashboardCourseFollowUpListDTO(
                summary=full_summary,
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )

        page_count = (
            (total + safe_page_size - 1) // safe_page_size if safe_page_size else 0
        )
        resolved_page = min(safe_page_index, max(page_count, 1))
        start = (resolved_page - 1) * safe_page_size
        if normalized_source_status:
            paged_rows = filtered_rows[start : start + safe_page_size]
        else:
            paged_rows = (
                db.session.query(filtered_follow_ups)
                .order_by(
                    filtered_follow_ups.c.created_at.desc(),
                    filtered_follow_ups.c.id.desc(),
                )
                .offset(start)
                .limit(safe_page_size)
                .all()
            )
        items = _build_paged_follow_up_items(
            paged_rows,
            shifu_bid=normalized_shifu_bid,
            outline_context_map=outline_context_map,
            source_status=normalized_source_status,
            filtered_source_status_map=filtered_source_status_map,
        )

        return DashboardCourseFollowUpListDTO(
            summary=full_summary,
            items=items,
            page=resolved_page,
            page_size=safe_page_size,
            total=total,
            page_count=page_count,
        )


def build_dashboard_course_follow_up_detail(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    generated_block_bid: str,
    *,
    timezone_name: str | None = None,
) -> DashboardCourseFollowUpDetailDTO:
    """Build dashboard course follow up detail."""
    _ = timezone_name
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_generated_block_bid = str(generated_block_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")
        if not normalized_generated_block_bid:
            raise_param_error("generated_block_bid is required")

        course_meta = _load_dashboard_course_meta(user_id, normalized_shifu_bid)
        if course_meta is None:
            raise_error("server.shifu.shifuNotFound")

        outline_items = _load_dashboard_course_outline_items(normalized_shifu_bid)
        outline_context_map = _build_course_outline_context_map(outline_items)
        ask_block = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.shifu_bid == normalized_shifu_bid,
                LearnGeneratedBlock.generated_block_bid
                == normalized_generated_block_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
                LearnGeneratedBlock.role == ROLE_STUDENT,
            )
            .order_by(LearnGeneratedBlock.id.desc())
            .first()
        )
        if ask_block is None:
            raise_param_error("generated_block_bid")

        progress_record_bid = str(ask_block.progress_record_bid or "").strip()
        groups = _load_follow_up_groups_for_progress_record(progress_record_bid)
        selected_group_index = next(
            (
                index
                for index, group in enumerate(groups)
                if str(group["ask_block"].generated_block_bid or "").strip()
                == normalized_generated_block_bid
            ),
            -1,
        )
        if selected_group_index < 0:
            raise_param_error("generated_block_bid")

        selected_group = groups[selected_group_index]
        user_bid = str(ask_block.user_bid or "").strip()
        user = _load_dashboard_course_user_map([user_bid]).get(user_bid)
        contact = _load_dashboard_course_user_contact_map([user_bid]).get(user_bid, {})
        context = outline_context_map.get(
            str(ask_block.outline_item_bid or "").strip(),
            {
                "chapter_title": "",
                "lesson_title": "",
            },
        )

        timeline: list[DashboardCourseFollowUpTimelineItemDTO] = []
        for index, group in enumerate(groups):
            current_ask_block = group["ask_block"]
            is_current = index == selected_group_index
            timeline.append(
                DashboardCourseFollowUpTimelineItemDTO(
                    role="student",
                    content=str(
                        getattr(current_ask_block, "generated_content", "") or ""
                    ),
                    created_at=getattr(current_ask_block, "created_at", None),
                    is_current=is_current,
                )
            )
            answer_block = group.get("answer_block")
            answer_content = _resolve_follow_up_answer_content(answer_block)
            if answer_content:
                timeline.append(
                    DashboardCourseFollowUpTimelineItemDTO(
                        role="teacher",
                        content=answer_content,
                        created_at=getattr(answer_block, "created_at", None),
                        is_current=is_current,
                    )
                )

        selected_answer_block = selected_group.get("answer_block")
        return DashboardCourseFollowUpDetailDTO(
            basic_info=DashboardCourseFollowUpDetailBasicInfoDTO(
                generated_block_bid=normalized_generated_block_bid,
                progress_record_bid=progress_record_bid,
                user_bid=user_bid,
                mobile=str(contact.get("mobile", "") or ""),
                email=str(contact.get("email", "") or ""),
                nickname=str(getattr(user, "nickname", "") or ""),
                chapter_title=str(context.get("chapter_title", "") or ""),
                lesson_title=str(context.get("lesson_title", "") or ""),
                created_at=getattr(ask_block, "created_at", None),
                turn_index=selected_group_index + 1,
            ),
            current_record=DashboardCourseFollowUpCurrentRecordDTO(
                follow_up_content=str(
                    getattr(ask_block, "generated_content", "") or ""
                ),
                answer_content=_resolve_follow_up_answer_content(selected_answer_block),
            ),
            timeline=timeline,
        )


def _summarize_course_ratings(
    normalized_shifu_bid: str,
    rated_at_expression: ColumnElement[datetime],
) -> DashboardCourseRatingSummaryDTO:
    """Summarize every rating of the course before list filters apply."""
    summary_row = (
        db.session.query(
            db.func.avg(LearnLessonFeedback.score).label("average_score"),
            db.func.count(LearnLessonFeedback.id).label("rating_count"),
            db.func.count(db.func.distinct(LearnLessonFeedback.user_bid)).label(
                "user_count"
            ),
            db.func.max(rated_at_expression).label("latest_rated_at"),
        )
        .filter(
            LearnLessonFeedback.shifu_bid == normalized_shifu_bid,
            LearnLessonFeedback.deleted == 0,
        )
        .first()
    )
    return DashboardCourseRatingSummaryDTO(
        average_score=_format_average_score(
            getattr(summary_row, "average_score", None)
        ),
        rating_count=int(getattr(summary_row, "rating_count", 0) or 0),
        user_count=int(getattr(summary_row, "user_count", 0) or 0),
        latest_rated_at=getattr(summary_row, "latest_rated_at", None),
    )


def _filter_course_ratings(
    filtered_query: Query,
    *,
    outline_context_map: dict[str, dict[str, str]],
    rated_at_expression: ColumnElement[datetime],
    keyword: str | None,
    normalized_chapter_keyword: str,
    normalized_score: str,
    normalized_has_comment: str,
    start_dt: datetime | None,
    end_dt_exclusive: datetime | None,
) -> Query:
    """Apply learner, chapter, score, comment, and date filters to ratings."""
    keyword_filter = _build_dashboard_learner_keyword_filter(
        LearnLessonFeedback.user_bid,
        str(keyword or ""),
    )
    if keyword_filter is not None:
        filtered_query = filtered_query.filter(keyword_filter)

    if normalized_chapter_keyword:
        matched_outline_item_bids = sorted(
            _resolve_dashboard_outline_keyword_match_bids(
                outline_context_map,
                normalized_chapter_keyword,
            )
        )
        if matched_outline_item_bids:
            filtered_query = filtered_query.filter(
                LearnLessonFeedback.outline_item_bid.in_(matched_outline_item_bids)
            )
        else:
            filtered_query = filtered_query.filter(false())

    if normalized_score:
        filtered_query = filtered_query.filter(
            LearnLessonFeedback.score == int(normalized_score)
        )
    if normalized_has_comment == "true":
        filtered_query = filtered_query.filter(
            db.func.trim(db.func.coalesce(LearnLessonFeedback.comment, "")) != ""
        )
    if start_dt is not None:
        filtered_query = filtered_query.filter(rated_at_expression >= start_dt)
    if end_dt_exclusive is not None:
        filtered_query = filtered_query.filter(rated_at_expression < end_dt_exclusive)
    return filtered_query


def _build_course_rating_items(
    page_rows: Sequence[object],
    *,
    outline_context_map: dict[str, dict[str, str]],
    user_map: dict[str, UserEntity],
    contact_map: dict[str, dict[str, str]],
) -> list[DashboardCourseRatingItemDTO]:
    items: list[DashboardCourseRatingItemDTO] = []
    for row in page_rows:
        user_bid = str(getattr(row, "user_bid", "") or "").strip()
        outline_item_bid = str(getattr(row, "outline_item_bid", "") or "").strip()
        rated_at = getattr(row, "rated_at", None)
        user = user_map.get(user_bid)
        contact = contact_map.get(user_bid, {"mobile": "", "email": ""})
        context = outline_context_map.get(
            outline_item_bid,
            {
                "chapter_title": "",
                "lesson_title": "",
            },
        )
        items.append(
            DashboardCourseRatingItemDTO(
                lesson_feedback_bid=str(getattr(row, "lesson_feedback_bid", "") or ""),
                progress_record_bid=str(getattr(row, "progress_record_bid", "") or ""),
                user_bid=user_bid,
                mobile=str(contact.get("mobile", "") or ""),
                email=str(contact.get("email", "") or ""),
                nickname=str(getattr(user, "nickname", "") or ""),
                chapter_title=str(context.get("chapter_title", "") or ""),
                lesson_title=str(context.get("lesson_title", "") or ""),
                score=int(getattr(row, "score", 0) or 0),
                comment=str(getattr(row, "comment", "") or ""),
                rated_at=rated_at,
            )
        )
    return items


def build_dashboard_course_ratings(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    *,
    page_index: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    chapter_keyword: str | None = None,
    score: str | None = None,
    has_comment: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    timezone_name: str | None = None,
) -> DashboardCourseRatingListDTO:
    """Build dashboard course ratings."""
    _ = timezone_name
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        course_meta = _load_dashboard_course_meta(user_id, normalized_shifu_bid)
        if course_meta is None:
            raise_error("server.shifu.shifuNotFound")

        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            DASHBOARD_COURSE_RATING_PAGE_SIZE_MAX,
        )
        normalized_score = str(score or "").strip()
        normalized_has_comment = str(has_comment or "").strip().lower()
        if normalized_score and normalized_score not in {"1", "2", "3", "4", "5"}:
            raise_param_error("score")
        if normalized_has_comment and normalized_has_comment != "true":
            raise_param_error("has_comment")

        outline_items = _load_dashboard_course_outline_items(normalized_shifu_bid)
        outline_context_map = _build_course_outline_context_map(outline_items)
        normalized_chapter_keyword = str(chapter_keyword or "").strip().lower()
        start_dt = _parse_dashboard_date_boundary(
            start_time,
            param_name="start_time",
        )
        end_dt_exclusive = _parse_dashboard_date_boundary(
            end_time,
            param_name="end_time",
            end_of_day=True,
        )
        _validate_dashboard_date_range(
            start_dt=start_dt,
            end_dt_exclusive=end_dt_exclusive,
            start_param_name="start_time",
            end_param_name="end_time",
        )
        rated_at_expression = db.func.coalesce(
            LearnLessonFeedback.updated_at,
            LearnLessonFeedback.created_at,
        )
        rating_base_query = db.session.query(
            LearnLessonFeedback.id.label("id"),
            LearnLessonFeedback.lesson_feedback_bid.label("lesson_feedback_bid"),
            LearnLessonFeedback.progress_record_bid.label("progress_record_bid"),
            LearnLessonFeedback.user_bid.label("user_bid"),
            LearnLessonFeedback.outline_item_bid.label("outline_item_bid"),
            LearnLessonFeedback.score.label("score"),
            LearnLessonFeedback.comment.label("comment"),
            rated_at_expression.label("rated_at"),
        ).filter(
            LearnLessonFeedback.shifu_bid == normalized_shifu_bid,
            LearnLessonFeedback.deleted == 0,
        )
        full_summary = _summarize_course_ratings(
            normalized_shifu_bid, rated_at_expression
        )
        filtered_query = _filter_course_ratings(
            rating_base_query,
            outline_context_map=outline_context_map,
            rated_at_expression=rated_at_expression,
            keyword=keyword,
            normalized_chapter_keyword=normalized_chapter_keyword,
            normalized_score=normalized_score,
            normalized_has_comment=normalized_has_comment,
            start_dt=start_dt,
            end_dt_exclusive=end_dt_exclusive,
        )

        total = (
            db.session.query(db.func.count())
            .select_from(filtered_query.subquery())
            .scalar()
            or 0
        )
        if total == 0:
            return DashboardCourseRatingListDTO(
                summary=full_summary,
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )

        page_count = (
            (total + safe_page_size - 1) // safe_page_size if safe_page_size else 0
        )
        resolved_page = min(safe_page_index, max(page_count, 1))
        start = (resolved_page - 1) * safe_page_size
        page_rows = (
            filtered_query.order_by(
                rated_at_expression.desc(),
                LearnLessonFeedback.id.desc(),
            )
            .offset(start)
            .limit(safe_page_size)
            .all()
        )
        page_user_bids = sorted(
            {
                str(getattr(row, "user_bid", "") or "").strip()
                for row in page_rows
                if str(getattr(row, "user_bid", "") or "").strip()
            }
        )
        user_map = _load_dashboard_course_user_map(page_user_bids)
        contact_map = _load_dashboard_course_user_contact_map(page_user_bids)
        items = _build_course_rating_items(
            page_rows,
            outline_context_map=outline_context_map,
            user_map=user_map,
            contact_map=contact_map,
        )
        return DashboardCourseRatingListDTO(
            summary=full_summary,
            items=items,
            page=resolved_page,
            page_size=safe_page_size,
            total=total,
            page_count=page_count,
        )


def build_dashboard_course_learners(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    *,
    page_index: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    learning_status: str | None = None,
    last_learning_start_time: str | None = None,
    last_learning_end_time: str | None = None,
    timezone_name: str | None = None,
) -> DashboardCourseDetailLearnersDTO:
    """Build dashboard course learners."""
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        course_meta = _load_dashboard_course_meta(user_id, normalized_shifu_bid)
        if course_meta is None:
            raise_error("server.shifu.shifuNotFound")

        learner_bids = sorted(_load_course_learner_bids(normalized_shifu_bid))
        leaf_outline_bids = _load_course_leaf_outline_bids(normalized_shifu_bid)
        return _build_dashboard_course_learners(
            app,
            shifu_bid=normalized_shifu_bid,
            learner_bids=learner_bids,
            leaf_outline_bids=leaf_outline_bids,
            page_index=page_index,
            page_size=page_size,
            keyword=keyword,
            learning_status=learning_status,
            last_learning_start_time=last_learning_start_time,
            last_learning_end_time=last_learning_end_time,
            timezone_name=timezone_name,
        )


def _build_dashboard_learning_mode_metrics(
    shifu_bid: str,
) -> list[DashboardCourseLearningModeMetricDTO]:
    recent_window_start = now_utc() - timedelta(days=7)
    learning_mode_expr = BillUsageRecord.extra["learning_mode"].as_string()
    normalized_learning_mode_expr = db.func.lower(
        db.func.trim(db.func.coalesce(learning_mode_expr, ""))
    )
    inferred_learning_mode_expr = case(
        (
            normalized_learning_mode_expr.in_(DASHBOARD_LEARNING_MODE_ORDER),
            normalized_learning_mode_expr,
        ),
        (
            BillUsageRecord.usage_type == BILL_USAGE_TYPE_TTS,
            LEARNING_MODE_LISTEN,
        ),
        else_=LEARNING_MODE_READ,
    )
    ledger_credit_subquery = (
        db.session.query(
            CreditLedgerEntry.source_bid.label("usage_bid"),
            db.func.coalesce(
                db.func.sum(db.func.abs(CreditLedgerEntry.amount)), 0
            ).label("consumed_credits"),
        )
        .filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_USAGE,
        )
        .group_by(CreditLedgerEntry.source_bid)
        .subquery()
    )
    ledger_amount_expr = db.func.coalesce(ledger_credit_subquery.c.consumed_credits, 0)
    rows = (
        db.session.query(
            inferred_learning_mode_expr.label("learning_mode"),
            db.func.count(db.func.distinct(BillUsageRecord.user_bid)).label(
                "participant_count"
            ),
            db.func.coalesce(db.func.sum(ledger_amount_expr), 0).label(
                "consumed_credits"
            ),
            db.func.coalesce(
                db.func.sum(
                    case(
                        (
                            BillUsageRecord.created_at >= recent_window_start,
                            ledger_amount_expr,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("recent_consumed_credits"),
        )
        .outerjoin(
            ledger_credit_subquery,
            ledger_credit_subquery.c.usage_bid == BillUsageRecord.usage_bid,
        )
        .filter(
            BillUsageRecord.shifu_bid == shifu_bid,
            BillUsageRecord.deleted == 0,
            BillUsageRecord.billable == 1,
            BillUsageRecord.status == 0,
            BillUsageRecord.record_level == 0,
            BillUsageRecord.usage_scene == BILL_USAGE_SCENE_PROD,
            BillUsageRecord.usage_type.in_((BILL_USAGE_TYPE_LLM, BILL_USAGE_TYPE_TTS)),
        )
        .group_by(inferred_learning_mode_expr)
        .all()
    )
    row_map = {
        str(getattr(row, "learning_mode", "") or "").strip(): row for row in rows
    }
    metrics: list[DashboardCourseLearningModeMetricDTO] = []
    for mode in DASHBOARD_LEARNING_MODE_ORDER:
        row = row_map.get(mode)
        participant_count = int(getattr(row, "participant_count", 0) or 0)
        consumed_credits = Decimal(str(getattr(row, "consumed_credits", 0) or 0))
        recent_consumed_credits = Decimal(
            str(getattr(row, "recent_consumed_credits", 0) or 0)
        )
        consumption_speed = ""
        if row is not None:
            consumption_speed = _format_credit_value(
                recent_consumed_credits / Decimal(7)
            )
        average_consumed_credits = ""
        if participant_count > 0:
            average_consumed_credits = _format_credit_value(
                consumed_credits / Decimal(participant_count)
            )
        metrics.append(
            DashboardCourseLearningModeMetricDTO(
                mode=mode,
                participant_count=participant_count,
                consumed_credits=_format_credit_value(consumed_credits),
                consumption_speed=consumption_speed,
                average_consumed_credits=average_consumed_credits,
            )
        )
    return metrics


def build_dashboard_course_detail(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    *,
    timezone_name: str | None = None,
) -> DashboardCourseDetailDTO:
    """Build dashboard course detail."""
    _ = timezone_name
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        course_meta = _load_dashboard_course_meta(user_id, normalized_shifu_bid)
        if course_meta is None:
            raise_error("server.shifu.shifuNotFound")

        learner_bids = _load_course_learner_bids(normalized_shifu_bid)
        learner_count = len(learner_bids)
        leaf_outline_bids = _load_course_leaf_outline_bids(normalized_shifu_bid)
        sorted_learner_bids = sorted(learner_bids)

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

        completed_learner_bids = _load_dashboard_course_completed_learner_bids(
            normalized_shifu_bid,
            leaf_outline_bids,
        )
        completed_learner_count = len(completed_learner_bids)

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
        rating_score = (
            db.session.query(db.func.avg(LearnLessonFeedback.score))
            .filter(
                LearnLessonFeedback.shifu_bid == normalized_shifu_bid,
                LearnLessonFeedback.deleted == 0,
            )
            .scalar()
        )

        created_at = _load_dashboard_course_created_at(normalized_shifu_bid)
        learned_lesson_count_map = _load_dashboard_course_learned_lesson_count_map(
            normalized_shifu_bid,
            sorted_learner_bids,
            leaf_outline_bids,
        )
        learning_mode_metrics = _build_dashboard_learning_mode_metrics(
            normalized_shifu_bid
        )
        learning_learner_count = sum(
            1
            for learner_bid in sorted_learner_bids
            if learned_lesson_count_map.get(learner_bid, 0) > 0
            and learner_bid not in completed_learner_bids
        )

        return DashboardCourseDetailDTO(
            basic_info=DashboardCourseDetailBasicInfoDTO(
                shifu_bid=normalized_shifu_bid,
                course_name=course_meta.shifu_name,
                course_status=_resolve_dashboard_course_status(normalized_shifu_bid),
                created_at=created_at,
                chapter_count=len(leaf_outline_bids),
                learner_count=learner_count,
            ),
            metrics=DashboardCourseDetailMetricsDTO(
                order_count=order_count,
                order_amount=_format_money(order_amount),
                learning_learner_count=int(learning_learner_count),
                completed_learner_count=completed_learner_count,
                completion_rate=_format_percentage(
                    completed_learner_count,
                    learner_count,
                ),
                total_follow_up_count=int(total_follow_up_count),
                rating_score=_format_average_score(rating_score),
            ),
            learning_mode_metrics=learning_mode_metrics,
        )
