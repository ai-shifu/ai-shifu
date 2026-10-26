"""Opaque memory keys survive shared rendering without application dependencies."""

import pytest
from markdown_flow import InteractionParser
from markdownflow import (
    InteractionSpec,
    Option,
    QuestionLabels,
    QuestionRenderer,
    UnrepresentableInteractionError,
)

_RENDERER = QuestionRenderer(
    QuestionLabels(continue_label="Proceed", free_text_placeholder="Your response")
)


@pytest.mark.parametrize(
    "variable",
    [
        "What is your gender?",
        "Which [path] | level//hint...?",
        "a}",
        "}",
        "outer{{inner",
        "Why <!--this-->?",
        "\ufeffname?\ufeff",
    ],
)
def test_renderer_preserves_the_complete_opaque_key(variable: str) -> None:
    spec = InteractionSpec(
        type="single",
        prompt="Choose one",
        variable=variable,
        options=[Option(display="A"), Option(display="B")],
    )
    rendered = _RENDERER.render_interaction(spec)
    assert rendered == "?[%{{ " + variable + " }} A | B]"
    assert InteractionParser().parse(rendered)["variable"] == variable
    assert _RENDERER.unrenderable_reason(spec) is None


@pytest.mark.parametrize("variable", ["", " \t\n", "\u0085\u001f\u3000"])
def test_legacy_blank_optional_keys_render_without_a_marker(variable: str) -> None:
    spec = InteractionSpec(
        type="single",
        prompt="Choose one",
        variable=variable,
        options=[Option(display="A")],
    )
    assert _RENDERER.render_interaction(spec) == "?[A]"
    assert spec.variable == variable


@pytest.mark.parametrize("variable", ["a\x00b", "a\nb", "a\u2028b", "x}}y"])
def test_renderer_rejects_keys_that_cannot_round_trip(variable: str) -> None:
    spec = InteractionSpec(
        type="single",
        prompt="Choose one",
        variable=variable,
        options=[Option(display="A")],
    )
    with pytest.raises(UnrepresentableInteractionError, match="Invalid variable name"):
        _RENDERER.render_interaction(spec)
    assert _RENDERER.unrenderable_reason(spec) == "Invalid variable name"


def test_host_labels_stay_explicit_for_opaque_named_text_input() -> None:
    spec = InteractionSpec(type="text", prompt="Explain", variable="Your goal?")
    rendered = _RENDERER.render_interaction(spec)
    parsed = InteractionParser().parse(rendered)
    assert parsed["variable"] == "Your goal?"
    assert parsed["question"] == "Your response"
