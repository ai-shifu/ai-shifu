"""References and image controls stay within observed ContentRender ownership."""

import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from markdownflow.engine import (
    ScriptBundle,
    collected_names,
    marker_context,
    render_first_prompt,
    rendered_reference_runs,
)
from markdownflow.engine.marker_context import analyze_marker_context
from markdownflow.engine.rendered_reference_runs import Run, RunIndex, build_ownership
from markdownflow.engine.tools import script_options

if TYPE_CHECKING:
    from collections.abc import Callable

_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "rendered_reference_runs_browser.json"
)
_CASES = json.loads(_FIXTURE.read_text())["cases"]


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["id"])
def test_reference_ownership_matches_observed_content_render(
    case: dict[str, Any],
) -> None:
    source = case["source"]
    assert len(analyze_marker_context(source).image_labels) == case["images"]
    assert script_options(source) == {button: button for button in case["buttons"]}
    names = (
        set(case["legacyNames"])
        if case["marker"].startswith("%")
        else {"goal"}
        if case["buttons"]
        else set()
    )
    assert collected_names(source) == names
    prompt = render_first_prompt(ScriptBundle(script=source), {"goal": "current"})
    assert ("current" in prompt) is ("goal" not in names)


def test_renderer_owner_index_is_lazy_and_shared_per_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = marker_context.build_ownership

    def counted(*args: object, **kwargs: object) -> RunIndex:
        nonlocal calls
        calls += 1
        return cast("Callable[..., RunIndex]", original)(*args, **kwargs)

    monkeypatch.setattr(marker_context, "build_ownership", counted)
    analyze_marker_context("?[{{goal}} A | B]\n" * 100)
    assert calls == 0
    source = "![?[{{goal}} A | B]][image] " * 100 + "\n\n[image]: /x"
    assert len(analyze_marker_context(source).image_labels) == 100
    assert calls == 1


@pytest.mark.parametrize("size", [100, 1000, 10000])
def test_owner_queries_use_bounded_binary_search(size: int) -> None:
    work = 0

    class CountedStarts(tuple):
        __slots__ = ()

        def __getitem__(self, key: int) -> int:
            nonlocal work
            work += 1
            return super().__getitem__(key)

    owners = RunIndex(
        Run(index * 2, index * 2 + 2, "markdown") for index in range(size)
    )
    owners.starts = CountedStarts(owners.starts)
    assert [owners.owner(index * 2) for index in range(size)] == list(range(size))
    assert 0 < work <= size * (math.ceil(math.log2(size)) + 1)


@pytest.mark.parametrize("size", [100, 1000, 4000])
def test_nested_html_ownership_reads_each_tag_a_bounded_number_of_times(
    monkeypatch: pytest.MonkeyPatch, size: int
) -> None:
    calls = 0
    original = rendered_reference_runs.markup

    def counted(text: str, start: int) -> rendered_reference_runs.Markup:
        nonlocal calls
        calls += 1
        return original(text, start)

    monkeypatch.setattr(rendered_reference_runs, "markup", counted)
    source = "<details>" + "<div>" * size + "</div>" * size + "</details>"
    owners = build_ownership(source)
    assert owners.runs == (Run(0, len(source), "stable"),)
    assert calls <= 8 * (size + 1)


@pytest.mark.parametrize("size", [100, 400, 1600])
@pytest.mark.parametrize(
    "style",
    [
        "nested",
        "ancestor-pop",
        "completed-inner",
        "ancestor-pop-completed",
        "rawtext-closer",
        "nested-ancestor",
        "distinct-ancestors",
        "distinct-inner-closer",
    ],
)
def test_custom_button_element_queries_share_bounded_work(
    monkeypatch: pytest.MonkeyPatch, size: int, style: str
) -> None:
    calls = 0
    original = rendered_reference_runs.markup

    def counted(text: str, start: int) -> rendered_reference_runs.Markup:
        nonlocal calls
        calls += 1
        return original(text, start)

    monkeypatch.setattr(rendered_reference_runs, "markup", counted)
    opener = "<custom-button-after-content>"
    if style.startswith("distinct"):
        body = "".join(f"<tag{index}>" + opener for index in range(size))
        if style == "distinct-inner-closer":
            body += "</custom-button-after-content>"
        body += "".join(f"</tag{index}>" for index in range(size))
        body += '<script>"</custom-button-after-content>"</script>'
    elif style == "nested-ancestor":
        body = ("<span>" + opener) * size + "</span>" * size
        body += '<script>"</custom-button-after-content>"</script>'
    else:
        body = (
            ("<span>" + opener + "</span>") * size
            if style in {"ancestor-pop", "ancestor-pop-completed", "rawtext-closer"}
            else opener * size
        )
    if style == "completed-inner":
        body += "</custom-button-after-content>"
    elif style == "ancestor-pop-completed":
        body += opener + "done</custom-button-after-content>"
    elif style == "rawtext-closer":
        body += '<script>"</custom-button-after-content>"</script>'
    source = "<div>" + body + "</div>"
    owners = build_ownership(source)
    assert owners.runs[0].kind == "sandbox"
    assert owners.runs[-1].end == len(source)
    assert any(run.kind == "markdown" for run in owners.runs) is (
        style in {"completed-inner", "ancestor-pop-completed", "distinct-inner-closer"}
    )
    assert calls <= 16 * (size + 1)
