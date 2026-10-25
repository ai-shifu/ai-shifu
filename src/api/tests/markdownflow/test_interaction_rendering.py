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
    "question",
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
def test_renderer_preserves_the_complete_opaque_key(question: str) -> None:
    spec = InteractionSpec(
        type="single",
        prompt="Choose one",
        question=question,
        options=[Option(display="A"), Option(display="B")],
    )
    rendered = _RENDERER.render_interaction(spec)
    assert rendered == "?[%{{ " + question + " }} A | B]"
    assert InteractionParser().parse(rendered)["variable"] == question
    assert _RENDERER.unrenderable_reason(spec) is None


@pytest.mark.parametrize("question", ["", " \t\n", "\u0085\u001f\u3000"])
def test_legacy_blank_optional_keys_render_without_a_marker(question: str) -> None:
    spec = InteractionSpec(
        type="single",
        prompt="Choose one",
        question=question,
        options=[Option(display="A")],
    )
    assert _RENDERER.render_interaction(spec) == "?[A]"
    assert spec.question == question


@pytest.mark.parametrize("question", ["a\x00b", "a\nb", "a\u2028b", "x}}y"])
def test_renderer_rejects_keys_that_cannot_round_trip(question: str) -> None:
    spec = InteractionSpec(
        type="single",
        prompt="Choose one",
        question=question,
        options=[Option(display="A")],
    )
    with pytest.raises(UnrepresentableInteractionError, match="Invalid question text"):
        _RENDERER.render_interaction(spec)
    assert _RENDERER.unrenderable_reason(spec) == "Invalid question text"


def test_host_labels_stay_explicit_for_opaque_named_text_input() -> None:
    spec = InteractionSpec(type="text", prompt="Explain", question="Your goal?")
    rendered = _RENDERER.render_interaction(spec)
    parsed = InteractionParser().parse(rendered)
    assert parsed["variable"] == "Your goal?"
    assert parsed["question"] == "Your response"
