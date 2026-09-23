"""Cover reading the outline a finished 2.0 lesson is advanced through, against a real database.

The planner is tested on a tree alone; this is the part that builds that tree from the course
tables, and the run-agent tests replace it with a stub. What matters here is *which rows* it
reads: the structure names the exact row each outline item was built from, and one bid can have
several rows kept at once.
"""

from __future__ import annotations

import uuid

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.learn_dtos import LearnStatus
from flaskr.service.learn.learn_funcs import resolve_outline_progression
from flaskr.service.shifu.consts import UNIT_TYPE_VALUE_NORMAL
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    LogDraftStruct,
    LogPublishedStruct,
    PublishedOutlineItem,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem

CHAPTER = "chapter-1"
LESSON = "lesson-1"
NEXT = "lesson-2"


@pytest.fixture
def course(app: object) -> str:
    """Give each test a course of its own, and clear its rows afterwards."""
    identity = uuid.uuid4().hex
    yield identity
    with app.app_context(), unit_of_work():
        for model in (
            PublishedOutlineItem,
            DraftOutlineItem,
            LogPublishedStruct,
            LogDraftStruct,
        ):
            model.query.filter(model.shifu_bid == identity).delete()


def _outline_row(
    model: type,
    shifu_bid: str,
    bid: str,
    *,
    title: str,
    hidden: bool = False,
) -> int:
    """Insert one outline row and return its id, which is what the structure refers to."""
    row = model(
        shifu_bid=shifu_bid,
        outline_item_bid=bid,
        title=title,
        hidden=int(hidden),
        content="",
        type=UNIT_TYPE_VALUE_NORMAL,
        position=0,
    )
    db.session.add(row)
    db.session.flush()
    return row.id


def _structure(shifu_bid: str, chapter_id: int, lessons: dict[str, int]) -> str:
    """Build the structure the way the course service stores it: one row id per node."""
    return HistoryItem(
        bid=shifu_bid,
        id=0,
        type="shifu",
        children=[
            HistoryItem(
                bid=CHAPTER,
                id=chapter_id,
                type="outline",
                children=[
                    HistoryItem(bid=bid, id=row_id, type="outline", children=[])
                    for bid, row_id in lessons.items()
                ],
            )
        ],
    ).to_json()


def _store_structure(model: type, shifu_bid: str, struct: str) -> None:
    db.session.add(
        model(struct_bid=uuid.uuid4().hex, shifu_bid=shifu_bid, struct=struct)
    )


def _resolve(app: object, shifu_bid: str, *, preview_mode: bool = False) -> list:
    updates = resolve_outline_progression(
        app, shifu_bid=shifu_bid, outline_bid=LESSON, preview_mode=preview_mode
    )
    return [(u.outline_bid, u.status, u.title) for u in updates]


def test_the_row_the_structure_names_is_read_not_the_latest_row_for_the_bid(
    app: object, course: str
) -> None:
    """Two rows share the lesson's bid; only the one the structure points at was served.

    Publishing writes a fresh row per node and a draft clone carries the bid over, so asking by
    bid can answer from a revision the learner never saw. The structure resolves the ambiguity.
    """
    with app.app_context(), unit_of_work():
        chapter = _outline_row(PublishedOutlineItem, course, CHAPTER, title="Chapter")
        served = _outline_row(
            PublishedOutlineItem, course, LESSON, title="Served", hidden=False
        )
        # Newer row, same bid: what a lookup by bid would pick, and not what was served.
        _outline_row(PublishedOutlineItem, course, LESSON, title="Later", hidden=True)
        following = _outline_row(PublishedOutlineItem, course, NEXT, title="Next")
        _store_structure(
            LogPublishedStruct,
            course,
            _structure(course, chapter, {LESSON: served, NEXT: following}),
        )

    with app.app_context():
        assert _resolve(app, course) == [
            (LESSON, LearnStatus.COMPLETED, "Served"),
            (NEXT, LearnStatus.IN_PROGRESS, "Next"),
        ]


def test_the_older_row_is_read_when_that_is_the_one_the_structure_names(
    app: object, course: str
) -> None:
    """The mirror image: the structure points at the older row, so its title and flag win."""
    with app.app_context(), unit_of_work():
        chapter = _outline_row(PublishedOutlineItem, course, CHAPTER, title="Chapter")
        _outline_row(PublishedOutlineItem, course, LESSON, title="Unserved")
        served = _outline_row(PublishedOutlineItem, course, LESSON, title="Served")
        following = _outline_row(
            PublishedOutlineItem, course, NEXT, title="Hidden next", hidden=True
        )
        # A newer row for the next lesson says visible; the served one says hidden.
        _outline_row(PublishedOutlineItem, course, NEXT, title="Visible next")
        _store_structure(
            LogPublishedStruct,
            course,
            _structure(course, chapter, {LESSON: served, NEXT: following}),
        )

    with app.app_context():
        # The next lesson is hidden in the served revision, so there is no hand-over, and the
        # chapter closes behind the learner.
        assert _resolve(app, course) == [
            (LESSON, LearnStatus.COMPLETED, "Served"),
            (CHAPTER, LearnStatus.COMPLETED, "Chapter"),
        ]


def test_a_preview_reads_the_draft_outline(app: object, course: str) -> None:
    """The author previews the draft, not the published course."""
    with app.app_context(), unit_of_work():
        chapter = _outline_row(DraftOutlineItem, course, CHAPTER, title="Draft chapter")
        lesson = _outline_row(DraftOutlineItem, course, LESSON, title="Draft lesson")
        _store_structure(
            LogDraftStruct, course, _structure(course, chapter, {LESSON: lesson})
        )

    with app.app_context():
        assert _resolve(app, course, preview_mode=True) == [
            (LESSON, LearnStatus.COMPLETED, "Draft lesson"),
            (CHAPTER, LearnStatus.COMPLETED, "Draft chapter"),
        ]
        assert _resolve(app, course) == []


def test_a_course_with_no_published_structure_changes_nothing(
    app: object, course: str
) -> None:
    with app.app_context():
        assert _resolve(app, course) == []
