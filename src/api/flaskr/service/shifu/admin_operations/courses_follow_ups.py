"""Operator course follow-up (ask/answer) listing and detail views.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, Optional, Sequence, Set
from flask import Flask
from sqlalchemy import and_, or_
from flaskr.dao import db
from flaskr.service.learn.learn_dtos import ElementType
from flaskr.service.learn.listen_element_payloads import _deserialize_payload
from flaskr.service.learn.const import (
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
)
from flaskr.service.common.models import (
    raise_param_error,
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
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
)
from flaskr.service.user.models import (
    AuthCredential,
    UserInfo as UserEntity,
)

from flaskr.service.shifu.admin_operations.courses_shared import (
    COURSE_FOLLOW_UP_LIST_MAX_PAGE_SIZE,
    _build_course_outline_context_map,
    _load_operator_course_outline_items,
    _load_user_map,
    _normalize_identifier,
)


def _build_course_follow_up_base_subquery(shifu_bid: str):
    return (
        db.session.query(
            LearnGeneratedBlock.id.label("id"),
            LearnGeneratedBlock.generated_block_bid.label("generated_block_bid"),
            LearnGeneratedBlock.progress_record_bid.label("progress_record_bid"),
            LearnGeneratedBlock.user_bid.label("user_bid"),
            LearnGeneratedBlock.outline_item_bid.label("outline_item_bid"),
            LearnGeneratedBlock.generated_content.label("follow_up_content"),
            LearnGeneratedBlock.created_at.label("created_at"),
            db.func.row_number()
            .over(
                partition_by=LearnGeneratedBlock.progress_record_bid,
                order_by=(
                    LearnGeneratedBlock.created_at.asc(),
                    LearnGeneratedBlock.id.asc(),
                ),
            )
            .label("turn_index"),
        )
        .filter(
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.role == ROLE_STUDENT,
        )
        .subquery()
    )


def _build_follow_up_user_keyword_filter(
    user_bid_column: Any, keyword: str
) -> Any | None:
    normalized = _normalize_identifier(keyword)
    if not normalized:
        return None

    credential_match_exists = (
        db.session.query(AuthCredential.id)
        .filter(
            AuthCredential.user_bid == user_bid_column,
            AuthCredential.deleted == 0,
            AuthCredential.provider_name.in_(["phone", "email", "google"]),
            AuthCredential.identifier.ilike(f"%{normalized}%"),
        )
        .exists()
    )

    user_filters = [UserEntity.nickname.ilike(f"%{normalized}%")]
    if "@" in normalized or normalized.isdigit():
        user_filters.append(UserEntity.user_identify.ilike(f"%{normalized}%"))

    user_match_exists = (
        db.session.query(UserEntity.id)
        .filter(
            UserEntity.user_bid == user_bid_column,
            UserEntity.deleted == 0,
            or_(*user_filters),
        )
        .exists()
    )

    return or_(credential_match_exists, user_match_exists)


def _resolve_follow_up_matching_outline_bids(
    outline_context_map: Dict[str, Dict[str, str]],
    chapter_keyword: str,
) -> Optional[Set[str]]:
    normalized_keyword = str(chapter_keyword or "").strip().lower()
    if not normalized_keyword:
        return None

    return {
        outline_item_bid
        for outline_item_bid, context in outline_context_map.items()
        if normalized_keyword
        in str(context.get("chapter_title", "") or "").strip().lower()
        or normalized_keyword
        in str(context.get("lesson_title", "") or "").strip().lower()
    }


def _resolve_follow_up_answer_block(
    blocks: Sequence[LearnGeneratedBlock],
    index: int,
) -> LearnGeneratedBlock | None:
    ask_position = int(blocks[index].position or 0)
    for next_block in blocks[index + 1 :]:
        next_block_type = int(next_block.type or 0)
        next_block_role = int(next_block.role or 0)
        if (
            next_block_type == BLOCK_TYPE_MDASK_VALUE
            and next_block_role == ROLE_STUDENT
        ):
            return None
        if next_block_type == BLOCK_TYPE_MDANSWER_VALUE:
            return next_block
        if (
            next_block_type == BLOCK_TYPE_MDCONTENT_VALUE
            and next_block_role == ROLE_TEACHER
            and int(next_block.position or 0) == ask_position
        ):
            return next_block
    return None


def _resolve_follow_up_answer_content(block: LearnGeneratedBlock | None) -> str:
    if block is None:
        return ""

    generated_content = str(getattr(block, "generated_content", "") or "").strip()
    if generated_content:
        return generated_content

    return str(getattr(block, "block_content_conf", "") or "").strip()


def _load_follow_up_groups_for_progress_record(
    progress_record_bid: str,
) -> list[dict[str, Any]]:
    normalized_progress_record_bid = str(progress_record_bid or "").strip()
    if not normalized_progress_record_bid:
        return []

    blocks = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.progress_record_bid == normalized_progress_record_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            or_(
                and_(
                    LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
                    LearnGeneratedBlock.role == ROLE_STUDENT,
                ),
                LearnGeneratedBlock.type == BLOCK_TYPE_MDANSWER_VALUE,
                and_(
                    LearnGeneratedBlock.type == BLOCK_TYPE_MDCONTENT_VALUE,
                    LearnGeneratedBlock.role == ROLE_TEACHER,
                ),
            ),
        )
        .order_by(LearnGeneratedBlock.created_at.asc(), LearnGeneratedBlock.id.asc())
        .all()
    )
    groups: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        if (
            int(block.type or 0) != BLOCK_TYPE_MDASK_VALUE
            or int(block.role or 0) != ROLE_STUDENT
        ):
            continue
        answer_block = _resolve_follow_up_answer_block(blocks, index)
        groups.append(
            {
                "ask_block": block,
                "answer_block": answer_block,
            }
        )
    return groups


def _load_follow_up_groups_for_progress_records(
    progress_record_bids: Sequence[str],
) -> dict[str, list[dict[str, Any]]]:
    normalized_progress_record_bids = sorted(
        {
            str(progress_record_bid or "").strip()
            for progress_record_bid in progress_record_bids
            if str(progress_record_bid or "").strip()
        }
    )
    if not normalized_progress_record_bids:
        return {}

    blocks = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.progress_record_bid.in_(
                normalized_progress_record_bids
            ),
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            or_(
                and_(
                    LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
                    LearnGeneratedBlock.role == ROLE_STUDENT,
                ),
                LearnGeneratedBlock.type == BLOCK_TYPE_MDANSWER_VALUE,
                and_(
                    LearnGeneratedBlock.type == BLOCK_TYPE_MDCONTENT_VALUE,
                    LearnGeneratedBlock.role == ROLE_TEACHER,
                ),
            ),
        )
        .order_by(
            LearnGeneratedBlock.progress_record_bid.asc(),
            LearnGeneratedBlock.created_at.asc(),
            LearnGeneratedBlock.id.asc(),
        )
        .all()
    )
    blocks_by_progress_record: dict[str, list[LearnGeneratedBlock]] = {}
    for block in blocks:
        progress_record_bid = str(
            getattr(block, "progress_record_bid", "") or ""
        ).strip()
        if not progress_record_bid:
            continue
        blocks_by_progress_record.setdefault(progress_record_bid, []).append(block)

    groups_by_progress_record: dict[str, list[dict[str, Any]]] = {}
    for progress_record_bid, progress_blocks in blocks_by_progress_record.items():
        groups: list[dict[str, Any]] = []
        for index, block in enumerate(progress_blocks):
            if (
                int(block.type or 0) != BLOCK_TYPE_MDASK_VALUE
                or int(block.role or 0) != ROLE_STUDENT
            ):
                continue
            groups.append(
                {
                    "ask_block": block,
                    "answer_block": _resolve_follow_up_answer_block(
                        progress_blocks, index
                    ),
                }
            )
        groups_by_progress_record[progress_record_bid] = groups
    return groups_by_progress_record


def _resolve_follow_up_source_from_element(
    *,
    shifu_bid: str,
    user_bid: str,
    progress_record_bid: str,
    answer_generated_block_bid: str,
    fallback_position: int,
    ask_created_at: datetime | None,
) -> dict[str, Any]:
    normalized_answer_generated_block_bid = str(
        answer_generated_block_bid or ""
    ).strip()
    normalized_user_bid = str(user_bid or "").strip()
    normalized_shifu_bid = str(shifu_bid or "").strip()
    normalized_progress_record_bid = str(progress_record_bid or "").strip()
    if (
        not normalized_answer_generated_block_bid
        or not normalized_user_bid
        or not normalized_shifu_bid
        or not normalized_progress_record_bid
    ):
        return {}

    follow_up_elements = (
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.generated_block_bid
            == normalized_answer_generated_block_bid,
            LearnGeneratedElement.user_bid == normalized_user_bid,
            LearnGeneratedElement.shifu_bid == normalized_shifu_bid,
            LearnGeneratedElement.progress_record_bid == normalized_progress_record_bid,
            LearnGeneratedElement.event_type == "element",
            LearnGeneratedElement.element_type.in_(
                [ElementType.ASK.value, ElementType.ANSWER.value]
            ),
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        )
        .order_by(
            LearnGeneratedElement.sequence_number.asc(),
            LearnGeneratedElement.run_event_seq.asc(),
            LearnGeneratedElement.id.asc(),
        )
        .all()
    )
    if not follow_up_elements:
        return {}

    anchor_element_bid = ""
    for row in follow_up_elements:
        payload = _deserialize_payload(str(getattr(row, "payload", "") or ""))
        anchor_element_bid = str(
            getattr(payload, "anchor_element_bid", "") or ""
        ).strip()
        if anchor_element_bid:
            break
    if not anchor_element_bid:
        return {}

    anchor_query = LearnGeneratedElement.query.filter(
        LearnGeneratedElement.shifu_bid == normalized_shifu_bid,
        LearnGeneratedElement.user_bid == normalized_user_bid,
        LearnGeneratedElement.progress_record_bid == normalized_progress_record_bid,
        LearnGeneratedElement.event_type == "element",
        or_(
            LearnGeneratedElement.element_bid == anchor_element_bid,
            LearnGeneratedElement.target_element_bid == anchor_element_bid,
        ),
        LearnGeneratedElement.deleted == 0,
    )
    if ask_created_at is not None:
        anchor_query = anchor_query.filter(
            LearnGeneratedElement.created_at <= ask_created_at
        )
    anchor_element = anchor_query.order_by(
        LearnGeneratedElement.created_at.desc(),
        LearnGeneratedElement.sequence_number.desc(),
        LearnGeneratedElement.run_event_seq.desc(),
        LearnGeneratedElement.id.desc(),
    ).first()
    if anchor_element is None:
        return {
            "source_output_content": "",
            "source_output_type": "element",
            "source_position": int(fallback_position or 0),
            "source_element_bid": anchor_element_bid,
            "source_element_type": "",
        }

    return {
        "source_output_content": str(getattr(anchor_element, "content_text", "") or ""),
        "source_output_type": "element",
        "source_position": int(fallback_position or 0),
        "source_element_bid": anchor_element_bid,
        "source_element_type": str(getattr(anchor_element, "element_type", "") or ""),
    }


def _resolve_follow_up_source_from_blocks(
    ask_block: LearnGeneratedBlock,
) -> dict[str, Any]:
    progress_record_bid = str(
        getattr(ask_block, "progress_record_bid", "") or ""
    ).strip()
    if not progress_record_bid:
        return {}

    position = int(getattr(ask_block, "position", 0) or 0)
    query = LearnGeneratedBlock.query.filter(
        LearnGeneratedBlock.progress_record_bid == progress_record_bid,
        LearnGeneratedBlock.deleted == 0,
        LearnGeneratedBlock.role == ROLE_TEACHER,
        LearnGeneratedBlock.position == position,
        LearnGeneratedBlock.type.in_(
            [BLOCK_TYPE_MDINTERACTION_VALUE, BLOCK_TYPE_MDCONTENT_VALUE]
        ),
    )
    ask_created_at = getattr(ask_block, "created_at", None)
    ask_block_id = int(getattr(ask_block, "id", 0) or 0)
    if ask_created_at is not None and ask_block_id > 0:
        query = query.filter(
            or_(
                LearnGeneratedBlock.created_at < ask_created_at,
                and_(
                    LearnGeneratedBlock.created_at == ask_created_at,
                    LearnGeneratedBlock.id < ask_block_id,
                ),
            )
        )
    elif ask_block_id > 0:
        query = query.filter(LearnGeneratedBlock.id < ask_block_id)

    source_block = query.order_by(
        LearnGeneratedBlock.created_at.desc(),
        LearnGeneratedBlock.id.desc(),
    ).first()
    if source_block is None:
        return {}

    source_type = (
        "interaction"
        if int(getattr(source_block, "type", 0) or 0) == BLOCK_TYPE_MDINTERACTION_VALUE
        else "content"
    )
    if source_type == "interaction":
        source_content = str(
            getattr(source_block, "block_content_conf", "") or ""
        ).strip()
        if not source_content:
            source_content = str(getattr(source_block, "generated_content", "") or "")
    else:
        source_content = str(
            getattr(source_block, "generated_content", "") or ""
        ).strip()
        if not source_content:
            source_content = str(getattr(source_block, "block_content_conf", "") or "")

    return {
        "source_output_content": source_content,
        "source_output_type": source_type,
        "source_position": int(getattr(source_block, "position", 0) or 0),
        "source_element_bid": "",
        "source_element_type": "",
    }


def _resolve_follow_up_source(
    *,
    ask_block: LearnGeneratedBlock,
    answer_block: LearnGeneratedBlock | None,
) -> dict[str, Any]:
    fallback_position = int(getattr(ask_block, "position", 0) or 0)
    if answer_block is not None:
        source = _resolve_follow_up_source_from_element(
            shifu_bid=str(getattr(ask_block, "shifu_bid", "") or ""),
            user_bid=str(getattr(ask_block, "user_bid", "") or ""),
            progress_record_bid=str(
                getattr(ask_block, "progress_record_bid", "") or ""
            ),
            answer_generated_block_bid=str(
                getattr(answer_block, "generated_block_bid", "") or ""
            ),
            fallback_position=fallback_position,
            ask_created_at=getattr(ask_block, "created_at", None),
        )
        if source:
            return source

    source = _resolve_follow_up_source_from_blocks(ask_block)
    if source:
        return source

    return {
        "source_output_content": "",
        "source_output_type": "",
        "source_position": fallback_position,
        "source_element_bid": "",
        "source_element_type": "",
    }


def _build_follow_up_source_status_map(
    *,
    shifu_bid: str,
    generated_block_bids: list[str],
) -> dict[str, bool]:
    normalized_generated_block_bids = sorted(
        {
            str(generated_block_bid or "").strip()
            for generated_block_bid in generated_block_bids
            if str(generated_block_bid or "").strip()
        }
    )
    if not normalized_generated_block_bids:
        return {}

    ask_blocks = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.generated_block_bid.in_(
                normalized_generated_block_bids
            ),
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDASK_VALUE,
            LearnGeneratedBlock.role == ROLE_STUDENT,
        )
        .order_by(LearnGeneratedBlock.id.asc())
        .all()
    )
    if not ask_blocks:
        return {}

    groups_cache = _load_follow_up_groups_for_progress_records(
        [
            str(getattr(ask_block, "progress_record_bid", "") or "")
            for ask_block in ask_blocks
        ]
    )
    answer_block_map: dict[str, LearnGeneratedBlock | None] = {}
    for groups in groups_cache.values():
        for group in groups:
            group_ask_block = group.get("ask_block")
            group_generated_block_bid = str(
                getattr(group_ask_block, "generated_block_bid", "") or ""
            ).strip()
            if not group_generated_block_bid:
                continue
            answer_block_map[group_generated_block_bid] = group.get("answer_block")
    source_status_map: dict[str, bool] = {}

    for ask_block in ask_blocks:
        generated_block_bid = str(
            getattr(ask_block, "generated_block_bid", "") or ""
        ).strip()
        if not generated_block_bid:
            continue

        source_info = _resolve_follow_up_source(
            ask_block=ask_block,
            answer_block=answer_block_map.get(generated_block_bid),
        )
        source_status_map[generated_block_bid] = bool(
            str(source_info.get("source_output_content", "") or "").strip()
        )

    return source_status_map


def get_operator_course_follow_ups(
    app: Flask,
    *,
    shifu_bid: str,
    page_index: int,
    page_size: int,
    filters: Optional[dict] = None,
    include_summary: bool = True,
) -> AdminOperationCourseFollowUpListDTO:
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
        follow_up_base = _build_course_follow_up_base_subquery(normalized_shifu_bid)
        user_keyword_filter = _build_follow_up_user_keyword_filter(
            follow_up_base.c.user_bid,
            keyword,
        )
        matching_outline_item_bids = _resolve_follow_up_matching_outline_bids(
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
            filtered_source_status_map = _build_follow_up_source_status_map(
                shifu_bid=normalized_shifu_bid,
                generated_block_bids=[
                    str(getattr(row, "generated_block_bid", "") or "")
                    for row in filtered_rows
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
            source_status_map = _build_follow_up_source_status_map(
                shifu_bid=normalized_shifu_bid,
                generated_block_bids=[
                    str(getattr(row, "generated_block_bid", "") or "")
                    for row in paged_rows
                ],
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
            answer_content = _resolve_follow_up_answer_content(answer_block)
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
        source_info = _resolve_follow_up_source(
            ask_block=ask_block,
            answer_block=selected_answer_block,
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
                answer_content=_resolve_follow_up_answer_content(selected_answer_block),
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
