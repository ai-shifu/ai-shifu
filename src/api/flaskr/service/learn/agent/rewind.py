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
  one that received the old answer, as a pending interaction or as a message -- and runs it
  with the new answer.

Turns written before checkpoints existed cannot be taken back. That is said to the learner, never
handed to the 1.0 engine: 1.0 would regenerate from rows it did not write and leave the 2.0
session where it was, so the page and the lesson would disagree from then on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from flask import current_app
from flaskr.service.learn.agent.turn_liveness import turn_is_live
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
from flaskr.util.datetime import now_utc
from markdownflow import InteractionParser
from pydantic_ai.messages import ModelRequest, TextPart, ToolCallPart, UserPromptPart

if TYPE_CHECKING:
    from flaskr.api.markdownflow import Session

_KEY = "agent_turn"
_VERSION = 1
# Follow-up questions run beside the lesson on the 1.0 path and are kept, as 1.0 keeps them.
_KEPT_BLOCK_TYPES = (BLOCK_TYPE_MDASK_VALUE, BLOCK_TYPE_MDANSWER_VALUE)


class RewindUnavailableError(Exception):
    """The block the learner went back to cannot be returned to."""


@dataclass(frozen=True)
class NarratedAnswer:
    """Evidence that a saved message was the reply to one rendered control."""

    control: str
    start: int
    values: list[str]
    session_id: str | None
    user_input: str


def narrated_answer(
    original: dict[str, Any] | None,
    accepting: dict[str, Any] | None,
    control: str,
) -> NarratedAnswer | None:
    """Recognize only the immediate answer to a single non-native control."""
    if (
        not isinstance(original, dict)
        or original.get("version") != _VERSION
        or original.get("question_ids") not in (None, [])
        or not isinstance(accepting, dict)
        or accepting.get("version") != _VERSION
        or accepting.get("answered_question_id") is not None
    ):
        return None
    before = original.get("checkpoint")
    after = accepting.get("checkpoint")
    values = accepting.get("values")
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None
    start, end = before.get("messages"), after.get("messages")
    prior_turn = before.get("turn")
    original_id, accepting_id = before.get("session_id"), after.get("session_id")
    if (
        not isinstance(start, int)
        or not isinstance(end, int)
        or not 0 <= start < end
        or not isinstance(prior_turn, int)
        or after.get("turn") != prior_turn + 1
        or after.get("pending") != []
        or after.get("answers") != {}
        or after.get("finished") is not False
        or after.get("interrupted", False)
        or (original_id and accepting_id and original_id != accepting_id)
        or not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) or not value.strip() for value in values)
    ):
        return None
    from .interaction_history import narrated_user_input

    user_input = narrated_user_input(control, values)
    if user_input is None:
        return None
    return NarratedAnswer(
        control, start, values, accepting_id or original_id, user_input
    )


@dataclass
class RewindPlan:
    """What going back to a block takes: the state to restore and the rows to retire."""

    checkpoint: dict[str, Any]
    # The learner input to run the restored turn with; None means the request's own input.
    replay_values: list[str] | None
    retired_block_bids: list[str] = field(default_factory=list)
    source_block_bids: list[str] = field(default_factory=list)
    progress_record_bid: str | None = None
    narrated: NarratedAnswer | None = None


def plan_turn_rewind(
    turns: list[dict[str, Any]],
    *,
    block_bid: str,
    answering: bool,
    question_id: str | None = None,
    narrated_control: str | None = None,
) -> RewindPlan | None:
    """Select and validate the same rewind for every course session store.

    Content replays its own input. An answer edit restores the turn that
    accepted that question, retaining the question's original teaching.
    """
    anchor = next(
        (i for i, turn in enumerate(turns) if turn.get("block_bid") == block_bid),
        None,
    )
    if anchor is None:
        raise RewindUnavailableError
    target = anchor
    narrated = None
    if answering and narrated_control is not None:
        # Never search forward for a non-native answer. A later turn may belong
        # to a different question, or even a different engine session.
        target = anchor + 1
        if target == len(turns):
            raise RewindUnavailableError
        narrated = narrated_answer(
            turns[anchor].get("record"),
            turns[target].get("record"),
            narrated_control,
        )
        if narrated is None:
            raise RewindUnavailableError
    elif answering:
        target = None
        for i in range(anchor + 1, len(turns)):
            # Published learning keeps its existing next-turn boundary. Draft
            # presentation metadata names the turn that actually accepted input.
            if question_id is None:
                target = i
                break
            if "answered_question_id" in turns[i]:
                if turns[i]["answered_question_id"] == question_id:
                    target = i
                    break
                continue
            record = turns[i].get("record")
            if isinstance(record, dict) and "answered_question_id" in record:
                if record["answered_question_id"] == question_id:
                    target = i
                    break
                continue
            checkpoint = record.get("checkpoint") if isinstance(record, dict) else None
            pending = (
                checkpoint.get("pending") if isinstance(checkpoint, dict) else None
            )
            if (
                isinstance(pending, list)
                and pending
                and isinstance(pending[0], dict)
                and pending[0].get("tool_call_id") == question_id
            ):
                target = i
                break
        if target is None:
            return None
    record = turns[target].get("record")
    if not isinstance(record, dict) or record.get("version") != _VERSION:
        raise RewindUnavailableError
    checkpoint = record.get("checkpoint")
    values = record.get("values")
    if (
        not isinstance(checkpoint, dict)
        or not {"messages", "memory", "pending", "answers", "turn", "finished"}
        <= checkpoint.keys()
        or not isinstance(checkpoint["messages"], int)
        or checkpoint["messages"] < 0
        or not isinstance(checkpoint["pending"], list)
        or any(not isinstance(q, dict) for q in checkpoint["pending"])
        or not isinstance(values, list)
        or any(not isinstance(value, str) for value in values)
        or (answering and narrated is None and not checkpoint["pending"])
        or (
            answering
            and question_id is not None
            and checkpoint["pending"][0].get("tool_call_id") != question_id
        )
    ):
        raise RewindUnavailableError
    return RewindPlan(
        checkpoint=checkpoint,
        replay_values=None if answering else list(values),
        retired_block_bids=[turn["block_bid"] for turn in turns[target:]],
        narrated=narrated,
    )


def validate_narrated_rewind(session: Session, plan: RewindPlan) -> None:
    """Prove the control and the accepted input exist at this session's boundary."""
    evidence = plan.narrated
    if evidence is None:
        return
    end = plan.checkpoint["messages"]
    if end >= len(session.messages) or (
        evidence.session_id and evidence.session_id != session.id
    ):
        raise RewindUnavailableError
    request = session.messages[end]
    old_answer = ",".join(evidence.values)
    if not isinstance(request, ModelRequest) or not any(
        isinstance(part, UserPromptPart)
        and isinstance(part.content, str)
        and (
            part.content == old_answer
            or (
                part.content.startswith("<memory_context>Host memory revalidation")
                and part.content.endswith(f"</memory_context>\n\n{old_answer}")
            )
        )
        for part in request.parts
    ):
        raise RewindUnavailableError

    # Historical checkpoints lack a session ID. Verify the originating markup
    # in the saved model response as well as the reply at the exact boundary.
    from .interaction_syntax import InteractionSyntaxFilter

    syntax = InteractionSyntaxFilter()
    syntax.feed(
        "".join(
            part.content
            for message in session.messages[evidence.start : end]
            for part in message.parts
            if isinstance(part, TextPart)
        )
    )
    syntax.flush()
    if not syntax.spans:
        raise RewindUnavailableError
    parser = InteractionParser()
    original = parser.parse(syntax.spans[-1])
    shown = parser.parse(evidence.control)
    if original.get("question") == "":
        # The host may have inserted a localized placeholder at render time.
        original["question"] = shown.get("question", "")
    if original != shown:
        raise RewindUnavailableError


def checkpoint_of(session: Session) -> dict[str, Any]:
    """Return the state of `session` a later rewind needs, as JSON-ready data."""
    state = session.to_dict()
    return {
        "messages": len(session.messages),
        "session_id": state.get("id"),
        "memory": state["memory"],
        "answer_hashes": state.get("answer_hashes", {}),
        "memory_generations": state.get("memory_generations", {}),
        "pending": state["pending"],
        "answers": state["answers"],
        "request_inputs": state.get("request_inputs", []),
        "turn": state["turn"],
        "finished": state["finished"],
        "interrupted": state.get("interrupted", False),
    }


def restore(session: Session, checkpoint: dict[str, Any]) -> None:
    """Put `session` back into the state `checkpoint` recorded.

    The script, the learner's profile and the usage count stay as they are: the first two are
    re-read every turn, and the model calls already made were made.
    """
    from flaskr.api.markdownflow import Session as SessionClass

    state = session.to_dict()
    message_count = int(checkpoint.get("messages") or 0)
    retained_calls = {
        part.tool_call_id
        for message in session.messages[:message_count]
        for part in message.parts
        if isinstance(part, ToolCallPart) and part.tool_name == "interact"
    }
    state.update(
        memory=checkpoint.get("memory") or {},
        interaction_specs={
            call_id: spec
            for call_id, spec in state.get("interaction_specs", {}).items()
            if call_id in retained_calls
        },
        pending=checkpoint.get("pending") or [],
        answers=checkpoint.get("answers") or {},
        request_inputs=checkpoint.get("request_inputs") or [],
        turn=int(checkpoint.get("turn") or 0),
        finished=bool(checkpoint.get("finished", False)),
        interrupted=bool(checkpoint.get("interrupted", False)),
    )
    state["messages"] = state["messages"][:message_count]
    if "answer_hashes" in checkpoint:
        state["answer_hashes"] = checkpoint["answer_hashes"]
    else:
        state.pop("answer_hashes", None)
    restored = SessionClass.from_dict(state)
    session.messages = restored.messages
    session.memory = restored.memory
    session.interaction_specs = restored.interaction_specs
    session.answer_hashes = restored.answer_hashes
    # Restored memory reflects the deletions seen when the checkpoint was taken, so later
    # deletions are refreshed again. Older checkpoints refresh every deleted-once key.
    session.memory_generations = {
        str(key): int(value)
        for key, value in (checkpoint.get("memory_generations") or {}).items()
    }
    session.pending = restored.pending
    session.answers = restored.answers
    session.request_inputs = restored.request_inputs
    session.turn = restored.turn
    session.finished = restored.finished
    session.interrupted = restored.interrupted


def turn_record(checkpoint: dict[str, Any], values: list[str]) -> str:
    """Return what a turn block keeps so the turn can be taken back to later."""
    return json.dumps(
        {_KEY: {"version": _VERSION, "checkpoint": checkpoint, "values": values}},
        ensure_ascii=False,
    )


def with_turn_interactions(
    turn: str, *, session: Session, question_ids: list[str]
) -> str:
    """Record the emitted controls and which pending question actually accepted input."""
    if not turn:
        return turn
    document = json.loads(turn)
    record = document[_KEY]
    pending = record["checkpoint"].get("pending", [])
    accepted_id = None
    if pending and isinstance(pending[0], dict) and record["values"]:
        first = pending[0].get("tool_call_id")
        if isinstance(first, str) and first:
            remaining = {item.tool_call_id for item in session.pending}
            if first not in remaining or first in session.answers:
                accepted_id = first
    record["question_ids"] = question_ids
    record["answered_question_id"] = accepted_id
    return json.dumps(document, ensure_ascii=False)


def recorded_question_ids(
    record: dict[str, Any] | None, control_count: int
) -> list[str] | None:
    """Return the emitted identities only when every control has an unambiguous ID."""
    ids = record.get("question_ids") if record else None
    if (
        not isinstance(ids, list)
        or len(ids) != control_count
        or any(
            not isinstance(question_id, str) or not question_id for question_id in ids
        )
        or len(set(ids)) != control_count
    ):
        return None
    return ids


def read_turn_record(block: LearnGeneratedBlock) -> dict[str, Any] | None:
    """Read a recognized durable turn checkpoint without exposing session state to clients."""
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


def read_turn_learner_values(block: LearnGeneratedBlock) -> list[str]:
    """Project only submitted learner text from a recognized turn record.

    Follow-up history uses this durable input evidence without reading agent
    sessions or exposing checkpoint memory, pending tools or configuration.
    """
    record = read_turn_record(block)
    if record is None:
        return []
    values = record.get("values")
    if not isinstance(values, list) or any(
        not isinstance(value, str) for value in values
    ):
        return []
    return [value for value in values if value.strip()]


def _anchor_block(
    *, user_bid: str, outline_bid: str, anchor: str, shifu_bid: str | None = None
) -> LearnGeneratedBlock | None:
    """Find the block the learner went back to, by element or by block identifier.

    The browser sends a block identifier in both reload fields for a question and an element's
    for content, and 1.0 accepts either; so does this.
    """
    elements = LearnGeneratedElement.query.filter_by(
        element_bid=anchor,
        user_bid=user_bid,
        outline_item_bid=outline_bid,
        status=1,
        deleted=0,
    )
    if shifu_bid is not None:
        elements = elements.filter_by(shifu_bid=shifu_bid)
    element = elements.order_by(LearnGeneratedElement.id.desc()).first()
    block_bid = (element.generated_block_bid or "") if element else anchor
    blocks = LearnGeneratedBlock.query.filter_by(
        generated_block_bid=block_bid,
        user_bid=user_bid,
        outline_item_bid=outline_bid,
        status=1,
        deleted=0,
    )
    if shifu_bid is not None:
        blocks = blocks.filter_by(shifu_bid=shifu_bid)
    block = blocks.first()
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


def _question_for_control(
    block: LearnGeneratedBlock, element_bid: str, turns: list[dict[str, Any]]
) -> tuple[str | None, str | None]:
    """Identify the selected native question or the sole narrated control.

    A turn may ask several questions at once. Its controls, in emission order, match the
    pending queue of the turn that followed it (as `interaction_history` reads answers).
    Without that question an answer edit would restore the first question's turn and the
    new value would answer the first question instead of the one the learner changed.
    """
    rows = (
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.generated_block_bid == block.generated_block_bid,
            LearnGeneratedElement.user_bid == block.user_bid,
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.event_type == "element",
            LearnGeneratedElement.element_type == "interaction",
        )
        .order_by(
            LearnGeneratedElement.sequence_number.asc(),
            LearnGeneratedElement.run_event_seq.asc(),
            LearnGeneratedElement.id.asc(),
        )
        .all()
    )
    identities: list[str] = []
    selected = None
    for row in rows:
        identity = (
            row.target_element_bid
            if not row.is_new and row.target_element_bid
            else row.element_bid
        )
        if not identity:
            continue
        if identity not in identities:
            identities.append(identity)
        if element_bid in (row.element_bid, identity):
            selected = identities.index(identity)
    if selected is None and not (
        element_bid == block.generated_block_bid and len(identities) == 1
    ):
        return None, None
    ids = recorded_question_ids(turns[0].get("record"), len(identities))
    if ids is not None:
        return (ids[selected] if selected is not None else None), None
    control = next(
        (
            row
            for row in rows
            if selected is None
            or element_bid
            in (
                row.element_bid,
                row.target_element_bid
                if not row.is_new and row.target_element_bid
                else row.element_bid,
            )
        ),
        None,
    )
    control_text = control.content_text if control is not None else None
    # Only the turn right after this one received these questions. A later turn's queue
    # belongs to other questions, so an unrecorded next turn means "cannot tell".
    following = turns[1].get("record") if len(turns) > 1 else None
    checkpoint = following.get("checkpoint") if isinstance(following, dict) else None
    pending = checkpoint.get("pending") if isinstance(checkpoint, dict) else None
    if (
        pending == []
        and len(identities) == 1
        and control is not None
        and control.status == 1
        and control.shifu_bid == block.shifu_bid
        and control.outline_item_bid == block.outline_item_bid
        and control.progress_record_bid == block.progress_record_bid
    ):
        return None, control_text or ""
    if (
        selected is None
        or not isinstance(pending, list)
        or len(identities) > len(pending)
    ):
        return None, None
    question = pending[selected]
    tool_call_id = question.get("tool_call_id") if isinstance(question, dict) else None
    if not isinstance(tool_call_id, str) or not tool_call_id:
        return None, None
    # Pairing by position holds only while each control renders its question. A
    # confirmation shows no control and shifts the queue; any mismatch means "cannot tell".
    from flaskr.api.markdownflow import InteractionSpec
    from pydantic import ValidationError

    from .interaction_history import _matches_control

    try:
        spec = InteractionSpec.model_validate(question.get("spec"))
        if spec.type == "confirm" or not _matches_control(spec, control_text or ""):
            return None, None
    except (ValidationError, ValueError):
        return None, None
    return tool_call_id, None


def plan_rewind(
    *,
    user_bid: str,
    outline_bid: str,
    anchor: str,
    answering: bool,
    shifu_bid: str | None = None,
    progress_record_bid: str | None = None,
) -> RewindPlan | None:
    """Work out how to take the lesson back to the block the learner chose.

    `answering` says whether the learner sent an answer (a question chosen differently) or
    nothing (content regenerated). Returns None when there is nothing to take back: a question
    that was never answered is simply being answered now. Raises `RewindUnavailableError` when the
    block cannot be returned to.
    """
    block = _anchor_block(
        user_bid=user_bid, outline_bid=outline_bid, anchor=anchor, shifu_bid=shifu_bid
    )
    if (
        block is None
        or block.type != BLOCK_TYPE_MDCONTENT_VALUE
        or (
            progress_record_bid is not None
            and block.progress_record_bid != progress_record_bid
        )
    ):
        raise RewindUnavailableError
    blocks = _turn_blocks_from(block, include_it=True)
    after_anchor = {b.generated_block_bid for b in blocks[1:]}
    abandoned = [
        bid
        for bid in abandoned_turn_block_bids(
            user_bid=block.user_bid,
            outline_bid=block.outline_item_bid,
            progress_record_bid=block.progress_record_bid,
        )
        if bid in after_anchor
    ]
    turns = [
        {"block_bid": b.generated_block_bid, "record": read_turn_record(b)}
        for b in blocks
        if b.generated_block_bid not in abandoned
    ]
    question_id, narrated_control = (
        _question_for_control(block, anchor, turns) if answering else (None, None)
    )
    plan = plan_turn_rewind(
        turns,
        block_bid=block.generated_block_bid,
        answering=answering,
        question_id=question_id,
        narrated_control=narrated_control,
    )
    if plan is None and question_id is not None:
        # Without an accepting checkpoint only the next unanswered control is
        # actionable. Missing old metadata must not turn an edit into a new answer.
        from flaskr.service.learn.agent.session_store import (
            StoredSessionUnusable,
            load_agent_session,
        )

        try:
            session = load_agent_session(current_app, user_bid, outline_bid)
        except StoredSessionUnusable:
            raise RewindUnavailableError from None
        if (
            session is None
            or not session.pending
            or session.pending[0].tool_call_id != question_id
        ):
            raise RewindUnavailableError
    if plan is not None:
        plan.retired_block_bids.extend(
            bid for bid in abandoned if bid not in plan.retired_block_bids
        )
        plan.source_block_bids = [
            t["block_bid"] for t in turns if t["record"] is not None
        ]
        plan.progress_record_bid = block.progress_record_bid
    return plan


# How long an empty, unrecorded block must sit before it counts as abandoned when its run left
# no word that it ended. After a disconnect the request releases the lesson lock while the
# producer thread may still be finishing the turn (prepared feedback persists its text late); a
# young block may still fill in. A run that ends says so (`agent.turn_liveness`); without that,
# wait twice the run lock's lifetime (`host.run.RUN_SCRIPT_TIMEOUT_SECONDS`, 5 minutes), since a
# run older than that has already lost the lock every concurrent-turn guard relies on. Raise both
# together.
ABANDONED_TURN_GRACE = timedelta(minutes=10)


def abandoned_turn_block_bids(
    *, user_bid: str, outline_bid: str, progress_record_bid: str
) -> list[str]:
    """Name the live turn blocks of an attempt whose run died before it saved.

    A run killed mid-stream, or one whose cleanup failed, leaves its block live with neither
    text nor turn record. A turn saved before checkpoints existed can look the same (one that
    only asked a question teaches no text), so a block counts only once an earlier block of the
    same attempt carries a record: from then on every saved turn writes one. Before the first
    record, an empty block counts when that record was taken at turn 0, which proves no earlier
    turn reached the saved session. A block whose run may still be finishing after the request
    that started it went away is left alone (`_run_has_ended`). No saved session ever included an
    abandoned block, so it is never a turn to go back to.
    """
    blocks = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.progress_record_bid == progress_record_bid,
            LearnGeneratedBlock.user_bid == user_bid,
            LearnGeneratedBlock.outline_item_bid == outline_bid,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDCONTENT_VALUE,
        )
        .order_by(LearnGeneratedBlock.id.asc())
        .all()
    )
    now = now_utc()
    abandoned: list[str] = []
    # Empty blocks seen before the attempt's first record: abandoned only if that record shows
    # no saved turn came before it (its checkpoint was taken at turn 0).
    leading: list[str] = []
    recorded = False
    for block in blocks:
        record = read_turn_record(block)
        empty = (
            record is None
            and not (block.generated_content or "").strip()
            and not (block.block_content_conf or "").strip()
            and _run_has_ended(block, now)
        )
        if record is not None:
            if not recorded and record["checkpoint"].get("turn") == 0:
                abandoned.extend(leading)
            recorded = True
        elif empty:
            (abandoned if recorded else leading).append(block.generated_block_bid)
    return abandoned


def _run_has_ended(block: LearnGeneratedBlock, now: datetime) -> bool:
    """Whether the run that wrote this block can no longer fill it in."""
    live = turn_is_live(current_app, block.generated_block_bid)
    if live is not None:
        return not live
    # The run left no word: its mark was never written, was lost, or has expired.
    return (
        block.created_at is not None and now - block.created_at >= ABANDONED_TURN_GRACE
    )


def retire_abandoned_turns(
    *, user_bid: str, outline_bid: str, progress_record_bid: str
) -> None:
    """Retire abandoned turn blocks, and their elements, before the next turn starts.

    A rewind retires them with the turns it supersedes; this covers the learner who simply
    answers again, which plans no rewind, so the dead turn's streamed rows do not stay in history.
    """
    bids = abandoned_turn_block_bids(
        user_bid=user_bid,
        outline_bid=outline_bid,
        progress_record_bid=progress_record_bid,
    )
    if bids:
        stage_retirement(
            RewindPlan(checkpoint={}, replay_values=None, retired_block_bids=bids),
            user_bid=user_bid,
            outline_bid=outline_bid,
        )


def _attached_follow_up_blocks(
    *, user_bid: str, outline_bid: str, progress_record_bid: str, retired: list[str]
) -> set[str]:
    scope = {
        "user_bid": user_bid,
        "outline_item_bid": outline_bid,
        "progress_record_bid": progress_record_bid,
        "status": 1,
        "deleted": 0,
    }
    elements = LearnGeneratedElement.query.filter_by(**scope)
    retired_elements = set()
    for row in elements.filter(
        LearnGeneratedElement.generated_block_bid.in_(retired)
    ).all():
        retired_elements.update((row.element_bid, row.target_element_bid))
    retired_elements.discard("")
    retired_elements.discard(None)
    linked = set()
    for row in elements.filter(
        LearnGeneratedElement.element_type.in_(["ask", "answer"])
    ).all():
        try:
            payload = json.loads(row.payload or "{}")
        except ValueError:
            continue
        if (
            isinstance(payload, dict)
            and payload.get("anchor_element_bid") in retired_elements
        ):
            linked.add(row.generated_block_bid)
    return linked


def stage_retirement(plan: RewindPlan, *, user_bid: str, outline_bid: str) -> None:
    """Deactivate the blocks and elements the rewind superseded, as 1.0's reload does."""
    if not plan.retired_block_bids:
        return
    retired = set(plan.retired_block_bids)
    if plan.progress_record_bid and plan.source_block_bids:
        anchor = _anchor_block(
            user_bid=user_bid, outline_bid=outline_bid, anchor=plan.source_block_bids[0]
        )
        if anchor is None or anchor.progress_record_bid != plan.progress_record_bid:
            raise RewindUnavailableError
        active = [
            block.generated_block_bid
            for block in _turn_blocks_from(anchor, include_it=True)
            if read_turn_record(block) is not None
        ]
        if active != plan.source_block_bids:
            raise RewindUnavailableError
        retired.update(
            _attached_follow_up_blocks(
                user_bid=user_bid,
                outline_bid=outline_bid,
                progress_record_bid=plan.progress_record_bid,
                retired=plan.retired_block_bids,
            )
        )
    LearnGeneratedBlock.query.filter(
        LearnGeneratedBlock.generated_block_bid.in_(retired),
        LearnGeneratedBlock.user_bid == user_bid,
        LearnGeneratedBlock.outline_item_bid == outline_bid,
        LearnGeneratedBlock.status == 1,
    ).update({LearnGeneratedBlock.status: 0}, synchronize_session=False)
    LearnGeneratedElement.query.filter(
        LearnGeneratedElement.generated_block_bid.in_(retired),
        LearnGeneratedElement.user_bid == user_bid,
        LearnGeneratedElement.outline_item_bid == outline_bid,
        LearnGeneratedElement.status == 1,
    ).update({LearnGeneratedElement.status: 0}, synchronize_session=False)
