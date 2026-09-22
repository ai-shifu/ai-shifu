"""Cover which outline items change state when a 2.0 lesson ends.

A 2.0 lesson sent no outline updates at all, so a learner who finished one saw the lesson still
described as unfinished and the page went on asking for a continuation that did not exist. These
cover the decision that drives those updates, against an outline alone.
"""

from __future__ import annotations

import pytest
from flaskr.service.learn.agent.outline_progression import plan_lesson_completion
from flaskr.service.learn.learn_dtos import LearnStatus
from flaskr.service.shifu.shifu_history_manager import HistoryItem


def _lesson(bid: str) -> HistoryItem:
    """Build a leaf: a lesson, whose children are blocks rather than outline items."""
    return HistoryItem(bid=bid, id=0, type="outline", children=[])


def _chapter(bid: str, lessons: list[HistoryItem]) -> HistoryItem:
    return HistoryItem(bid=bid, id=0, type="outline", children=lessons)


# Two chapters of two lessons each, the shape of a real course.
COURSE = _chapter(
    "course",
    [
        _chapter("ch1", [_lesson("l1"), _lesson("l2")]),
        _chapter("ch2", [_lesson("l3"), _lesson("l4")]),
    ],
)
VISIBLE = dict.fromkeys(("ch1", "ch2", "l1", "l2", "l3", "l4"), False)
TITLES = {bid: bid.upper() for bid in VISIBLE}


def _plan(outline_bid: str, hidden: dict[str, bool] | None = None) -> list[tuple]:
    updates = plan_lesson_completion(
        COURSE, outline_bid, hidden if hidden is not None else VISIBLE, TITLES
    )
    return [(u.outline_bid, u.status, u.has_children) for u in updates]


def test_a_lesson_with_another_after_it_hands_over_to_it() -> None:
    assert _plan("l1") == [
        ("l1", LearnStatus.COMPLETED, False),
        ("l2", LearnStatus.IN_PROGRESS, False),
    ]


def test_the_last_lesson_of_a_chapter_finishes_the_chapter_with_it() -> None:
    """The sidebar never ticked a chapter off, because only its lessons were ever reported."""
    assert _plan("l2") == [
        ("l2", LearnStatus.COMPLETED, False),
        ("ch1", LearnStatus.COMPLETED, True),
        ("ch2", LearnStatus.IN_PROGRESS, True),
        ("l3", LearnStatus.IN_PROGRESS, False),
    ]


def test_the_last_lesson_of_the_course_completes_without_handing_over() -> None:
    """There is nothing after it; the completions still stand."""
    assert _plan("l4") == [
        ("l4", LearnStatus.COMPLETED, False),
        ("ch2", LearnStatus.COMPLETED, True),
    ]


def test_a_hidden_lesson_is_never_handed_over_to() -> None:
    """Hidden items are not in the outline the learner was served."""
    hidden = {**VISIBLE, "l2": True}
    assert _plan("l1", hidden) == [
        ("l1", LearnStatus.COMPLETED, False),
        ("ch1", LearnStatus.COMPLETED, True),
        ("ch2", LearnStatus.IN_PROGRESS, True),
        ("l3", LearnStatus.IN_PROGRESS, False),
    ]


def test_an_item_missing_from_the_outline_counts_as_hidden() -> None:
    """Absence is not permission: advancing onto something never served would be worse."""
    partial = {"ch1": False, "l1": False, "l2": False}
    assert _plan("l2", partial) == [
        ("l2", LearnStatus.COMPLETED, False),
        ("ch1", LearnStatus.COMPLETED, True),
    ]


def test_a_lesson_the_outline_does_not_contain_changes_nothing() -> None:
    assert _plan("nowhere") == []


@pytest.mark.parametrize("bid", ["l1", "l2", "l3", "l4"])
def test_the_lesson_that_ended_is_always_the_first_thing_reported(bid: str) -> None:
    """Its own completion is what the browser reads to stop asking for more."""
    plan = _plan(bid)
    assert plan[0] == (bid, LearnStatus.COMPLETED, False)


def test_a_chapter_with_nothing_visible_in_it_is_stepped_over() -> None:
    """A chapter holding no reachable lesson is not somewhere a learner can be handed to.

    Stepping from one sibling to the next stopped at such a chapter and named it as the thing to
    go to, so the lessons after it never came up and the learner was handed nowhere.
    """
    course = _chapter(
        "course",
        [
            _chapter("ch1", [_lesson("l1")]),
            _chapter("empty", [_lesson("h1"), _lesson("h2")]),
            _chapter("ch3", [_lesson("l5")]),
        ],
    )
    hidden = {
        **dict.fromkeys(("ch1", "empty", "ch3", "l1", "l5"), False),
        "h1": True,
        "h2": True,
    }
    plan = plan_lesson_completion(course, "l1", hidden, {})
    assert [(u.outline_bid, u.status) for u in plan] == [
        ("l1", LearnStatus.COMPLETED),
        ("ch1", LearnStatus.COMPLETED),
        ("ch3", LearnStatus.IN_PROGRESS),
        ("l5", LearnStatus.IN_PROGRESS),
    ]


def test_chapters_close_from_the_inside_out_and_open_from_the_outside_in() -> None:
    """A lesson ends its own chapter before the part holding that chapter, and the reverse after.

    The browser applies these in the order they arrive, so a chapter opened before the part it
    sits in would be shown inside something still described as untouched.
    """
    course = _chapter(
        "course",
        [
            _chapter("partA", [_chapter("ch1", [_lesson("l1")])]),
            _chapter("partB", [_chapter("ch2", [_lesson("l2")])]),
        ],
    )
    hidden = dict.fromkeys(
        ("partA", "partB", "ch1", "ch2", "l1", "l2"),
        False,
    )
    plan = plan_lesson_completion(course, "l1", hidden, {})
    assert [(u.outline_bid, u.status) for u in plan] == [
        ("l1", LearnStatus.COMPLETED),
        ("ch1", LearnStatus.COMPLETED),
        ("partA", LearnStatus.COMPLETED),
        ("partB", LearnStatus.IN_PROGRESS),
        ("ch2", LearnStatus.IN_PROGRESS),
        ("l2", LearnStatus.IN_PROGRESS),
    ]


def test_a_lesson_hidden_while_being_studied_still_hands_over_to_the_next() -> None:
    """The author hid the lesson the learner was in; the learner still finishes it.

    Looking the ended lesson up among the visible ones found nothing, so nobody was handed
    anywhere and the chapter was closed over a lesson the learner had not reached.
    """
    course = _chapter(
        "course", [_chapter("ch1", [_lesson("l1"), _lesson("l2"), _lesson("l3")])]
    )
    hidden = {**dict.fromkeys(("ch1", "l1", "l3"), False), "l2": True}
    plan = plan_lesson_completion(course, "l2", hidden, {})
    assert [(u.outline_bid, u.status) for u in plan] == [
        ("l2", LearnStatus.COMPLETED),
        ("l3", LearnStatus.IN_PROGRESS),
    ]


def test_a_lesson_hidden_with_its_whole_chapter_moves_on_to_the_next_chapter() -> None:
    """A hidden chapter is nowhere to stay; the next visible lesson is in the chapter after."""
    hidden = {**VISIBLE, "ch1": True, "l2": True}
    assert _plan("l2", hidden) == [
        ("l2", LearnStatus.COMPLETED, False),
        ("ch1", LearnStatus.COMPLETED, True),
        ("ch2", LearnStatus.IN_PROGRESS, True),
        ("l3", LearnStatus.IN_PROGRESS, False),
    ]
