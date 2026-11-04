"""Keep the course teaching instructions consistent across every lesson."""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from flaskr.service.learn.agent import lesson_entry
from markdownflow.engine import Prompts

_SYSTEM = Prompts.default().base


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("course voice", "course voice"),
        ("  course voice\n", "course voice"),
        (" \n", ""),
        (None, ""),
    ],
)
def test_teaching_brief_uses_the_course_prompt(
    prompt: str | None, expected: str
) -> None:
    assert (
        lesson_entry._teaching_brief(SimpleNamespace(llm_system_prompt=prompt))
        == expected
    )


def test_missing_course_prompt_produces_no_teaching_brief() -> None:
    assert lesson_entry._teaching_brief(SimpleNamespace()) == ""


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
