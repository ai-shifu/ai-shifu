"""Reference label budgets follow observed browser output, not inferred lengths."""

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from markdownflow.engine import ScriptBundle, collected_names, render_first_prompt
from markdownflow.engine.document_blocks import DocumentBlocks
from markdownflow.engine.marker_context import _INLINE_HTML
from markdownflow.engine.tools import script_options

_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "reference_label_browser_budgets.json"
)
_DATA = json.loads(_FIXTURE.read_text())
_OBSERVATIONS = _DATA["cases"]
_ENDINGS = {"LF": "\n", "CRLF": "\r\n", "CR": "\r"}
_CASES = [
    pytest.param(case, _ENDINGS[ending], id=f"{case['id']} | {ending}")
    for case in _OBSERVATIONS
    for ending in case.get("lineEndings", _DATA["lineEndings"])
]


def _source(case: dict[str, Any]) -> str:
    source = "".join(
        chunk if isinstance(chunk, str) else chunk["text"] * chunk["repeat"]
        for chunk in case["source"]
    )
    assert hashlib.sha256(source.encode()).hexdigest() == case["sha256"]
    return source


@pytest.mark.parametrize(("case", "newline"), _CASES)
def test_reference_label_budget_matches_observed_content_render(
    case: dict[str, Any], newline: str
) -> None:
    """All endings were captured with identical image/control outcomes in the browser."""
    source = _source(case).replace("\n", newline)
    expected_names = (
        frozenset({"goal"})
        if case["marker"].startswith("%") or case["buttons"]
        else frozenset()
    )
    assert collected_names(source) == expected_names
    assert script_options(source) == {button: button for button in case["buttons"]}
    if not case["marker"].startswith("%"):
        prompt = render_first_prompt(ScriptBundle(script=source), {"goal": "current"})
        assert ("current" in prompt) is bool(case["images"])
    source += newline * 2 + "?[{{visible}} C | D]"
    assert collected_names(source) == expected_names | {"visible"}
    assert script_options(source) == {
        **{button: button for button in case["buttons"]},
        "C": "C",
        "D": "D",
    }


@pytest.mark.parametrize("size", [100, 200, 400])
@pytest.mark.parametrize(("unit", "width"), [("😀\t", 2), ("a\t", 3), ("abc\t", 1)])
def test_physical_tab_widths_are_indexed_once_per_document(
    size: int, unit: str, width: int
) -> None:
    """Repeated label queries cannot repeatedly scan the same physical prefix."""
    work = 0

    class CountedText(str):
        __slots__ = ()

        def __iter__(self) -> Iterator[str]:
            nonlocal work
            for character in super().__iter__():
                work += 1
                yield character

    source = CountedText(unit * size)
    blocks = DocumentBlocks(source, _INLINE_HTML)
    positions = [
        index for index, character in enumerate(str(source)) if character == "\t"
    ]
    work = 0
    assert [blocks.label_character_size(at) for at in positions] == [width] * size
    assert [blocks.label_character_size(at) for at in reversed(positions)] == [
        width
    ] * size
    assert work <= len(source)
