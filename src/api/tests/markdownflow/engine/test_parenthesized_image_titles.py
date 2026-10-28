"""Image title syntax follows observed ContentRender output."""

import json
from pathlib import Path
from typing import Any

import pytest
from markdownflow.engine import (
    ScriptBundle,
    collected_names,
    render_first_prompt,
    substitute_variables,
)
from markdownflow.engine.marker_context import analyze_marker_context
from markdownflow.engine.tools import script_options

_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "parenthesized_image_titles_browser.json"
)
_CASES = json.loads(_FIXTURE.read_text())["cases"]


@pytest.mark.parametrize("case", _CASES, ids=lambda case: str(case["id"]))
def test_parenthesized_image_titles_follow_observed_content_render(
    case: dict[str, Any],
) -> None:
    """Accepted titles shield their contents and keep a later real question visible."""
    source = case["source"]
    image = bool(case["images"])
    expected_names = {"goal"} if case["marker"].startswith("%") or not image else set()
    if case["group"] == "title-literal":
        expected_names.add("visible")
    assert collected_names(source) == expected_names
    assert script_options(source) == {button: button for button in case["buttons"]}
    if not case["marker"].startswith("%"):
        prompt = render_first_prompt(ScriptBundle(script=source), {"goal": "current"})
        assert ("current" in prompt) is image


@pytest.mark.parametrize("image", [False, True])
@pytest.mark.parametrize("destination", ["/x", "</x>"])
def test_title_image_validation_preserves_generic_resource_literal_spans(
    image: bool, destination: str
) -> None:
    """The historical opaque-resource guard remains separate from image admission."""
    prefix = ("!" if image else "") + f"[example]({destination} (Diagram ({{{{))"
    source = prefix + "\n\n?[{{visible}} C | D]\n\nRead {{value}}."
    assert (prefix.index("("), len(prefix)) in analyze_marker_context(source).literals
    assert collected_names(source) == frozenset({"visible"})
    assert script_options(source) == {"C": "C", "D": "D"}
    assert substitute_variables(source, {"value": "current"}).endswith("Read current.")
