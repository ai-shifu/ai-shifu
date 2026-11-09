"""Query persisted listen-mode element state."""

from __future__ import annotations

from flaskr.service.learn.elements.payloads import _deserialize_payload
from flaskr.service.learn.learn_dtos import ElementType
from flaskr.service.learn.models import LearnGeneratedBlock, LearnGeneratedElement
from sqlalchemy import or_


def _load_latest_active_element_row(
    element_bid: str,
) -> LearnGeneratedElement | None:
    if not element_bid:
        return None
    return (
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.event_type == "element",
            or_(
                LearnGeneratedElement.element_bid == element_bid,
                LearnGeneratedElement.target_element_bid == element_bid,
            ),
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


def _repeated_anchor_aliases(anchor: LearnGeneratedElement) -> dict[str, str]:
    if anchor.element_type != ElementType.INTERACTION.value:
        return {}

    from flaskr.service.learn.elements.history import (
        _load_interaction_user_input_by_block_bid,
    )

    controls = LearnGeneratedElement.query.filter_by(
        progress_record_bid=anchor.progress_record_bid,
        user_bid=anchor.user_bid,
        shifu_bid=anchor.shifu_bid,
        outline_item_bid=anchor.outline_item_bid,
        event_type="element",
        element_type=ElementType.INTERACTION.value,
        deleted=0,
        status=1,
    ).all()
    aliases_by_progress: dict[str, dict[str, str]] = {}
    _load_interaction_user_input_by_block_bid(
        controls, repeated_controls=aliases_by_progress
    )
    return aliases_by_progress.get(anchor.progress_record_bid, {})


def find_follow_up_element_rows(
    progress_record_bid: str,
    anchor_element_bid: str,
) -> list[LearnGeneratedElement]:
    """Read anchor sidecars in turn order, not run-local generation order."""
    if not progress_record_bid or not anchor_element_bid:
        return []
    anchor = _load_latest_active_element_row(anchor_element_bid)
    if anchor is None or anchor.progress_record_bid != progress_record_bid:
        return []
    rows = (
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.progress_record_bid == progress_record_bid,
            LearnGeneratedElement.user_bid == anchor.user_bid,
            LearnGeneratedElement.shifu_bid == anchor.shifu_bid,
            LearnGeneratedElement.outline_item_bid == anchor.outline_item_bid,
            LearnGeneratedElement.event_type == "element",
            LearnGeneratedElement.element_type.in_(
                [ElementType.ASK.value, ElementType.ANSWER.value]
            ),
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        )
        .order_by(LearnGeneratedElement.id.asc())
        .all()
    )
    payloads = {row.id: _deserialize_payload(row.payload or "") for row in rows}
    aliases = (
        _repeated_anchor_aliases(anchor)
        if any(
            payload.anchor_element_bid != anchor_element_bid
            for payload in payloads.values()
        )
        else {}
    )
    original_anchor = aliases.get(anchor_element_bid, anchor_element_bid)
    matched_rows = [
        row
        for row in rows
        if aliases.get(
            payloads[row.id].anchor_element_bid, payloads[row.id].anchor_element_bid
        )
        == original_anchor
    ]
    ask_order = {
        row.element_bid: row.id
        for row in matched_rows
        if row.element_type == ElementType.ASK.value
    }
    # Each new request restarts run-local counters. Bind answer snapshots to
    # their original question so a late patch cannot move an old turn forward.
    matched_rows.sort(
        key=lambda row: (
            ask_order.get(payloads[row.id].ask_element_bid, row.id)
            if row.element_type == ElementType.ANSWER.value
            else row.id,
            row.sequence_number or 0,
            row.run_event_seq or 0,
            row.id,
        )
    )
    return matched_rows


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
