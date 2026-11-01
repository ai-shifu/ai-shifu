"""Operator course follow-up (ask/answer) listing and detail views.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.common.models import (
    raise_param_error,
)
from flaskr.service.learn.api import (
    build_course_follow_up_base_subquery,
    build_follow_up_source_status_map,
    build_follow_up_user_keyword_filter,
    load_follow_up_groups_for_progress_record,
    resolve_follow_up_answer_content,
    resolve_follow_up_matching_outline_bids,
    resolve_follow_up_source,
)
from flaskr.service.learn.const import (
    ROLE_STUDENT,
)
from flaskr.service.learn.elements.payloads import _deserialize_payload
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
)
from flaskr.service.shifu.admin_dtos_courses import (
    AdminOperationCourseFollowUpCurrentRecordDTO,
    AdminOperationCourseFollowUpDetailBasicInfoDTO,
    AdminOperationCourseFollowUpDetailDTO,
    AdminOperationCourseFollowUpItemDTO,
    AdminOperationCourseFollowUpListDTO,
    AdminOperationCourseFollowUpSummaryDTO,
    AdminOperationCourseFollowUpTimelineItemDTO,
)
from flaskr.service.shifu.admin_operations.courses_shared import (
    COURSE_FOLLOW_UP_LIST_MAX_PAGE_SIZE,
    _build_course_outline_context_map,
    _load_operator_course_outline_items,
    _load_user_map,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDASK_VALUE,
)

if TYPE_CHECKING:
    from flask import Flask


def _extract_anchor_element_bid_from_payload(raw_payload: str) -> str:
    """Read the anchor bid through the full element payload deserializer.

    Operator views keep parsing the whole payload, so a payload whose other
    fields fail validation still raises here, as it did before the shared
    follow-up loaders were extracted.
    """
    payload = _deserialize_payload(raw_payload)
    return str(getattr(payload, "anchor_element_bid", "") or "").strip()


def get_operator_course_follow_ups(
    app: Flask,
    *,
    shifu_bid: str,
    page_index: int,
    page_size: int,
    filters: dict | None = None,
    include_summary: bool = True,
) -> AdminOperationCourseFollowUpListDTO:
    """Return operator course follow ups."""
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")

        safe_page_index = max(int(page_index or 1), 1)
        safe_page_size = min(
            max(int(page_size or 20), 1),
            COURSE_FOLLOW_UP_LIST_MAX_PAGE_SIZE,
        )
        filters = filters or {}

        _detail_source, outline_items = _load_operator_course_outline_items(
            normalized_shifu_bid
        )
        outline_context_map = _build_course_outline_context_map(outline_items)

        keyword = str(filters.get("keyword", "") or "").strip()
        chapter_keyword = str(filters.get("chapter_keyword", "") or "").strip().lower()
        source_status = str(filters.get("source_status", "") or "").strip().lower()
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")
        if source_status not in {"", "resolved", "missing"}:
            raise_param_error("source_status")
        follow_up_base = build_course_follow_up_base_subquery(normalized_shifu_bid)
        user_keyword_filter = build_follow_up_user_keyword_filter(
            follow_up_base.c.user_bid,
            keyword,
        )
        matching_outline_item_bids = resolve_follow_up_matching_outline_bids(
            outline_context_map,
            chapter_keyword,
        )

        if chapter_keyword and not matching_outline_item_bids:
            return AdminOperationCourseFollowUpListDTO(
                summary=AdminOperationCourseFollowUpSummaryDTO(
                    follow_up_count=0,
                    user_count=0,
                    lesson_count=0,
                    latest_follow_up_at=None,
                ),
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )

        filtered_query = db.session.query(follow_up_base)
        if user_keyword_filter is not None:
            filtered_query = filtered_query.filter(user_keyword_filter)
        if matching_outline_item_bids is not None:
            filtered_query = filtered_query.filter(
                follow_up_base.c.outline_item_bid.in_(
                    sorted(matching_outline_item_bids)
                )
            )
        if start_time:
            filtered_query = filtered_query.filter(
                follow_up_base.c.created_at >= start_time
            )
        if end_time:
            filtered_query = filtered_query.filter(
                follow_up_base.c.created_at <= end_time
            )

        summary_row = None
        filtered_source_status_map: dict[str, bool] | None = None
        if source_status:
            filtered_rows = filtered_query.order_by(
                follow_up_base.c.created_at.desc(),
                follow_up_base.c.id.desc(),
            ).all()
            filtered_source_status_map = build_follow_up_source_status_map(
                shifu_bid=normalized_shifu_bid,
                generated_block_bids=[
                    str(getattr(row, "generated_block_bid", "") or "")
                    for row in filtered_rows
                ],
                anchor_element_bid_extractor=_extract_anchor_element_bid_from_payload,
            )
            filtered_rows = [
                row
                for row in filtered_rows
                if filtered_source_status_map.get(
                    str(getattr(row, "generated_block_bid", "") or "").strip(), False
                )
                == (source_status == "resolved")
            ]
            total = len(filtered_rows)
            if include_summary:
                unique_user_bids = {
                    str(getattr(row, "user_bid", "") or "").strip()
                    for row in filtered_rows
                    if str(getattr(row, "user_bid", "") or "").strip()
                }
                unique_outline_item_bids = {
                    str(getattr(row, "outline_item_bid", "") or "").strip()
                    for row in filtered_rows
                    if str(getattr(row, "outline_item_bid", "") or "").strip()
                }
                latest_follow_up_at = max(
                    (
                        getattr(row, "created_at", None)
                        for row in filtered_rows
                        if getattr(row, "created_at", None) is not None
                    ),
                    default=None,
                )
                summary = AdminOperationCourseFollowUpSummaryDTO(
                    follow_up_count=total,
                    user_count=len(unique_user_bids),
                    lesson_count=len(unique_outline_item_bids),
                    latest_follow_up_at=latest_follow_up_at,
                )
            else:
                summary = AdminOperationCourseFollowUpSummaryDTO(follow_up_count=total)
        else:
            filtered_follow_ups = filtered_query.subquery()
            if include_summary:
                summary_row = db.session.query(
                    db.func.count(filtered_follow_ups.c.id).label("follow_up_count"),
                    db.func.count(
                        db.func.distinct(
                            db.func.nullif(filtered_follow_ups.c.user_bid, "")
                        )
                    ).label("user_count"),
                    db.func.count(
                        db.func.distinct(
                            db.func.nullif(filtered_follow_ups.c.outline_item_bid, "")
                        )
                    ).label("lesson_count"),
                    db.func.max(filtered_follow_ups.c.created_at).label(
                        "latest_follow_up_at"
                    ),
                ).one()
                total = int(getattr(summary_row, "follow_up_count", 0) or 0)
            else:
                total = int(
                    db.session.query(db.func.count(filtered_follow_ups.c.id)).scalar()
                    or 0
                )

        if total == 0:
            return AdminOperationCourseFollowUpListDTO(
                summary=AdminOperationCourseFollowUpSummaryDTO(),
                items=[],
                page=safe_page_index,
                page_size=safe_page_size,
                total=0,
                page_count=0,
            )

        start = (safe_page_index - 1) * safe_page_size
        if source_status:
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
        user_map = _load_user_map(
            sorted(
                {
                    str(getattr(row, "user_bid", "") or "").strip()
                    for row in paged_rows
                    if str(getattr(row, "user_bid", "") or "").strip()
                }
            )
        )
        if source_status and filtered_source_status_map is not None:
            source_status_map = filtered_source_status_map
        else:
            source_status_map = build_follow_up_source_status_map(
                shifu_bid=normalized_shifu_bid,
                generated_block_bids=[
                    str(getattr(row, "generated_block_bid", "") or "")
                    for row in paged_rows
                ],
                anchor_element_bid_extractor=_extract_anchor_element_bid_from_payload,
            )

        items: list[AdminOperationCourseFollowUpItemDTO] = []
        for row in paged_rows:
            generated_block_bid = str(
                getattr(row, "generated_block_bid", "") or ""
            ).strip()
            outline_item_bid = str(getattr(row, "outline_item_bid", "") or "").strip()
            user_bid = str(getattr(row, "user_bid", "") or "").strip()
            created_at = getattr(row, "created_at", None)
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
                AdminOperationCourseFollowUpItemDTO(
                    generated_block_bid=generated_block_bid,
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
                    follow_up_content=str(getattr(row, "follow_up_content", "") or ""),
                    has_source_output=bool(
                        source_status_map.get(generated_block_bid, False)
                    ),
                    turn_index=int(getattr(row, "turn_index", 0) or 0),
                    created_at=created_at,
                )
            )
        if not source_status and include_summary:
            summary = AdminOperationCourseFollowUpSummaryDTO(
                follow_up_count=total,
                user_count=int(getattr(summary_row, "user_count", 0) or 0),
                lesson_count=int(getattr(summary_row, "lesson_count", 0) or 0),
                latest_follow_up_at=getattr(summary_row, "latest_follow_up_at", None),
            )
        elif not source_status:
            summary = AdminOperationCourseFollowUpSummaryDTO(follow_up_count=total)
        return AdminOperationCourseFollowUpListDTO(
            summary=summary,
            items=items,
            page=safe_page_index,
            page_size=safe_page_size,
            total=total,
            page_count=math.ceil(total / safe_page_size) if safe_page_size else 0,
        )


def get_operator_course_follow_up_detail(
    app: Flask,
    *,
    shifu_bid: str,
    generated_block_bid: str,
) -> AdminOperationCourseFollowUpDetailDTO:
    """Return operator course follow up detail."""
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_generated_block_bid = str(generated_block_bid or "").strip()
        if not normalized_shifu_bid:
            raise_param_error("shifu_bid is required")
        if not normalized_generated_block_bid:
            raise_param_error("generated_block_bid is required")

        detail_source, outline_items = _load_operator_course_outline_items(
            normalized_shifu_bid
        )
        course = detail_source["course"]
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
        groups = load_follow_up_groups_for_progress_record(progress_record_bid)
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
        user_map = _load_user_map([str(ask_block.user_bid or "").strip()])
        user = user_map.get(str(ask_block.user_bid or "").strip(), {})
        context = outline_context_map.get(
            str(ask_block.outline_item_bid or "").strip(),
            {
                "chapter_title": "",
                "lesson_title": "",
            },
        )

        timeline: list[AdminOperationCourseFollowUpTimelineItemDTO] = []
        for index, group in enumerate(groups):
            current_ask_block = group["ask_block"]
            is_current = index == selected_group_index
            timeline.append(
                AdminOperationCourseFollowUpTimelineItemDTO(
                    role="student",
                    content=str(
                        getattr(current_ask_block, "generated_content", "") or ""
                    ),
                    created_at=getattr(current_ask_block, "created_at", None),
                    is_current=is_current,
                )
            )
            answer_block = group.get("answer_block")
            answer_content = resolve_follow_up_answer_content(answer_block)
            if answer_content:
                timeline.append(
                    AdminOperationCourseFollowUpTimelineItemDTO(
                        role="teacher",
                        content=answer_content,
                        created_at=getattr(answer_block, "created_at", None),
                        is_current=is_current,
                    )
                )

        selected_answer_block = selected_group.get("answer_block")
        source_info = resolve_follow_up_source(
            ask_block=ask_block,
            answer_block=selected_answer_block,
            anchor_element_bid_extractor=_extract_anchor_element_bid_from_payload,
        )
        return AdminOperationCourseFollowUpDetailDTO(
            basic_info=AdminOperationCourseFollowUpDetailBasicInfoDTO(
                generated_block_bid=normalized_generated_block_bid,
                progress_record_bid=progress_record_bid,
                user_bid=str(ask_block.user_bid or ""),
                mobile=str(user.get("mobile", "") or ""),
                email=str(user.get("email", "") or ""),
                nickname=str(user.get("nickname", "") or ""),
                course_name=str(getattr(course, "title", "") or ""),
                shifu_bid=normalized_shifu_bid,
                chapter_title=str(context.get("chapter_title", "") or ""),
                lesson_title=str(context.get("lesson_title", "") or ""),
                created_at=getattr(ask_block, "created_at", None),
                turn_index=selected_group_index + 1,
            ),
            current_record=AdminOperationCourseFollowUpCurrentRecordDTO(
                follow_up_content=str(
                    getattr(ask_block, "generated_content", "") or ""
                ),
                answer_content=resolve_follow_up_answer_content(selected_answer_block),
                source_output_content=str(
                    source_info.get("source_output_content", "") or ""
                ),
                source_output_type=str(source_info.get("source_output_type", "") or ""),
                source_position=int(source_info.get("source_position", 0) or 0),
                source_element_bid=str(source_info.get("source_element_bid", "") or ""),
                source_element_type=str(
                    source_info.get("source_element_type", "") or ""
                ),
            ),
            timeline=timeline,
        )
