from __future__ import annotations

from flaskr.service.learn.learn_dtos import ElementType
from flaskr.service.learn.listen_element_payloads import _deserialize_payload
from flaskr.service.learn.models import LearnGeneratedBlock, LearnGeneratedElement


def _load_latest_active_element_row(
    element_bid: str,
) -> LearnGeneratedElement | None:
    if not element_bid:
        return None
    return (
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.event_type == "element",
            LearnGeneratedElement.element_bid == element_bid,
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        )
        .order_by(
            LearnGeneratedElement.sequence_number.desc(),
            LearnGeneratedElement.run_event_seq.desc(),
            LearnGeneratedElement.id.desc(),
        )
        .first()
    )


def find_follow_up_element_rows(
    progress_record_bid: str,
    anchor_element_bid: str,
) -> list[LearnGeneratedElement]:
    if not progress_record_bid or not anchor_element_bid:
        return []
    rows = (
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.progress_record_bid == progress_record_bid,
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
    matched_rows: list[LearnGeneratedElement] = []
    for row in rows:
        payload = _deserialize_payload(row.payload or "")
        if (payload.anchor_element_bid or "") == anchor_element_bid:
            matched_rows.append(row)
    return matched_rows


def find_latest_ask_element_row(
    progress_record_bid: str,
    anchor_element_bid: str,
) -> LearnGeneratedElement | None:
    rows = find_follow_up_element_rows(progress_record_bid, anchor_element_bid)
    for row in reversed(rows):
        if str(row.element_type or "") == ElementType.ASK.value:
            return row
    return None


def find_latest_answer_element_row(
    progress_record_bid: str,
    anchor_element_bid: str,
) -> LearnGeneratedElement | None:
    if not progress_record_bid or not anchor_element_bid:
        return None
    rows = find_follow_up_element_rows(progress_record_bid, anchor_element_bid)
    for row in reversed(rows):
        if str(row.element_type or "") == ElementType.ANSWER.value:
            return row
    return None


def _load_interaction_user_input(generated_block_bid: str) -> str:
    if not generated_block_bid:
        return ""

    interaction_block = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid == generated_block_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
        )
        .order_by(LearnGeneratedBlock.id.desc())
        .first()
    )
    if interaction_block is None:
        return ""
    return str(interaction_block.generated_content or "")
