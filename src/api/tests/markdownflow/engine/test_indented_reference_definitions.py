"""Consecutive definitions follow the renderer's logical content ownership."""

import json
from pathlib import Path
from typing import Any

import pytest
from markdownflow.engine import ScriptBundle, collected_names, render_first_prompt
from markdownflow.engine.document_blocks import DocumentBlocks
from markdownflow.engine.marker_context import _INLINE_HTML, analyze_marker_context
from markdownflow.engine.tools import script_options

_FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "indented_reference_definitions_browser.json"
)
_CASES = json.loads(_FIXTURE.read_text())["cases"]


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["id"])
def test_indented_definition_ownership_matches_observed_content_render(
    case: dict[str, Any],
) -> None:
    source = case["source"]
    expected_names = (
        {"goal"} if case["marker"].startswith("%") or case["buttons"] else set()
    )
    assert len(analyze_marker_context(source).image_labels) == case["images"]
    assert collected_names(source) == expected_names
    assert script_options(source) == {button: button for button in case["buttons"]}
    prompt = render_first_prompt(ScriptBundle(script=source), {"goal": "current"})
    assert ("current" in prompt) is ("goal" not in expected_names)


@pytest.mark.parametrize("padding", ["    ", "\t"])
@pytest.mark.parametrize("body", ["[image]: /x", "ordinary prose"])
def test_definition_continuation_does_not_relax_other_block_starts(
    padding: str, body: str
) -> None:
    blocks = DocumentBlocks("[one]: /one\n" + padding + body, _INLINE_HTML)
    assert blocks.block_content_start(1) is None
    assert (blocks.reference_label_prefix(blocks.lines[1].start) is not None) is (
        body == "[image]: /x"
    )


@pytest.mark.parametrize("size", [100, 400, 1600])
def test_indented_definition_chain_reuses_validated_predecessors(
    monkeypatch: pytest.MonkeyPatch, size: int
) -> None:
    calls = 0
    original = DocumentBlocks.reference_projection

    def counted(
        self: DocumentBlocks, index: int, steps: tuple[int, ...]
    ) -> tuple[int, str, bool, int]:
        nonlocal calls
        calls += 1
        return original(self, index, steps)

    monkeypatch.setattr(DocumentBlocks, "reference_projection", counted)
    source = "[one]: /one\n" + "    [two]: /two\n" * size
    blocks = DocumentBlocks(source, _INLINE_HTML)
    assert len(blocks.closed_reference_lines) == size + 1
    assert calls <= 8 * len(blocks.lines)
