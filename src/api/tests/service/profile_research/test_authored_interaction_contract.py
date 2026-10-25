"""Validate the confirmation values the learner actually receives."""

import pytest
from flaskr.api.markdownflow import InteractionSpec, Option, render_question
from flaskr.service.profile_research.authored_interaction import (
    check_authored_interaction,
)
from markdownflow.engine.tools import _script_questions


@pytest.mark.parametrize(
    ("source", "prompt", "stored", "accepted"),
    [
        ("?[Next//next]", "Next", "next", False),
        ("?[Next//continue]", "Next", "continue", True),
        ("?[Next]", "Next", "continue", True),
        (
            "?[Next//next]",
            "Press the button to continue to the next section.",
            "next",
            True,
        ),
    ],
)
def test_confirm_validation_compares_the_rendered_stored_value(
    source: str, prompt: str, stored: str, accepted: bool
) -> None:
    spec = InteractionSpec(
        type="confirm", prompt=prompt, options=[Option(display="Next", value=stored)]
    )
    authored = _script_questions(source)[0]
    reason = check_authored_interaction(spec, authored)
    assert (reason is None) is accepted
    if not accepted:
        assert "stored value" in reason
        assert render_question(spec)[1] == "?[Next//continue]"


@pytest.mark.parametrize("stored", ["value//extra", "value"])
def test_only_the_first_display_value_separator_splits_a_choice(stored: str) -> None:
    authored = _script_questions("?[Label//value//extra | Other]")[0]
    spec = InteractionSpec(
        type="single",
        prompt="Choose",
        options=[Option(display="Label", value=stored), Option(display="Other")],
    )
    reason = check_authored_interaction(spec, authored)
    assert (reason is None) == (stored == "value//extra")
