"""Cover what a finished 2.0 lesson writes to the progress records, against a real database.

The planner decides which outline items changed; this is the part that writes them down, so a
learner who reloads tomorrow sees what the stream told them today. Every test here runs through
SQLite and reads the rows back, because the run-agent tests replace this function with a stub.
"""

from __future__ import annotations

import uuid

import pytest
from flaskr.dao import db
from flaskr.service.learn.agent.lesson_record import apply_outline_progression
from flaskr.service.learn.learn_dtos import LearnStatus, OutlineItemUpdateDTO
from flaskr.service.learn.models import LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_RESET,
)

SHIFU = "course-a"
LESSON = "lesson-1"
NEXT = "lesson-2"
CHAPTER = "chapter-1"
NEXT_CHAPTER = "chapter-2"


@pytest.fixture
def learner(app: object) -> str:
    """Give each test a learner of its own, so rows never leak between tests."""
    identity = uuid.uuid4().hex
    yield identity
    with app.app_context():
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == identity
        ).delete()
        db.session.commit()


def _record(user_bid: str, outline_bid: str, status: int) -> None:
    record = LearnProgressRecord()
    record.progress_record_bid = uuid.uuid4().hex
    record.user_bid = user_bid
    record.shifu_bid = SHIFU
    record.outline_item_bid = outline_bid
    record.status = status
    record.block_position = 0
    db.session.add(record)


def _live_status(user_bid: str, outline_bid: str) -> int | None:
    record = (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .order_by(LearnProgressRecord.id.desc())
        .first()
    )
    return None if record is None else record.status


def _rows(user_bid: str, outline_bid: str) -> list[LearnProgressRecord]:
    return LearnProgressRecord.query.filter(
        LearnProgressRecord.user_bid == user_bid,
        LearnProgressRecord.outline_item_bid == outline_bid,
    ).all()


def _completed(bid: str, *, has_children: bool = False) -> OutlineItemUpdateDTO:
    return OutlineItemUpdateDTO(
        outline_bid=bid,
        title=bid,
        status=LearnStatus.COMPLETED,
        has_children=has_children,
    )


def _in_progress(bid: str, *, has_children: bool = False) -> OutlineItemUpdateDTO:
    return OutlineItemUpdateDTO(
        outline_bid=bid,
        title=bid,
        status=LearnStatus.IN_PROGRESS,
        has_children=has_children,
    )


def _apply(app: object, user_bid: str, updates: list[OutlineItemUpdateDTO]) -> bool:
    return apply_outline_progression(
        app,
        user_bid=user_bid,
        shifu_bid=SHIFU,
        outline_bid=LESSON,
        updates=updates,
    )


def test_the_finished_lesson_is_recorded_complete(app: object, learner: str) -> None:
    with app.app_context():
        _record(learner, LESSON, LEARN_STATUS_IN_PROGRESS)
        db.session.commit()

        assert _apply(app, learner, [_completed(LESSON)]) is True

        assert _live_status(learner, LESSON) == LEARN_STATUS_COMPLETED


def test_the_lesson_handed_to_is_recorded_as_started(app: object, learner: str) -> None:
    """The next lesson has no record yet; one is created so the outline knows it began."""
    with app.app_context():
        _record(learner, LESSON, LEARN_STATUS_IN_PROGRESS)
        db.session.commit()

        _apply(app, learner, [_completed(LESSON), _in_progress(NEXT)])

        assert _live_status(learner, LESSON) == LEARN_STATUS_COMPLETED
        assert _live_status(learner, NEXT) == LEARN_STATUS_IN_PROGRESS


def test_a_lesson_already_finished_is_not_reopened_by_being_handed_to(
    app: object, learner: str
) -> None:
    """The learner may be revisiting an earlier lesson; its completion must survive that."""
    with app.app_context():
        _record(learner, LESSON, LEARN_STATUS_IN_PROGRESS)
        _record(learner, NEXT, LEARN_STATUS_COMPLETED)
        db.session.commit()

        _apply(app, learner, [_completed(LESSON), _in_progress(NEXT)])

        assert _live_status(learner, NEXT) == LEARN_STATUS_COMPLETED


def test_chapters_get_records_of_their_own(app: object, learner: str) -> None:
    """The outline reads a chapter's state from the chapter's record; nothing else writes it."""
    with app.app_context():
        _record(learner, LESSON, LEARN_STATUS_IN_PROGRESS)
        db.session.commit()

        _apply(
            app,
            learner,
            [
                _completed(LESSON),
                _completed(CHAPTER, has_children=True),
                _in_progress(NEXT_CHAPTER, has_children=True),
                _in_progress(NEXT),
            ],
        )

        assert _live_status(learner, CHAPTER) == LEARN_STATUS_COMPLETED
        assert _live_status(learner, NEXT_CHAPTER) == LEARN_STATUS_IN_PROGRESS


def test_a_lesson_reset_after_its_turn_committed_is_not_completed_again(
    app: object, learner: str
) -> None:
    """The reset landed in the gap between the turn's commit and this write.

    Finding no live record used to mean creating one, and it was created already complete: the
    learner who had just asked to retake the lesson got its completion straight back, and was
    handed on to the next lesson as well. Now nothing is written and the caller is told so.
    """
    with app.app_context():
        _record(learner, LESSON, LEARN_STATUS_RESET)
        db.session.commit()

        assert _apply(app, learner, [_completed(LESSON), _in_progress(NEXT)]) is False

        assert _live_status(learner, LESSON) is None
        assert len(_rows(learner, LESSON)) == 1
        assert _rows(learner, NEXT) == []


def test_a_lesson_with_no_record_at_all_is_not_invented(
    app: object, learner: str
) -> None:
    """Same gap, older data: a lesson the reset deleted outright rather than marked."""
    with app.app_context():
        assert _apply(app, learner, [_completed(LESSON)]) is False

        assert _rows(learner, LESSON) == []
