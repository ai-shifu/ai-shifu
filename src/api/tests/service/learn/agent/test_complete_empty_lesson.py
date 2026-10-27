"""Complete a lesson with no script the way 1.0 finished one, against a real database."""

from __future__ import annotations

import uuid

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn.agent.lesson_entry import complete_empty_lesson
from flaskr.service.learn.exceptions import PaidError
from flaskr.service.learn.learn_dtos import GeneratedType, LearnStatus
from flaskr.service.learn.models import LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    LogPublishedStruct,
    PublishedOutlineItem,
    PublishedShifu,
)

from tests.service.learn.test_resolve_outline_progression import (
    CHAPTER,
    LESSON,
    NEXT,
    _outline_row,
    _store_structure,
    _structure,
    course,  # noqa: F401 - pytest fixture
)


def _publish(shifu_bid: str, *, price: int = 0) -> None:
    """Publish a chapter whose first lesson is empty, followed by another lesson."""
    with unit_of_work():
        db.session.add(PublishedShifu(shifu_bid=shifu_bid, price=price))
        chapter = _outline_row(PublishedOutlineItem, shifu_bid, CHAPTER, title="Ch")
        lesson = _outline_row(PublishedOutlineItem, shifu_bid, LESSON, title="Empty")
        following = _outline_row(PublishedOutlineItem, shifu_bid, NEXT, title="Next")
        _store_structure(
            LogPublishedStruct,
            shifu_bid,
            _structure(shifu_bid, chapter, {LESSON: lesson, NEXT: following}),
        )


def _complete(
    app: object, shifu_bid: str, learner: str, *, preview: bool = False
) -> list:
    return list(
        complete_empty_lesson(
            app,
            user_bid=learner,
            shifu_bid=shifu_bid,
            outline_bid=LESSON,
            preview_mode=preview,
        )
    )


def _records(shifu_bid: str, learner: str) -> dict[str, int]:
    return {
        row.outline_item_bid: row.status
        for row in LearnProgressRecord.query.filter_by(
            shifu_bid=shifu_bid, user_bid=learner, deleted=0
        )
    }


def test_an_empty_lesson_is_completed_and_hands_on_to_the_next(
    app: object,
    course: str,  # noqa: F811 - pytest fixture
) -> None:
    learner = uuid.uuid4().hex
    with app.app_context():
        _publish(course)
        events = _complete(app, course, learner)

        updates = {
            event.content.outline_bid: event.content.status
            for event in events
            if event.type == GeneratedType.OUTLINE_ITEM_UPDATE
        }
        assert updates[LESSON] == LearnStatus.COMPLETED
        assert updates[NEXT] == LearnStatus.IN_PROGRESS
        assert [e.type for e in events][-1] == GeneratedType.INTERACTION
        records = _records(course, learner)
        assert records[LESSON] == LEARN_STATUS_COMPLETED
        assert records[NEXT] == LEARN_STATUS_IN_PROGRESS


def test_an_unbought_paid_lesson_is_not_completed(
    app: object,
    course: str,  # noqa: F811 - pytest fixture
) -> None:
    learner = uuid.uuid4().hex
    with app.app_context():
        _publish(course, price=10)
        with pytest.raises(PaidError):
            _complete(app, course, learner)
        assert _records(course, learner) == {}


def test_a_preview_changes_no_progress(
    app: object,
    course: str,  # noqa: F811 - pytest fixture
) -> None:
    learner = uuid.uuid4().hex
    with app.app_context():
        _publish(course)
        with unit_of_work():
            _outline_row(DraftOutlineItem, course, LESSON, title="Draft")
        assert _complete(app, course, learner, preview=True) == []
        assert _records(course, learner) == {}


def test_a_missing_lesson_is_reported_not_completed(
    app: object,
    course: str,  # noqa: F811 - pytest fixture
) -> None:
    learner = uuid.uuid4().hex
    with app.app_context():
        _publish(course)
        with unit_of_work():
            PublishedOutlineItem.query.filter_by(
                shifu_bid=course, outline_item_bid=LESSON
            ).update({"deleted": 1})
        with pytest.raises(AppError) as error:
            _complete(app, course, learner)
        assert error.value.code == ERROR_CODE["server.shifu.lessonNotFoundInCourse"]
        assert _records(course, learner) == {}


def test_reopening_a_completed_empty_lesson_replays_nothing(
    app: object,
    course: str,  # noqa: F811 - pytest fixture
) -> None:
    learner = uuid.uuid4().hex
    with app.app_context():
        _publish(course)
        assert _complete(app, course, learner)
        records = _records(course, learner)

        assert _complete(app, course, learner) == []
        assert _records(course, learner) == records
