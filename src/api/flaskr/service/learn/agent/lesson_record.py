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

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.learn.learn_dtos import LearnStatus, OutlineItemUpdateDTO
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_RESET,
)
from flaskr.service.shifu.consts import BLOCK_TYPE_MDCONTENT_VALUE
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
        .with_for_update()
        .first()
    )


def active_progress_record(
    app: Flask, *, user_bid: str, shifu_bid: str, outline_bid: str
) -> LearnProgressRecord:
    """Return the learner's live progress record for this lesson, creating it if it is missing.

    Staged, not committed: the caller owns the transaction, so the record lands with the session
    and the turn's elements or not at all.
    """
    record = (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .order_by(LearnProgressRecord.id.desc())
        .first()
    )
    if record is not None:
        return record

    record = LearnProgressRecord()
    record.progress_record_bid = generate_id(app)
    record.user_bid = user_bid
    record.shifu_bid = shifu_bid
    record.outline_item_bid = outline_bid
    record.status = LEARN_STATUS_IN_PROGRESS
    record.block_position = 0
    db.session.add(record)
    return record


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
    record = (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.progress_record_bid == progress_record_bid,
            LearnProgressRecord.deleted == 0,
        )
        .with_for_update()
        .first()
    )
    if record is None or record.status == LEARN_STATUS_RESET:
        return None
    return record


def mark_lesson_finished(record: LearnProgressRecord) -> None:
    """Record that the lesson is over, where the product reads completion from.

    Progress is read from this status, not from the agent session's own `finished` flag, so a
    lesson the model finished would otherwise stay "in progress" in the outline and be missing
    from completion reports.
    """
    record.status = LEARN_STATUS_COMPLETED


def mark_lesson_in_progress(record: LearnProgressRecord) -> None:
    """Record that the lesson is being taught again, after being taken back before its end."""
    record.status = LEARN_STATUS_IN_PROGRESS


def retire_unused_block(*, generated_block_bid: str) -> None:
    """Drop a block the turn never filled in.

    The block is created before the turn streams, because the element rows reference it while it
    runs. A turn that dies before it finishes -- an engine error, a learner closing the page --
    never records its text, and the row left behind is an empty assistant turn that the 1.0 run
    would read as part of the conversation if the course moved back off the allowlist.

    Only an untouched block is dropped: one that already has text belongs to a turn that finished.
    """
    block = LearnGeneratedBlock.query.filter(
        LearnGeneratedBlock.generated_block_bid == generated_block_bid,
        LearnGeneratedBlock.deleted == 0,
    ).first()
    if block is not None and not (block.generated_content or "").strip():
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
    moment a course moves back off the allowlist: 1.0 would resume the lesson seeing its own
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
    """Record the outline changes a finished lesson caused, so a reload agrees with the page.

    The browser is told about them as they happen, but a learner who comes back tomorrow is told
    by the database instead. Without this the chapter a learner watched tick over would be back
    to unfinished on their next visit, and the lesson they were handed on to would not know it
    had started.

    Chapters are included: a chapter's own record is what the outline reads its state from, and
    nothing else writes it on this path.

    The finished lesson's own record is found, never created. This runs in a transaction of its
    own, after the turn that finished the lesson has committed, and a reset can commit in the gap
    between the two. The reset marks every record of the lesson as reset; creating a fresh one
    here and marking it complete would hand the learner back the very completion they had just
    cleared, and carry them past the lesson they asked to retake. When no live record is left,
    nothing is written at all -- not the hand-over either, since the learner is not moving on --
    and False is returned so the caller does not report changes that were never made. Records
    for the lesson being handed to and for chapters may still be created: nothing else writes
    them on this path, and a reset does not touch them.
    """
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
            return False
        for update in updates:
            if update.outline_bid == outline_bid:
                record = lesson
            else:
                record = active_progress_record(
                    app,
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    outline_bid=update.outline_bid,
                )
            if update.status == LearnStatus.COMPLETED:
                record.status = LEARN_STATUS_COMPLETED
            elif record.status != LEARN_STATUS_COMPLETED:
                # A lesson already finished is not reopened by being handed to again: the learner
                # may be revisiting it, and reporting it unfinished would lose a completion.
                record.status = LEARN_STATUS_IN_PROGRESS
    return True
