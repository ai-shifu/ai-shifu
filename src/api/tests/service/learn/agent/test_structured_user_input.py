"""Submitted answers replay as structured control defaults on both history paths."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from flaskr.api.markdownflow import InteractionSpec
from flaskr.service.learn.agent.interaction_history import structured_user_input
from flaskr.service.learn.agent.run_agent import _turn_input

_MULTI = {
    "type": "multi_or_text",
    "prompt": "Which apply?",
    "options": [
        {"display": "Apples, pears", "value": "apples, pears"},
        {"display": "Plums", "value": "plums"},
    ],
    "placeholder": "Something else",
}


def test_single_choice_plus_image_survives_execution_and_history() -> None:
    """A single choice must not truncate the attached free-text image answer."""
    marker = (
        "![learner-image](https://images.example/learner-images/" + "a" * 32 + ".png)"
    )
    spec = {**_MULTI, "type": "single_or_text"}
    session = SimpleNamespace(
        started=True,
        pending=[SimpleNamespace(spec=InteractionSpec.model_validate(spec))],
    )
    turn = _turn_input(session, ["plums", "See this: " + marker])
    assert turn.values == ["plums"]
    assert turn.text == "See this: " + marker
    saved = json.loads(structured_user_input(spec, ["plums", "See this: " + marker]))
    assert saved["selectedValues"] == ["plums"]
    assert saved["inputText"] == "See this: " + marker


def test_choices_containing_commas_stay_separate_values() -> None:
    encoded = structured_user_input(_MULTI, ["apples, pears", "plums", "figs, dates"])
    assert encoded is not None
    assert json.loads(encoded) == {
        "selectedValues": ["apples, pears", "plums"],
        "inputText": "figs, dates",
        "buttonText": "",
    }


def test_single_choice_sets_the_button_text() -> None:
    spec = {**_MULTI, "type": "single"}
    encoded = structured_user_input(spec, ["plums"])
    assert encoded is not None
    assert json.loads(encoded)["buttonText"] == "plums"


@pytest.mark.parametrize(
    "spec",
    [
        {"type": "confirm", "prompt": "Continue?"},
        {"type": "unknown", "prompt": "?"},
    ],
)
def test_confirmations_and_invalid_specs_have_no_structured_default(
    spec: dict[str, object],
) -> None:
    assert structured_user_input(spec, ["yes"]) is None
