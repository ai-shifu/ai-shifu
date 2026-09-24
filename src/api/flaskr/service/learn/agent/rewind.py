"""Take a 2.0 lesson back to an earlier turn, the way a 1.0 lesson regenerates from a block.

A learner can go back: choose differently on a question already answered, or regenerate a piece
of content. The browser truncates the page and sends the block it went back to. A 1.0 run
deactivates the rows written after it and carries on; the 2.0 engine has a conversation to take
back as well, and nothing in the rows says what that conversation looked like at the time.

So every turn records it. Before a turn runs, the state of the session -- how many messages it
had, its memory, the questions it was waiting on, the answers collected for them -- is written onto
that turn's block together with the learner input the turn was run with. Messages are only ever
appended, so a count restores them; nothing else of the history is copied.

Going back to a block is then a restore plus a turn:

* regenerating content in block B restores B's own checkpoint and runs B's input again;
* answering a question asked in B differently restores the checkpoint of the turn after B -- the
  one that received the old answer, which began with exactly that question pending -- and runs it
  with the new answer.

Turns written before checkpoints existed cannot be taken back. That is said to the learner, never
handed to the 1.0 engine: 1.0 would regenerate from rows it did not write and leave the 2.0
session where it was, so the page and the lesson would disagree from then on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.order.consts import LEARN_STATUS_RESET
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
)

if TYPE_CHECKING:
    from flaskr.service.learn.agent.engine.session import Session

_KEY = "agent_turn"
_VERSION = 1
# Follow-up questions run beside the lesson on the 1.0 path and are kept, as 1.0 keeps them.
_KEPT_BLOCK_TYPES = (BLOCK_TYPE_MDASK_VALUE, BLOCK_TYPE_MDANSWER_VALUE)


class RewindUnavailableError(Exception):
    """The block the learner went back to cannot be returned to."""


@dataclass
class RewindPlan:
    """What going back to a block takes: the state to restore and the rows to retire."""

    checkpoint: dict[str, Any]
    # The learner input to run the restored turn with; None means the request's own input.
    replay_values: list[str] | None
    retired_block_bids: list[str] = field(default_factory=list)


def checkpoint_of(session: Session) -> dict[str, Any]:
    """Return the state of `session` a later rewind needs, as JSON-ready data."""
    state = session.to_dict()
    return {
        "messages": len(session.messages),
        "memory": state["memory"],
        "pending": state["pending"],
        "answers": state["answers"],
        "turn": state["turn"],
        "finished": state["finished"],
    }


def restore(session: Session, checkpoint: dict[str, Any]) -> None:
    """Put `session` back into the state `checkpoint` recorded.

    The script, the learner's profile and the usage count stay as they are: the first two are
    re-read every turn, and the model calls already made were made.
    """
    from flaskr.service.learn.agent.engine.session import Session as SessionClass

    state = session.to_dict()
    state.update(
        memory=checkpoint.get("memory") or {},
        pending=checkpoint.get("pending") or [],
        answers=checkpoint.get("answers") or {},
        turn=int(checkpoint.get("turn") or 0),
        finished=bool(checkpoint.get("finished", False)),
    )
    state["messages"] = state["messages"][: int(checkpoint.get("messages") or 0)]
    restored = SessionClass.from_dict(state)
    session.messages = restored.messages
    session.memory = restored.memory
    session.pending = restored.pending
    session.answers = restored.answers
    session.turn = restored.turn
    session.finished = restored.finished


def turn_record(checkpoint: dict[str, Any], values: list[str]) -> str:
    """Return what a turn block keeps so the turn can be taken back to later."""
    return json.dumps(
        {_KEY: {"version": _VERSION, "checkpoint": checkpoint, "values": values}},
        ensure_ascii=False,
    )


def _read_turn_record(block: LearnGeneratedBlock) -> dict[str, Any] | None:
    try:
        data = json.loads(block.block_content_conf or "")
    except ValueError:
        return None
    record = data.get(_KEY) if isinstance(data, dict) else None
    if not isinstance(record, dict) or record.get("version") != _VERSION:
        return None
    if not isinstance(record.get("checkpoint"), dict):
        return None
    return record


def _anchor_block(
    *, user_bid: str, outline_bid: str, anchor: str
) -> LearnGeneratedBlock | None:
    """Find the block the learner went back to, by element or by block identifier.

    The browser sends a block identifier in both reload fields for a question and an element's
    for content, and 1.0 accepts either; so does this.
    """
    element = (
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.element_bid == anchor,
            LearnGeneratedElement.user_bid == user_bid,
            LearnGeneratedElement.deleted == 0,
        )
        .order_by(LearnGeneratedElement.id.desc())
        .first()
    )
    block_bid = (element.generated_block_bid or "") if element else anchor
    block = LearnGeneratedBlock.query.filter(
        LearnGeneratedBlock.generated_block_bid == block_bid,
        LearnGeneratedBlock.user_bid == user_bid,
        LearnGeneratedBlock.outline_item_bid == outline_bid,
        LearnGeneratedBlock.status == 1,
        LearnGeneratedBlock.deleted == 0,
    ).first()
    if block is None:
        return None
    # Only a block of the attempt still being taken: one from before a reset is history.
    live = LearnProgressRecord.query.filter(
        LearnProgressRecord.progress_record_bid == block.progress_record_bid,
        LearnProgressRecord.user_bid == user_bid,
        LearnProgressRecord.deleted == 0,
        LearnProgressRecord.status != LEARN_STATUS_RESET,
    ).first()
    return block if live is not None else None


def _turn_blocks_from(
    block: LearnGeneratedBlock, *, include_it: bool
) -> list[LearnGeneratedBlock]:
    """Return the lesson's live turn blocks from `block` on, oldest first."""
    return (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.progress_record_bid == block.progress_record_bid,
            LearnGeneratedBlock.user_bid == block.user_bid,
            LearnGeneratedBlock.outline_item_bid == block.outline_item_bid,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.type.notin_(_KEPT_BLOCK_TYPES),
            LearnGeneratedBlock.id >= block.id
            if include_it
            else LearnGeneratedBlock.id > block.id,
        )
        .order_by(LearnGeneratedBlock.id.asc())
        .all()
    )


def plan_rewind(
    *,
    user_bid: str,
    outline_bid: str,
    anchor: str,
    answering: bool,
) -> RewindPlan | None:
    """Work out how to take the lesson back to the block the learner chose.

    `answering` says whether the learner sent an answer (a question chosen differently) or
    nothing (content regenerated). Returns None when there is nothing to take back: a question
    that was never answered is simply being answered now. Raises `RewindUnavailableError` when the
    block cannot be returned to.
    """
    block = _anchor_block(user_bid=user_bid, outline_bid=outline_bid, anchor=anchor)
    if block is None or block.type != BLOCK_TYPE_MDCONTENT_VALUE:
        raise RewindUnavailableError
    if answering:
        later = _turn_blocks_from(block, include_it=False)
        if not later:
            return None
        target = later[0]
    else:
        target = block
    record = _read_turn_record(target)
    if record is None:
        raise RewindUnavailableError
    if answering and not record["checkpoint"].get("pending"):
        # The turn after the question did not begin with a question waiting, so it was not the
        # one that received this answer.
        raise RewindUnavailableError
    return RewindPlan(
        checkpoint=record["checkpoint"],
        replay_values=None if answering else list(record.get("values") or []),
        retired_block_bids=[
            b.generated_block_bid
            for b in _turn_blocks_from(target, include_it=True)
            if b.generated_block_bid
        ],
    )


def stage_retirement(plan: RewindPlan, *, user_bid: str, outline_bid: str) -> None:
    """Deactivate the blocks and elements the rewind superseded, as 1.0's reload does."""
    if not plan.retired_block_bids:
        return
    LearnGeneratedBlock.query.filter(
        LearnGeneratedBlock.generated_block_bid.in_(plan.retired_block_bids),
        LearnGeneratedBlock.user_bid == user_bid,
        LearnGeneratedBlock.outline_item_bid == outline_bid,
        LearnGeneratedBlock.status == 1,
    ).update({LearnGeneratedBlock.status: 0}, synchronize_session=False)
    LearnGeneratedElement.query.filter(
        LearnGeneratedElement.generated_block_bid.in_(plan.retired_block_bids),
        LearnGeneratedElement.user_bid == user_bid,
        LearnGeneratedElement.outline_item_bid == outline_bid,
        LearnGeneratedElement.status == 1,
    ).update({LearnGeneratedElement.status: 0}, synchronize_session=False)
