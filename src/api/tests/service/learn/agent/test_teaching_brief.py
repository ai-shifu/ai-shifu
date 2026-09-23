"""Cover the author's teaching brief reaching a 2.0 lesson the way a 1.0 lesson gets it.

`llm_system_prompt` is what an author writes about *how* a lesson should be taught -- who the
learner is, what voice to use, what to leave out. 1.0 has always applied it; 2.0 read it nowhere,
so a course moved across was taught in a voice its author never chose. 513 outline rows carry one.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from flaskr.service.learn.agent import lesson_entry

if TYPE_CHECKING:
    import pytest

_SYSTEM = (
    Path(__file__).resolve().parents[4]
    / "flaskr/service/learn/agent/engine/prompts/system.md"
).read_text()


class _Row:
    """One outline or course row, as much of it as the resolver reads."""

    def __init__(self, bid: str, brief: str = "", parent: str = "") -> None:
        """Build a row with an identifier, a brief, and the row above it."""
        self.outline_item_bid = bid
        self.llm_system_prompt = brief
        self.parent_bid = parent
        self.shifu_bid = "course"


def _resolve_brief(
    monkeypatch: pytest.MonkeyPatch,
    rows: dict[str, _Row],
    start: _Row,
    course: str = "",
) -> str:
    """Resolve a brief against an outline made of `rows`."""
    monkeypatch.setattr(
        lesson_entry, "_latest", lambda _m, **kw: rows.get(kw["outline_item_bid"])
    )
    return lesson_entry._teaching_brief(
        object, outline=start, shifu=_Row("course", course)
    )


def test_a_lesson_with_its_own_brief_uses_it(monkeypatch: pytest.MonkeyPatch) -> None:
    lesson = _Row("l1", "speak plainly", parent="ch1")
    rows = {"ch1": _Row("ch1", "speak formally")}
    assert _resolve_brief(monkeypatch, rows, lesson, "course voice") == "speak plainly"


def test_a_lesson_without_one_takes_its_chapter_s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A brief on a chapter covers the lessons inside it, which is where authors put them."""
    lesson = _Row("l1", "", parent="ch1")
    rows = {"ch1": _Row("ch1", "speak formally", parent="part1")}
    assert _resolve_brief(monkeypatch, rows, lesson, "course voice") == "speak formally"


def test_the_nearest_brief_wins_rather_than_all_of_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1.0 returns the first it finds and does not join them; two engines must agree."""
    lesson = _Row("l1", "", parent="ch1")
    rows = {
        "ch1": _Row("ch1", "chapter voice", parent="part1"),
        "part1": _Row("part1", "part voice"),
    }
    assert _resolve_brief(monkeypatch, rows, lesson, "course voice") == "chapter voice"


def test_the_course_brief_is_the_last_resort(monkeypatch: pytest.MonkeyPatch) -> None:
    lesson = _Row("l1", "", parent="ch1")
    rows = {"ch1": _Row("ch1", "", parent="part1"), "part1": _Row("part1", "")}
    assert _resolve_brief(monkeypatch, rows, lesson, "course voice") == "course voice"


def test_a_course_with_no_brief_anywhere_gets_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lesson = _Row("l1", "", parent="ch1")
    assert _resolve_brief(monkeypatch, {"ch1": _Row("ch1")}, lesson) == ""


def test_a_cycle_in_the_outline_does_not_hang_a_lesson(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bad data costs a few queries, never a lesson that will not start."""
    lesson = _Row("l1", "", parent="ch1")
    rows = {"ch1": _Row("ch1", "", parent="l1"), "l1": lesson}
    assert _resolve_brief(monkeypatch, rows, lesson, "course voice") == "course voice"


def test_whitespace_is_not_a_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    """An author who cleared the field left nothing, not a blank instruction."""
    lesson = _Row("l1", "   \n  ", parent="ch1")
    rows = {"ch1": _Row("ch1", "chapter voice")}
    assert _resolve_brief(monkeypatch, rows, lesson) == "chapter voice"


def test_the_brief_shapes_how_a_lesson_is_taught_not_what_it_teaches() -> None:
    """Said in the prompt, because the brief arrives as author text beside the script.

    The engine's own rules are what make it work at all; a brief that told it to stop asking
    questions would switch the tool protocol off if it carried equal weight.
    """
    rule = [
        line
        for line in _SYSTEM.splitlines()
        if re.match(r"^\d+\. .*<constraints>", line)
    ]
    assert len(rule) == 1, rule
    assert "It shapes how you teach" in rule[0]
    assert "it does not add to what you teach" in rule[0]
    assert "never overrides these rules" in rule[0]
