"""Plan and retire only the active draft's superseded teaching turns."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from flaskr.service.learn.agent.engine import Session
from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
from flaskr.service.learn.agent.rewind import (
    RewindPlan,
    RewindUnavailableError,
    restore,
)
from flaskr.service.learn.agent.session_store import (
    PREVIEW_PRESENTATION_KEY,
    PreviewGenerationDiscardedError,
    StoredSessionUnusable,
    load_agent_session,
    preview_presentation,
)
from flaskr.service.learn.learn_dtos import ElementType
from flaskr.service.learn.listen_element_history import _build_final_elements_from_rows
from flaskr.service.learn.models import LearnGeneratedElement

if TYPE_CHECKING:
    from flask import Flask


@dataclass
class PreviewRewindPlan(RewindPlan):
    """Bind a restored turn and its retirement to one unchanged draft generation."""

    generation: str = ""
    source_blocks: list[str] = field(default_factory=list)


def plan_preview_rewind(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    anchor: str,
    answering: bool,
) -> PreviewRewindPlan | None:
    """Restore an owned question's accepting turn, or a content turn's original input.

    Block anchors remain compatible for single questions. Exact element anchors distinguish
    several questions in one block. An unanswered first pending question needs no rewind.
    """
    row = LearnAgentSession.query.filter_by(
        active_key=active_key_for(user_bid, outline_bid, preview_mode=True),
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        deleted=0,
    ).first()
    presentation = preview_presentation(row)
    if not presentation:
        raise RewindUnavailableError
    try:
        session = load_agent_session(app, user_bid, outline_bid, preview_mode=True)
    except StoredSessionUnusable as exc:
        raise RewindUnavailableError from exc
    if session is None:
        raise RewindUnavailableError
    owned = LearnGeneratedElement.query.filter(
        LearnGeneratedElement.user_bid == user_bid,
        LearnGeneratedElement.shifu_bid == shifu_bid,
        LearnGeneratedElement.outline_item_bid == outline_bid,
        LearnGeneratedElement.run_session_bid.in_(presentation["runs"]),
        LearnGeneratedElement.status == 1,
        LearnGeneratedElement.deleted == 0,
    )
    element = owned.filter(LearnGeneratedElement.element_bid == anchor).first()
    block_bid = element.generated_block_bid if element else anchor
    block_rows = owned.filter(
        LearnGeneratedElement.generated_block_bid == block_bid
    ).all()
    if not block_rows:
        raise RewindUnavailableError
    question_id = None
    if answering:
        controls, _events = _build_final_elements_from_rows(
            block_rows,
            interaction_user_input_by_block_bid={},
        )
        controls = [e for e in controls if e.element_type == ElementType.INTERACTION]
        ids = presentation["questions"].get(block_bid, [])
        ids = [ids] if isinstance(ids, str) else ids
        if element:
            offset = next(
                (i for i, e in enumerate(controls) if e.element_bid == anchor), None
            )
        else:
            offset = 0 if len(controls) == 1 else None
        if offset is None or offset >= len(ids):
            raise RewindUnavailableError
        question_id = ids[offset]
        if (
            session.pending
            and session.pending[0].tool_call_id == question_id
            and question_id not in session.answers
        ):
            return None
    turns = presentation.get("turns", [])
    if not isinstance(turns, list) or any(
        not isinstance(turn, dict)
        or not isinstance(turn.get("block_bid"), str)
        or not isinstance(turn.get("record"), dict)
        for turn in turns
    ):
        raise RewindUnavailableError
    target = next(
        (
            i
            for i, turn in enumerate(turns)
            if (
                turn.get("answered_question_id") == question_id
                if answering
                else turn.get("block_bid") == block_bid
            )
        ),
        None,
    )
    if target is None:
        raise RewindUnavailableError
    record = turns[target].get("record", {})
    checkpoint = record.get("checkpoint")
    if (
        record.get("version") != 1
        or not isinstance(checkpoint, dict)
        or not {"messages", "memory", "pending", "answers", "turn", "finished"}
        <= checkpoint.keys()
        or not isinstance(checkpoint["messages"], int)
        or not 0 <= checkpoint["messages"] <= len(session.messages)
    ):
        raise RewindUnavailableError
    if not isinstance(checkpoint["pending"], list) or any(
        not isinstance(question, dict) for question in checkpoint["pending"]
    ):
        raise RewindUnavailableError
    try:
        restore(Session.from_dict(session.to_dict()), checkpoint)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise RewindUnavailableError from exc
    values = record.get("values")
    if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
        raise RewindUnavailableError
    if answering and (
        not checkpoint["pending"]
        or checkpoint["pending"][0].get("tool_call_id") != question_id
    ):
        raise RewindUnavailableError
    return PreviewRewindPlan(
        checkpoint=checkpoint,
        replay_values=None if answering else list(values),
        retired_block_bids=[turn["block_bid"] for turn in turns[target:]],
        generation=row.agent_session_bid,
        source_blocks=[turn["block_bid"] for turn in turns],
    )


def stage_preview_retirement(
    plan: PreviewRewindPlan,
    *,
    generation: str,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
) -> None:
    """Retire the suffix with its session save, after that save locks the generation."""
    if generation != plan.generation:
        raise PreviewGenerationDiscardedError
    row = LearnAgentSession.query.filter_by(
        agent_session_bid=generation,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        deleted=0,
        active_key=active_key_for(user_bid, outline_bid, preview_mode=True),
    ).one()
    presentation = preview_presentation(row)
    if [
        turn["block_bid"] for turn in presentation.get("turns", [])
    ] != plan.source_blocks:
        raise PreviewGenerationDiscardedError
    retired = set(plan.retired_block_bids)
    LearnGeneratedElement.query.filter(
        LearnGeneratedElement.user_bid == user_bid,
        LearnGeneratedElement.shifu_bid == shifu_bid,
        LearnGeneratedElement.outline_item_bid == outline_bid,
        LearnGeneratedElement.run_session_bid.in_(presentation["runs"]),
        LearnGeneratedElement.generated_block_bid.in_(retired),
        LearnGeneratedElement.status == 1,
        LearnGeneratedElement.deleted == 0,
    ).update({LearnGeneratedElement.status: 0}, synchronize_session=False)
    presentation["turns"] = [
        t for t in presentation["turns"] if t["block_bid"] not in retired
    ]
    presentation["questions"] = {
        b: ids for b, ids in presentation["questions"].items() if b not in retired
    }
    presentation["answers"] = {
        q: a
        for q, a in presentation["answers"].items()
        if q in plan.checkpoint["answers"]
    }
    data = json.loads(row.session_data)
    data[PREVIEW_PRESENTATION_KEY] = presentation
    row.session_data = json.dumps(data, ensure_ascii=False)
