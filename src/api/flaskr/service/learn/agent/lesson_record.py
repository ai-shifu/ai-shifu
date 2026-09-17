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


def stage_turn_block(
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    progress_record_bid: str,
    generated_block_bid: str,
    position: int,
) -> LearnGeneratedBlock:
    """Record this turn as one generated block, so its elements can be found again.

    The element pipeline reads `progress_record_bid` off this row; history retrieval walks from the
    progress record to its blocks and admits the elements hanging off them. Without it the stream
    still reaches the learner and disappears on the next page load.
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
    block.generated_content = ""
    block.status = 1
    block.block_content_conf = ""
    block.position = position
    db.session.add(block)
    return block
