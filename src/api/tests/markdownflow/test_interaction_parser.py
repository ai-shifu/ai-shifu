"""Both binding forms share the syntax parser's existing option grammar."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import pytest
from markdownflow import InteractionParser, InteractionSpec, Option

if TYPE_CHECKING:
    from flask import Flask

_BODIES = [
    "...Your answer",
    "A | B",
    "A | B | ...Other",
    "A || B",
    "A || B || ...Other",
]


def _normalized_parse(parsed: dict[str, Any]) -> dict[str, Any]:
    if parsed.get("type") is not None:
        parsed["type"] = parsed["type"].value
    return parsed


@pytest.mark.parametrize("body", _BODIES)
@pytest.mark.parametrize("marker", ["{{goal}}", "%{{goal}}"])
@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_both_bindings_keep_all_five_control_shapes(
    body: str, marker: str, newline: str
) -> None:
    expected = _normalized_parse(InteractionParser().parse("?[%{{goal}} " + body + "]"))
    source = "?[ \t" + marker + newline + body + "]"
    assert _normalized_parse(InteractionParser().parse(source)) == expected


_A_B = [{"display": "A", "value": "A"}, {"display": "B", "value": "B"}]


# Pinned to the results before standard bindings were added.
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "?[A | B]",
            {
                "type": "non_assignment_button",
                "buttons": _A_B,
                "is_multi_select": False,
            },
        ),
        (
            "?[A || B]",
            {"type": "non_assignment_button", "buttons": _A_B, "is_multi_select": True},
        ),
        (
            "?[...Other]",
            {
                "type": "non_assignment_button",
                "buttons": [],
                "question": "Other",
                "is_multi_select": False,
            },
        ),
        (
            r"?[%{{goal}} A\|B//first | C\]D//second | ...Other]",
            {
                "type": "buttons_with_text",
                "variable": "goal",
                "buttons": [
                    {"display": "A|B", "value": "first"},
                    {"display": "C]D", "value": "second"},
                ],
                "question": "Other",
                "is_multi_select": False,
            },
        ),
        (
            "?[%{{ Which [path] | level//hint...? }} A | B]",
            {
                "type": "buttons_only",
                "variable": "Which [path] | level//hint...?",
                "buttons": _A_B,
                "is_multi_select": False,
            },
        ),
        (
            "?[%{{ a} }} A | B]",
            {
                "type": "buttons_only",
                "variable": "a}",
                "buttons": _A_B,
                "is_multi_select": False,
            },
        ),
        (
            "?[Read {{goal}} | Continue]",
            {
                "type": "non_assignment_button",
                "buttons": [
                    {"display": "Read {{goal}}", "value": "Read {{goal}}"},
                    {"display": "Continue", "value": "Continue"},
                ],
                "is_multi_select": False,
            },
        ),
        (
            r"\?[%{{goal}} A | B]",
            {
                "type": None,
                "error": r"Invalid interaction format: \?[%{{goal}} A | B]",
            },
        ),
    ],
)
def test_existing_legacy_and_unassigned_controls_keep_their_contract(
    source: str, expected: dict[str, Any]
) -> None:
    assert _normalized_parse(InteractionParser().parse(source)) == expected


def test_the_package_and_syntax_layer_share_one_parser() -> None:
    from markdownflow.syntax import InteractionParser as SyntaxInteractionParser

    assert InteractionParser is SyntaxInteractionParser


@pytest.mark.parametrize("marker", ["{{", "%{{"])
@pytest.mark.parametrize("name", ["", " \t ", "a\nb", "a\x00b"])
def test_invalid_names_keep_the_syntax_parser_error(marker: str, name: str) -> None:
    parsed = InteractionParser().parse("?[" + marker + name + "}} A | B]")
    assert parsed["type"] is None
    assert "Invalid variable name" in parsed["error"]


@pytest.mark.parametrize("marker", ["{{goal}}", "%{{goal}}"])
@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_profile_document_and_authored_contract_keep_the_answer_binding(
    app: Flask, marker: str, newline: str
) -> None:
    from flaskr.service.profile_research.authored_interaction import (
        check_authored_interaction,
    )
    from flaskr.service.profile_research.document import (
        validate_profile_research_document,
    )

    source = "?[" + marker + newline + "A | B]"
    metadata = validate_profile_research_document(source)
    assert metadata["variables"] == ["goal"]
    assert metadata["interaction_block_count"] == 1
    spec = InteractionSpec(
        type="single",
        prompt="Choose",
        variable="goal",
        options=[Option(display="A"), Option(display="B")],
    )
    with app.app_context():
        assert check_authored_interaction(spec, source, {"goal": "old"}) is None
        assert (
            check_authored_interaction(
                spec.model_copy(update={"variable": "wrong"}), source, {"goal": "old"}
            )
            is not None
        )


@pytest.mark.parametrize("standard", [False, True])
@pytest.mark.parametrize("kind", ["single", "text"])
def test_history_matches_equivalent_bindings_but_rejects_changed_controls(
    app: Flask, standard: bool, kind: Literal["single", "text"]
) -> None:
    from flaskr.api.markdownflow import render_interaction
    from flaskr.service.learn.agent.interaction_history import _matches_control

    spec = InteractionSpec(
        type=kind,
        prompt="Choose",
        variable="goal",
        options=[Option(display="A"), Option(display="B")] if kind == "single" else [],
    )
    with app.app_context():
        content = render_interaction(spec)
        if standard:
            content = content.replace("%{{", "{{", 1)
        assert _matches_control(spec, content)
        assert not _matches_control(
            spec.model_copy(update={"variable": "wrong"}), content
        )
        if kind == "single":
            assert not _matches_control(spec, content.replace("A", "Other", 1))
