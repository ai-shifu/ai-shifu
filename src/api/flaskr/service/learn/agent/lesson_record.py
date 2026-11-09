"""Record a 2.0 turn where the rest of the product already looks for it.

A lesson taught by the engine still has to appear in the learner's history, carry its audio and
count as progress. All of that is read starting from a `LearnProgressRecord`, and the elements the
stream persists are tied to it through a `LearnGeneratedBlock`. The engine produces neither, so
this does.

The same progress record settles a second question. Resetting a lesson marks its progress records
`LEARN_STATUS_RESET`, and a turn already running when that happens holds no session row for the
reset to clear -- it would insert one afterwards and hand the learner back the conversation they
had just cleared. A turn that reads the record it started from can see that it was reset and stop
rather than claim the lesson again, without a tombstone of its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.dao import db, retry_on_deadlock
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.learn.const import CONTEXT_INTERACTION_NEXT, ROLE_TEACHER
from flaskr.service.learn.learn_dtos import LearnStatus, OutlineItemUpdateDTO
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.learn.progress_ordering import progress_record_order
from flaskr.service.learn.utils_v2 import init_generated_block
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_RESET,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from flaskr.util.uuid import generate_id

if TYPE_CHECKING:
    from flask import Flask


def _this_turn_s_record(
    *, user_bid: str, shifu_bid: str, outline_bid: str, progress_record_bid: str
) -> LearnProgressRecord | None:
    """Return the record this turn was taught against, still live, locked until this commits.

    Named, not merely live. A learner who resets and starts again leaves a second record behind
    the first, and a turn from before the reset that asked only for "the live one" would find
    the new attempt and complete it -- finishing a lesson the learner had just started over and
    carrying them past it.

    Locked for the same reason `claim_for_writing` locks: a reset can otherwise commit between
    the read and the write, so the read sees a live lesson and the write lands after the reset,
    putting back the completion the learner had just cleared.
    """
    if not progress_record_bid:
        return None
    return (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.progress_record_bid == progress_record_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .populate_existing()
        .with_for_update()
        .first()
    )


def find_active_progress_record(
    *, user_bid: str, shifu_bid: str, outline_bid: str
) -> LearnProgressRecord | None:
    """Prefer the started attempt over a parallel follow-up's placeholder."""
    return (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .order_by(*progress_record_order())
        .first()
    )


def active_progress_record(
    app: Flask, *, user_bid: str, shifu_bid: str, outline_bid: str
) -> LearnProgressRecord:
    """Return the learner's live progress record for this lesson, creating it if it is missing.

    Staged, not committed: the caller owns the transaction, so the record lands with the session
    and the turn's elements or not at all.
    """
    record = find_active_progress_record(
        user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
    )
    if record is not None:
        return record
    return _stage_progress_record(
        app, user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
    )


def _stage_progress_record(
    app: Flask, *, user_bid: str, shifu_bid: str, outline_bid: str
) -> LearnProgressRecord:
    record = LearnProgressRecord()
    record.progress_record_bid = generate_id(app)
    record.user_bid = user_bid
    record.shifu_bid = shifu_bid
    record.outline_item_bid = outline_bid
    record.status = LEARN_STATUS_IN_PROGRESS
    record.block_position = 0
    db.session.add(record)
    return record


def _progress_for_reconciliation(
    app: Flask, *, user_bid: str, shifu_bid: str, outline_bid: str
) -> LearnProgressRecord | None:
    """Read current progress under lock and preserve deliberate retakes on reopen."""
    records = (
        LearnProgressRecord.query.filter_by(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            deleted=0,
        )
        .order_by(*progress_record_order())
        .populate_existing()
        .with_for_update()
        .all()
    )
    active = next(
        (record for record in records if record.status != LEARN_STATUS_RESET), None
    )
    if any(record.status == LEARN_STATUS_RESET for record in records) and (
        active is None
        or active.status not in (LEARN_STATUS_IN_PROGRESS, LEARN_STATUS_COMPLETED)
    ):
        return None
    return active or _stage_progress_record(
        app, user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
    )


def _unfinished_retakes(
    *, user_bid: str, shifu_bid: str, outline_bids: set[str]
) -> set[str]:
    """Find visible chapter lessons with an unfinished deliberate retake."""
    if not outline_bids:
        return set()
    progress = LearnProgressRecord.query.with_entities(
        LearnProgressRecord.outline_item_bid, LearnProgressRecord.status
    ).filter_by(user_bid=user_bid, shifu_bid=shifu_bid, deleted=0)
    retired = {
        bid
        for bid, _ in progress.filter(
            LearnProgressRecord.outline_item_bid.in_(outline_bids),
            LearnProgressRecord.status == LEARN_STATUS_RESET,
        ).with_for_update()
    }
    if not retired:
        return set()
    # A normal completed sibling never needs an active-row lock here.
    records = (
        progress.filter(
            LearnProgressRecord.outline_item_bid.in_(retired),
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .order_by(*progress_record_order())
        .with_for_update()
    )
    active: dict[str, int] = {}
    for bid, status in records:
        active.setdefault(bid, status)
    return {bid for bid in retired if active.get(bid) != LEARN_STATUS_COMPLETED}


def claim_for_writing(
    *, user_bid: str, shifu_bid: str, outline_bid: str, progress_record_bid: str
) -> LearnProgressRecord | None:
    """Lock the record this turn started from, or report that it is gone.

    Returns None when the lesson was reset while the turn ran: the learner asked for it to start
    over, and a first turn holds no session row for the reset to have cleared, so writing now would
    hand back the conversation they just cleared.

    The row is locked rather than merely read. Checking and writing in separate transactions leaves
    a gap a reset can commit inside -- the check sees a live lesson, the reset finds no session to
    discard, and the write lands afterwards. Holding the lock until this transaction commits makes
    the two orders the only possibilities: either the reset goes first and this sees it, or this
    goes first and the reset finds the session and clears it.
    """
    if not progress_record_bid:
        return None
    return (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.progress_record_bid == progress_record_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .populate_existing()
        .with_for_update()
        .first()
    )


def mark_lesson_finished(record: LearnProgressRecord) -> None:
    """Record that the lesson is over, where the product reads completion from.

    Progress is read from this status, not from the agent session's own `finished` flag, so a
    lesson the model finished would otherwise stay "in progress" in the outline and be missing
    from completion reports.
    """
    record.status = LEARN_STATUS_COMPLETED


def retire_unused_block(*, generated_block_bid: str) -> None:
    """Drop a block the turn never filled in.

    The block is created before the turn streams, because the element rows reference it while it
    runs. A turn that dies before it finishes -- an engine error, a learner closing the page --
    never records its text, and the row left behind is an empty assistant turn that the 1.0 run
    would read as part of the conversation if the deployment disabled 2.0.

    Only an untouched block is dropped. One that already has text, or a turn record, belongs to a
    turn that was saved: a turn that only asks a question teaches no text, and dropping its block
    after the save would leave the stored session ahead of the rows.
    """
    block = LearnGeneratedBlock.query.filter(
        LearnGeneratedBlock.generated_block_bid == generated_block_bid,
        LearnGeneratedBlock.deleted == 0,
    ).first()
    if (
        block is not None
        and not (block.generated_content or "").strip()
        and not (block.block_content_conf or "").strip()
    ):
        block.deleted = 1
        block.status = 0


def record_turn_content(
    *, generated_block_bid: str, content: str, turn_record: str = ""
) -> None:
    """Fill in what the turn taught, now that it is over.

    The row itself is created before the turn streams, because the element rows reference it while
    it runs. Its text is only known at the end.

    `turn_record` is what a later rewind to this turn needs (see `agent.rewind`); it goes in
    `block_content_conf`, which a 2.0 turn block has no other use for.
    """
    block = LearnGeneratedBlock.query.filter(
        LearnGeneratedBlock.generated_block_bid == generated_block_bid,
        LearnGeneratedBlock.deleted == 0,
    ).first()
    if block is not None:
        block.generated_content = content
        if turn_record:
            block.block_content_conf = turn_record


def stage_turn_block(
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    progress_record_bid: str,
    generated_block_bid: str,
    position: int,
    content: str = "",
) -> LearnGeneratedBlock:
    """Record this turn as one generated block, so its elements can be found again.

    The element pipeline reads `progress_record_bid` off this row; history retrieval walks from the
    progress record to its blocks and admits the elements hanging off them. Without it the stream
    still reaches the learner and disappears on the next page load.

    Created before the turn streams, not after: the element pipeline resolves an element's
    progress record by reading this row, so a block that appeared only at the end left every
    element of the turn with an empty progress reference.

    `content` is filled in by `record_turn_content` once the turn is over. The 1.0 run builds its
    model context from these rows and reads that column for the assistant's side of the
    conversation -- it does not fall back to the element rows. Leaving it empty would matter the
    moment the deployment disables 2.0: 1.0 would resume the lesson seeing its own
    questions answered by silence.
    """
    block = LearnGeneratedBlock()
    block.progress_record_bid = progress_record_bid
    block.user_bid = user_bid
    block.outline_item_bid = outline_bid
    block.shifu_bid = shifu_bid
    block.block_bid = ""
    # Lesson text, as far as the element pipeline is concerned.
    block.type = BLOCK_TYPE_MDCONTENT_VALUE
    # The identifier is the one the turn's events already carry, not a fresh one: the element rows
    # reference it, so a different value here would leave them orphaned.
    block.generated_block_bid = generated_block_bid
    block.generated_content = content
    block.status = 1
    block.block_content_conf = ""
    block.position = position
    db.session.add(block)
    return block


def apply_outline_progression(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    progress_record_bid: str,
    updates: list[OutlineItemUpdateDTO],
) -> bool:
    """Write ordinary completion progress while the finished attempt is active."""
    return (
        _write_outline_progression(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            progress_record_bid=progress_record_bid,
            updates=updates,
        )
        is not None
    )


@retry_on_deadlock(max_attempts=2)
def reconcile_outline_progression(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    progress_record_bid: str,
    updates: list[OutlineItemUpdateDTO],
    chapter_lessons: dict[str, set[str]],
) -> list[OutlineItemUpdateDTO]:
    """Reconcile a reopened attempt and return the selected outline's durable statuses."""
    return (
        _write_outline_progression(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            progress_record_bid=progress_record_bid,
            updates=updates,
            chapter_lessons=chapter_lessons,
        )
        or []
    )


def _write_outline_progression(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    progress_record_bid: str,
    updates: list[OutlineItemUpdateDTO],
    chapter_lessons: dict[str, set[str]] | None = None,
) -> list[OutlineItemUpdateDTO] | None:
    """Apply progress only if the attempt that finished is still active.

    A reset can commit after the turn finishes and before its catalog updates.
    Lock the exact attempt so progression cannot revive it or advance past it.
    Reopening respects independent retakes of later items, since this visit
    completed no new teaching. It includes unchanged active statuses so a
    catalog loaded before the history request can still render current progress.
    """
    reconcile = chapter_lessons is not None
    persisted_updates = []
    with app_context_scope(app), unit_of_work():
        lesson = _this_turn_s_record(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            progress_record_bid=progress_record_bid,
        )
        if lesson is None:
            app.logger.warning(
                "outline progression skipped, lesson was reset while it finished:"
                " user_bid=%s outline_bid=%s",
                user_bid,
                outline_bid,
            )
            return None
        if reconcile and lesson.status != LEARN_STATUS_COMPLETED:
            return None
        blocked_chapters = set()
        if chapter_lessons:
            unfinished = _unfinished_retakes(
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bids=set().union(*chapter_lessons.values()) - {outline_bid},
            )
            blocked_chapters = {
                chapter_bid
                for chapter_bid, lessons in chapter_lessons.items()
                if lessons & unfinished
            }
        for update in updates:
            if update.outline_bid == outline_bid:
                record = lesson
            else:
                select_progress = (
                    _progress_for_reconciliation
                    if reconcile
                    else active_progress_record
                )
                record = select_progress(
                    app,
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    outline_bid=update.outline_bid,
                )
                if record is None:
                    persisted_updates.append(
                        update.model_copy(update={"status": LearnStatus.NOT_STARTED})
                    )
                    continue
            # Handing the learner to a finished lesson preserves its completion.
            status = (
                LearnStatus.COMPLETED
                if record.status == LEARN_STATUS_COMPLETED
                or (
                    update.status == LearnStatus.COMPLETED
                    and update.outline_bid not in blocked_chapters
                )
                else LearnStatus.IN_PROGRESS
            )
            record.status = (
                LEARN_STATUS_COMPLETED
                if status == LearnStatus.COMPLETED
                else LEARN_STATUS_IN_PROGRESS
            )
            if reconcile:
                persisted_updates.append(update.model_copy(update={"status": status}))
    return persisted_updates


def record_next_lesson_interaction(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    progress_record_bid: str,
    content: str,
) -> str | None:
    """Persist the navigation control before its live element is sent.

    The 2.0 lesson has already saved its completion and outline updates. A reset can still land
    between those writes and this one, so the control belongs only to the same live progress row.
    Element history reads persisted rows directly and cannot recover a control sent only on SSE.
    """
    with app_context_scope(app), unit_of_work():
        record = _this_turn_s_record(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            progress_record_bid=progress_record_bid,
        )
        if record is None or record.status != LEARN_STATUS_COMPLETED:
            return None
        existing = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.progress_record_bid == progress_record_bid,
            LearnGeneratedBlock.user_bid == user_bid,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDINTERACTION_VALUE,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.block_content_conf.contains(CONTEXT_INTERACTION_NEXT),
        ).first()
        if existing is not None:
            return None
        block = init_generated_block(
            app,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            progress_record_bid=progress_record_bid,
            user_bid=user_bid,
            block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
            mdflow=content,
            block_index=record.block_position,
        )
        block.role = ROLE_TEACHER
        db.session.add(block)
        return block.generated_block_bid
