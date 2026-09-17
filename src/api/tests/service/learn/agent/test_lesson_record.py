"""Cover the records a 2.0 turn leaves behind, against a real database.

A lesson taught by the engine has to appear where the rest of the product looks: history retrieval
starts from a `LearnProgressRecord` and reaches elements through a `LearnGeneratedBlock`. The same
record is what tells a turn its lesson was reset while it ran.
"""

from __future__ import annotations

from flaskr.dao import db
from flaskr.service.learn.agent import lesson_record
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import LEARN_STATUS_RESET

USER = "learner-1"
SHIFU = "course-a"
OUTLINE = "outline-1"


def _clean() -> None:
    LearnProgressRecord.query.delete()
    LearnGeneratedBlock.query.delete()
    db.session.commit()


def _resolve() -> LearnProgressRecord:
    return lesson_record.active_progress_record(
        None, user_bid=USER, shifu_bid=SHIFU, outline_bid=OUTLINE
    )


def test_a_new_lesson_gets_a_progress_record(app: object) -> None:
    with app.app_context():
        _clean()
        record = _resolve()
        db.session.commit()

        assert record.progress_record_bid
        assert record.user_bid == USER
        assert record.outline_item_bid == OUTLINE
        _clean()


def test_a_lesson_already_under_way_keeps_its_record(app: object) -> None:
    """A second turn must hang off the same record, or its history splits in two."""
    with app.app_context():
        _clean()
        first = _resolve()
        db.session.commit()
        second = _resolve()
        db.session.commit()

        assert second.progress_record_bid == first.progress_record_bid
        _clean()


def test_a_reset_lesson_starts_a_new_record(app: object) -> None:
    with app.app_context():
        _clean()
        before = _resolve()
        before_bid = before.progress_record_bid
        before.status = LEARN_STATUS_RESET
        db.session.commit()

        after = _resolve()
        db.session.commit()

        assert after.progress_record_bid != before_bid
        _clean()


def test_a_turn_can_tell_its_lesson_was_reset_while_it_ran(app: object) -> None:
    """A first turn holds no session row yet, so this is what lets it decline to write itself."""
    with app.app_context():
        _clean()
        record = _resolve()
        bid = record.progress_record_bid
        db.session.commit()

        assert (
            lesson_record.was_reset_since(
                user_bid=USER,
                shifu_bid=SHIFU,
                outline_bid=OUTLINE,
                progress_record_bid=bid,
            )
            is False
        )

        record.status = LEARN_STATUS_RESET
        db.session.commit()

        assert (
            lesson_record.was_reset_since(
                user_bid=USER,
                shifu_bid=SHIFU,
                outline_bid=OUTLINE,
                progress_record_bid=bid,
            )
            is True
        )
        _clean()


def test_a_turn_block_carries_the_progress_record_the_elements_need(
    app: object,
) -> None:
    """The element pipeline reads this off the block; without it the elements are unreachable."""
    with app.app_context():
        _clean()
        lesson_record.stage_turn_block(
            user_bid=USER,
            shifu_bid=SHIFU,
            outline_bid=OUTLINE,
            progress_record_bid="progress-1",
            generated_block_bid="block-1",
            position=0,
        )
        db.session.commit()

        stored = LearnGeneratedBlock.query.filter_by(
            generated_block_bid="block-1"
        ).first()
        assert stored is not None
        assert stored.progress_record_bid == "progress-1"
        assert stored.user_bid == USER
        assert stored.outline_item_bid == OUTLINE
        _clean()
