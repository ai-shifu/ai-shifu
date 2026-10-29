"""Definition lookahead follows observed ContentRender paragraph boundaries."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from markdown_it.common.html_re import HTML_TAG_RE
from markdownflow.engine import (
    ScriptBundle,
    collected_names,
    document_blocks,
    render_first_prompt,
)
from markdownflow.engine.document_blocks import DocumentBlocks
from markdownflow.engine.tools import script_options

_FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "reference_definition_paragraphs_browser.json"
)
_CASES = json.loads(_FIXTURE.read_text())["cases"]
HTML_PATTERN = re.compile(HTML_TAG_RE.pattern.removeprefix("^"))


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["id"])
def test_reference_definition_lookahead_matches_observed_content_render(
    case: dict[str, Any],
) -> None:
    """Definition bodies do not create list containers the learner cannot see."""
    source = case["source"]
    image = bool(case["images"])
    expected_names = {"goal"} if case["marker"].startswith("%") or not image else set()
    assert collected_names(source) == expected_names
    assert script_options(source) == {button: button for button in case["buttons"]}
    if not case["marker"].startswith("%"):
        prompt = render_first_prompt(ScriptBundle(script=source), {"goal": "current"})
        assert ("current" in prompt) is image


@pytest.mark.parametrize("size", [100, 200, 400])
@pytest.mark.parametrize(
    "unit",
    ["[one]: /one\n", "> [o\n> ne]: /one\n", '> [one]: /one "a\n> line\n> b"\n'],
)
def test_reference_closure_lookahead_has_bounded_work(
    monkeypatch: pytest.MonkeyPatch, size: int, unit: str
) -> None:
    calls = 0
    original = document_blocks.DocumentBlocks.reference_projection

    def counted(
        self: DocumentBlocks, index: int, steps: tuple[int, ...]
    ) -> tuple[int, str, bool, int]:
        nonlocal calls
        calls += 1
        return original(self, index, steps)

    monkeypatch.setattr(DocumentBlocks, "reference_projection", counted)
    source = unit * size
    blocks = DocumentBlocks(source, HTML_PATTERN)
    assert calls <= 8 * len(blocks.lines)
