"""Verify authored profile controls cannot drift while their labels are localized."""

from __future__ import annotations

from typing import Any

import pytest
from flaskr.service.learn.agent.api import InteractionSpec
from flaskr.service.profile_research.authored_interaction import (
    check_authored_interaction,
)


def _spec(
    kind: str,
    values: list[str] | None = None,
    *,
    variable: str | None = None,
    prompt: str = "Localized question",
) -> InteractionSpec:
    data: dict[str, Any] = {
        "type": kind,
        "prompt": prompt,
        "variable": variable,
        "placeholder": "Localized input hint",
    }
    if values is not None:
        data["options"] = [
            {"display": f"Localized label {index}", "value": value}
            for index, value in enumerate(values)
        ]
    return InteractionSpec.model_validate(data)


@pytest.mark.parametrize(
    ("source", "spec"),
    [
        (
            "?[%{{role}} Teacher//teacher | Student//student]",
            _spec("single", ["teacher", "student"], variable="role"),
        ),
        ("?[Teacher | Student]", _spec("single", ["Teacher", "Student"])),
        (
            "?[%{{topics}} AI//ai || Systems//systems]",
            _spec("multi", ["ai", "systems"], variable="topics"),
        ),
        ("?[AI//ai || Systems//systems]", _spec("multi", ["ai", "systems"])),
        ("?[%{{goal}}...Your goal?]", _spec("text", variable="goal")),
        ("?[...Your goal?]", _spec("text")),
        (
            "?[%{{role}} Teacher//teacher | ...Other role]",
            _spec("single_or_text", ["teacher"], variable="role"),
        ),
        ("?[Teacher//teacher | ...Other role]", _spec("single_or_text", ["teacher"])),
        (
            "?[%{{topics}} AI//ai || Systems//systems || ...Other topic]",
            _spec("multi_or_text", ["ai", "systems"], variable="topics"),
        ),
        (
            "?[AI//ai || Systems//systems || ...Other topic]",
            _spec("multi_or_text", ["ai", "systems"]),
        ),
        ("?[%{{confirmed}} Yes//yes]", _spec("single", ["yes"], variable="confirmed")),
        ("?[继续]", _spec("single", ["继续"])),
        ("?[继续]", _spec("confirm", prompt="")),
        ("?[继续]", _spec("confirm", prompt="我准备好了")),
        ("?[准备好了//continue]", _spec("confirm", prompt="")),
        ("?[准备好了//advance]", _spec("confirm", ["advance"], prompt="")),
        (
            r"?[a\|b | wait\.\.\. | https:\/\/example.org]",
            _spec("single", ["a|b", "wait...", "https://example.org"]),
        ),
    ],
)
def test_authored_contract_allows_localized_display_text(
    source: str, spec: InteractionSpec
) -> None:
    assert check_authored_interaction(spec, source, {}) is None


@pytest.mark.parametrize(
    ("source", "spec"),
    [
        ("?[Teacher//teacher | Student//student]", _spec("single", ["teacher"])),
        ("?[Teacher//teacher]", _spec("single", ["teacher", "student"])),
        (
            "?[Teacher//teacher | Student//student]",
            _spec("single", ["student", "teacher"]),
        ),
        (
            "?[Teacher//teacher | Student//student]",
            _spec("single", ["teacher", "localized-student"]),
        ),
        ("?[Teacher | Student]", _spec("single", ["老师", "学生"])),
        (
            "?[%{{role}} Teacher//teacher]",
            _spec("single", ["teacher"], variable="other"),
        ),
        ("?[%{{role}} Teacher//teacher]", _spec("single", ["teacher"])),
        ("?[Teacher//teacher]", _spec("single", ["teacher"], variable="role")),
        ("?[%{{role}} Teacher//teacher]", _spec("confirm", ["teacher"], prompt="")),
        ("?[Teacher | Student]", _spec("multi", ["Teacher", "Student"])),
        ("?[Teacher || Student]", _spec("single", ["Teacher", "Student"])),
        ("?[...Your goal?]", _spec("single_or_text", ["invented"])),
        ("?[Teacher | ...Other role]", _spec("single", ["Teacher"])),
        ("?[Teacher || ...Other roles]", _spec("single_or_text", ["Teacher"])),
        ("?[Teacher]", _spec("single_or_text", ["Teacher"])),
        ("?[Teacher | Student]", _spec("confirm", prompt="")),
        ("?[准备好了//advance]", _spec("confirm", prompt="")),
        ("?[准备好了//advance]", _spec("confirm", ["advance"], prompt="继续")),
        ("?[继续//继续]", _spec("confirm", prompt="")),
    ],
)
def test_authored_contract_rejects_changed_answer_meaning(
    source: str, spec: InteractionSpec
) -> None:
    assert check_authored_interaction(spec, source, {})


def test_authored_contract_substitutes_reads_and_preserves_binding() -> None:
    source = "?[%{{role}} {{label}}//{{stored_role}} | Student//student]"
    spec = _spec("single", ["teacher", "student"], variable="role")

    assert (
        check_authored_interaction(
            spec,
            source,
            {"role": "old-answer", "label": "Teacher", "stored_role": "teacher"},
        )
        is None
    )


def test_authored_contract_keeps_escaped_slashes_literal_for_confirm() -> None:
    assert (
        check_authored_interaction(
            _spec("confirm", prompt=""), r"?[https:\/\/example.org]", {}
        )
        is None
    )


def test_authored_contract_refuses_an_unparseable_source() -> None:
    assert check_authored_interaction(_spec("text"), "not an interaction", {})
