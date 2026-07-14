"""Operator course rating listing and summary views.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

import math
from typing import Optional
from flask import Flask
from flaskr.dao import db
from flaskr.service.learn.models import (
    LearnLessonFeedback,
)
from flaskr.service.common.models import (
    raise_param_error,
)
from flaskr.service.shifu.admin_dtos_courses import (
    AdminOperationCourseRatingItemDTO,
    AdminOperationCourseRatingListDTO,
    AdminOperationCourseRatingSummaryDTO,
)

from flaskr.service.shifu.admin_operations.courses_follow_ups import (
    _build_follow_up_user_keyword_filter,
    _resolve_follow_up_matching_outline_bids,
)
from flaskr.service.shifu.admin_operations.courses_shared import (
    COURSE_RATING_LIST_MAX_PAGE_SIZE,
    _build_course_outline_context_map,
    _format_average_score,
    _load_operator_course_outline_items,
    _load_user_map,
    _normalize_identifier,
)


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


def get_operator_course_ratings(
    app: Flask,
    *,
    shifu_bid: str,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
    include_summary: bool = True,
) -> AdminOperationCourseRatingListDTO:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            COURSE_RATING_LIST_MAX_PAGE_SIZE,
        )
        filters = filters or {}

        _detail_source, outline_items = _load_operator_course_outline_items(
            normalized_shifu_bid
        )
        outline_context_map = _build_course_outline_context_map(outline_items)
        keyword = _normalize_identifier(str(filters.get("keyword", "") or "")).lower()
        chapter_keyword = str(filters.get("chapter_keyword", "") or "").strip().lower()
        score_filter = str(filters.get("score", "") or "").strip()
        mode_filter = _resolve_course_rating_mode(str(filters.get("mode", "") or ""))
        has_comment_filter = str(filters.get("has_comment", "") or "").strip().lower()
        sort_by = _resolve_course_rating_sort_by(str(filters.get("sort_by", "") or ""))
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")

        normalized_score_filter: Optional[int] = None
        if score_filter:
            if score_filter not in {"1", "2", "3", "4", "5"}:
                raise_param_error("score")
            normalized_score_filter = int(score_filter)
        if str(filters.get("mode", "") or "").strip() and not mode_filter:
            raise_param_error("mode")
        if has_comment_filter and has_comment_filter != "true":
            raise_param_error("has_comment")
        if str(filters.get("sort_by", "") or "").strip() and not sort_by:
            raise_param_error("sort_by")

        rated_at_expression = db.func.coalesce(
            LearnLessonFeedback.updated_at,
            LearnLessonFeedback.created_at,
        )
        base_filters = [
            LearnLessonFeedback.shifu_bid == normalized_shifu_bid,
            LearnLessonFeedback.deleted == 0,
        ]

        user_keyword_filter = _build_follow_up_user_keyword_filter(
            LearnLessonFeedback.user_bid,
            keyword,
        )
        if user_keyword_filter is not None:
            base_filters.append(user_keyword_filter)

        matching_outline_item_bids = _resolve_follow_up_matching_outline_bids(
            outline_context_map,
            chapter_keyword,
        )
        if matching_outline_item_bids is not None:
            if not matching_outline_item_bids:
                return AdminOperationCourseRatingListDTO(
                    summary=AdminOperationCourseRatingSummaryDTO(),
                    items=[],
                    page=safe_page_index,
                    page_size=safe_page_size,
                    total=0,
                    page_count=0,
                )
            base_filters.append(
                LearnLessonFeedback.outline_item_bid.in_(
                    sorted(matching_outline_item_bids)
                )
            )

        if normalized_score_filter is not None:
            base_filters.append(LearnLessonFeedback.score == normalized_score_filter)
        if mode_filter:
            base_filters.append(LearnLessonFeedback.mode == mode_filter)
        if has_comment_filter == "true":
            base_filters.append(
                db.func.trim(db.func.coalesce(LearnLessonFeedback.comment, "")) != ""
            )
        if start_time:
            base_filters.append(rated_at_expression >= start_time)
        if end_time:
            base_filters.append(rated_at_expression <= end_time)

        summary_source = (
            db.session.query(
                LearnLessonFeedback.id.label("id"),
                LearnLessonFeedback.score.label("score"),
                LearnLessonFeedback.user_bid.label("user_bid"),
                rated_at_expression.label("rated_at"),
            )
            .filter(*base_filters)
            .subquery()
        )
        if include_summary:
            summary_row = db.session.query(
                db.func.avg(summary_source.c.score).label("average_score"),
                db.func.count(summary_source.c.id).label("rating_count"),
                db.func.count(
                    db.func.distinct(db.func.nullif(summary_source.c.user_bid, ""))
                ).label("user_count"),
                db.func.max(summary_source.c.rated_at).label("latest_rated_at"),
            ).one()
            total = int(getattr(summary_row, "rating_count", 0) or 0)
        else:
            summary_row = None
            total = int(
                db.session.query(db.func.count(summary_source.c.id)).scalar() or 0
            )

        if total == 0:
            return AdminOperationCourseRatingListDTO(
                summary=AdminOperationCourseRatingSummaryDTO(),
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )

        start = (safe_page_index - 1) * safe_page_size
        page_query = db.session.query(
            LearnLessonFeedback.id.label("id"),
            LearnLessonFeedback.lesson_feedback_bid.label("lesson_feedback_bid"),
            LearnLessonFeedback.progress_record_bid.label("progress_record_bid"),
            LearnLessonFeedback.user_bid.label("user_bid"),
            LearnLessonFeedback.outline_item_bid.label("outline_item_bid"),
            LearnLessonFeedback.score.label("score"),
            LearnLessonFeedback.comment.label("comment"),
            LearnLessonFeedback.mode.label("mode"),
            rated_at_expression.label("rated_at"),
        ).filter(*base_filters)
        ordered_query = page_query.order_by(
            rated_at_expression.desc(),
            LearnLessonFeedback.id.desc(),
        )
        if sort_by == "score_asc":
            ordered_query = page_query.order_by(
                LearnLessonFeedback.score.asc(),
                rated_at_expression.desc(),
                LearnLessonFeedback.id.desc(),
            )
        page_rows = ordered_query.offset(start).limit(safe_page_size).all()
        user_map = _load_user_map(
            sorted(
                {
                    str(getattr(row, "user_bid", "") or "").strip()
                    for row in page_rows
                    if str(getattr(row, "user_bid", "") or "").strip()
                }
            )
        )

        items: list[AdminOperationCourseRatingItemDTO] = []
        for row in page_rows:
            user_bid = str(getattr(row, "user_bid", "") or "").strip()
            outline_item_bid = str(getattr(row, "outline_item_bid", "") or "").strip()
            context = outline_context_map.get(
                outline_item_bid,
                {
                    "chapter_outline_item_bid": "",
                    "chapter_title": "",
                    "lesson_outline_item_bid": outline_item_bid,
                    "lesson_title": "",
                },
            )
            user = user_map.get(user_bid, {})
            items.append(
                AdminOperationCourseRatingItemDTO(
                    lesson_feedback_bid=str(
                        getattr(row, "lesson_feedback_bid", "") or ""
                    ),
                    progress_record_bid=str(
                        getattr(row, "progress_record_bid", "") or ""
                    ),
                    user_bid=user_bid,
                    mobile=str(user.get("mobile", "") or ""),
                    email=str(user.get("email", "") or ""),
                    nickname=str(user.get("nickname", "") or ""),
                    chapter_outline_item_bid=str(
                        context.get("chapter_outline_item_bid", "") or ""
                    ),
                    chapter_title=str(context.get("chapter_title", "") or ""),
                    lesson_outline_item_bid=str(
                        context.get("lesson_outline_item_bid", "") or ""
                    ),
                    lesson_title=str(context.get("lesson_title", "") or ""),
                    score=int(getattr(row, "score", 0) or 0),
                    comment=str(getattr(row, "comment", "") or ""),
                    mode=_resolve_course_rating_mode(
                        str(getattr(row, "mode", "") or "")
                    ),
                    rated_at=getattr(row, "rated_at", None),
                )
            )

        if include_summary:
            summary = AdminOperationCourseRatingSummaryDTO(
                average_score=_format_average_score(
                    getattr(summary_row, "average_score", None)
                ),
                rating_count=total,
                user_count=int(getattr(summary_row, "user_count", 0) or 0),
                latest_rated_at=getattr(summary_row, "latest_rated_at", None),
            )
        else:
            summary = AdminOperationCourseRatingSummaryDTO()
        return AdminOperationCourseRatingListDTO(
            summary=summary,
            items=items,
            page=safe_page_index,
            page_size=safe_page_size,
            total=total,
            page_count=math.ceil(total / safe_page_size) if safe_page_size else 0,
        )
