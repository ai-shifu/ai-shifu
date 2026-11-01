"""Course-level follow-up and learning-progress loaders for reporting views.

The teacher dashboard and the operator admin console both report on the same
learner follow-up (ask/answer) records and per-learner lesson progress. These
query helpers are the single implementation both surfaces share; each caller
keeps its own permission checks, filters, pagination and DTO mapping.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.learn.const import (
    LEARN_STATUS_RESET,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
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
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.sql.selectable import Subquery

FOLLOW_UP_ELEMENT_TYPE_ASK = "ask"
FOLLOW_UP_ELEMENT_TYPE_ANSWER = "answer"


def _normalize_identifier(value: str) -> str:
    normalized = str(value or "").strip()
    if "@" in normalized:
        return normalized.lower()
    return normalized


def extract_anchor_element_bid(raw_payload: str) -> str:
    """Return the ``anchor_element_bid`` stored in a raw element payload.

    Malformed or non-object payloads yield an empty string.
    """
    if not raw_payload:
        return ""
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("anchor_element_bid", "") or "").strip()


def build_course_follow_up_base_subquery(shifu_bid: str) -> Subquery:
    """Build the subquery of active learner follow-up asks for one course."""
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


def build_follow_up_user_keyword_filter(
    user_bid_column: object,
    keyword: str,
) -> ColumnElement[bool] | None:
    """Build a learner nickname/contact keyword filter, or None for a blank keyword."""
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


def resolve_follow_up_matching_outline_bids(
    outline_context_map: dict[str, dict[str, str]],
    chapter_keyword: str,
) -> set[str] | None:
    """Return outline bids whose chapter or lesson title matches the keyword."""
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


def resolve_follow_up_answer_block(
    blocks: Sequence[LearnGeneratedBlock],
    index: int,
) -> LearnGeneratedBlock | None:
    """Return the answer block that follows the ask at ``index``, if any."""
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


def resolve_follow_up_answer_content(block: LearnGeneratedBlock | None) -> str:
    """Return the rendered answer text of an answer block."""
    if block is None:
        return ""

    generated_content = str(getattr(block, "generated_content", "") or "").strip()
    if generated_content:
        return generated_content

    return str(getattr(block, "block_content_conf", "") or "").strip()


def load_follow_up_groups_for_progress_record(
    progress_record_bid: str,
) -> list[dict[str, LearnGeneratedBlock | None]]:
    """Load ask/answer block groups for one progress record in creation order."""
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
                "answer_block": resolve_follow_up_answer_block(blocks, index),
            }
        )
    return groups


def load_follow_up_groups_for_progress_records(
    progress_record_bids: Sequence[str],
) -> dict[str, list[dict[str, LearnGeneratedBlock | None]]]:
    """Load ask/answer block groups for several progress records at once."""
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
                    "answer_block": resolve_follow_up_answer_block(
                        progress_blocks, index
                    ),
                }
            )
        groups_by_progress_record[progress_record_bid] = groups
    return groups_by_progress_record


def resolve_follow_up_source_from_element(
    *,
    shifu_bid: str,
    user_bid: str,
    progress_record_bid: str,
    answer_generated_block_bid: str,
    fallback_position: int,
    ask_created_at: datetime | None,
    anchor_element_bid_extractor: Callable[[str], str] = extract_anchor_element_bid,
) -> dict[str, object]:
    """Resolve the element a follow-up ask was anchored to.

    ``anchor_element_bid_extractor`` reads the anchor bid from a raw element
    payload; callers that need stricter payload parsing can supply their own.
    """
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
        anchor_element_bid = anchor_element_bid_extractor(
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


def resolve_follow_up_source_from_blocks(
    ask_block: LearnGeneratedBlock,
) -> dict[str, object]:
    """Resolve the teacher block a follow-up ask was raised against."""
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


def resolve_follow_up_source(
    *,
    ask_block: LearnGeneratedBlock,
    answer_block: LearnGeneratedBlock | None,
    anchor_element_bid_extractor: Callable[[str], str] = extract_anchor_element_bid,
) -> dict[str, object]:
    """Resolve the source output of a follow-up from elements, then blocks."""
    fallback_position = int(getattr(ask_block, "position", 0) or 0)
    if answer_block is not None:
        source = resolve_follow_up_source_from_element(
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
            anchor_element_bid_extractor=anchor_element_bid_extractor,
        )
        if source:
            return source

    source = resolve_follow_up_source_from_blocks(ask_block)
    if source:
        return source

    return {
        "source_output_content": "",
        "source_output_type": "",
        "source_position": fallback_position,
        "source_element_bid": "",
        "source_element_type": "",
    }


def build_follow_up_source_status_map(
    *,
    shifu_bid: str,
    generated_block_bids: list[str],
    anchor_element_bid_extractor: Callable[[str], str] = extract_anchor_element_bid,
) -> dict[str, bool]:
    """Map each follow-up ask bid to whether its source output is resolvable."""
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

    groups_cache = load_follow_up_groups_for_progress_records(
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

        source_info = resolve_follow_up_source(
            ask_block=ask_block,
            answer_block=answer_block_map.get(generated_block_bid),
            anchor_element_bid_extractor=anchor_element_bid_extractor,
        )
        source_status_map[generated_block_bid] = bool(
            str(source_info.get("source_output_content", "") or "").strip()
        )

    return source_status_map


def load_course_learned_lesson_count_map(
    shifu_bid: str,
    user_bids: Sequence[str],
    leaf_outline_bids: Sequence[str],
) -> dict[str, int]:
    """Count distinct non-reset leaf lessons each learner has progress on."""
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    normalized_leaf_outline_bids = [
        str(outline_item_bid or "").strip()
        for outline_item_bid in leaf_outline_bids
        if str(outline_item_bid or "").strip()
    ]
    if not normalized_user_bids or not normalized_leaf_outline_bids:
        return {}

    rows = (
        db.session.query(
            LearnProgressRecord.user_bid,
            db.func.count(db.func.distinct(LearnProgressRecord.outline_item_bid)).label(
                "learned_lesson_count"
            ),
        )
        .filter(
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.user_bid.in_(normalized_user_bids),
            LearnProgressRecord.outline_item_bid.in_(normalized_leaf_outline_bids),
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .group_by(LearnProgressRecord.user_bid)
        .all()
    )
    return {
        str(user_bid or "").strip(): int(learned_lesson_count or 0)
        for user_bid, learned_lesson_count in rows
        if str(user_bid or "").strip()
    }
