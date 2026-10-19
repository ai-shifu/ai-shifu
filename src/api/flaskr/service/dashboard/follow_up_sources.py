"""Resolve follow-up turns, answers, and source outputs for dashboard reporting."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.dashboard.common import (
    FOLLOW_UP_ELEMENT_TYPE_ANSWER,
    FOLLOW_UP_ELEMENT_TYPE_ASK,
    _normalize_dashboard_identifier,
)
from flaskr.service.learn.const import ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity
from sqlalchemy import and_, or_

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.sql.selectable import Subquery


def _build_course_follow_up_base_subquery(shifu_bid: str) -> Subquery:
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
    user_bid_column: object,
    keyword: str,
) -> ColumnElement[bool] | None:
    normalized = _normalize_dashboard_identifier(keyword)
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
    outline_context_map: dict[str, dict[str, str]],
    chapter_keyword: str,
) -> set[str] | None:
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
) -> list[dict[str, LearnGeneratedBlock | None]]:
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
    groups: list[dict[str, LearnGeneratedBlock | None]] = []
    for index, block in enumerate(blocks):
        if (
            int(block.type or 0) != BLOCK_TYPE_MDASK_VALUE
            or int(block.role or 0) != ROLE_STUDENT
        ):
            continue
        groups.append(
            {
                "ask_block": block,
                "answer_block": _resolve_follow_up_answer_block(blocks, index),
            }
        )
    return groups


def _load_follow_up_groups_for_progress_records(
    progress_record_bids: Sequence[str],
) -> dict[str, list[dict[str, LearnGeneratedBlock | None]]]:
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

    groups_by_progress_record: dict[
        str, list[dict[str, LearnGeneratedBlock | None]]
    ] = {}
    for progress_record_bid, progress_blocks in blocks_by_progress_record.items():
        groups: list[dict[str, LearnGeneratedBlock | None]] = []
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
) -> dict[str, object]:
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
                [FOLLOW_UP_ELEMENT_TYPE_ASK, FOLLOW_UP_ELEMENT_TYPE_ANSWER]
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
        anchor_element_bid = _extract_anchor_element_bid(
            str(getattr(row, "payload", "") or "")
        )
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
) -> dict[str, object]:
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
) -> dict[str, object]:
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


def _extract_anchor_element_bid(raw_payload: str) -> str:
    if not raw_payload:
        return ""
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("anchor_element_bid", "") or "").strip()


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
