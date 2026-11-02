"""Submitted answers replay as structured control defaults on both history paths."""

from __future__ import annotations

import json

import pytest
from flaskr.service.learn.agent.interaction_history import structured_user_input

_MULTI = {
    "type": "multi_or_text",
    "prompt": "Which apply?",
    "options": [
        {"display": "Apples, pears", "value": "apples, pears"},
        {"display": "Plums", "value": "plums"},
    ],
    "placeholder": "Something else",
}


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
