"""Reuse native container bounds without changing their physical source scope."""

import re

import pytest
from markdown_it.common.html_re import HTML_TAG_RE
from markdownflow.engine import document_blocks
from markdownflow.engine.document_blocks import DocumentBlocks
from markdownflow.engine.marker_context import analyze_marker_context

HTML_PATTERN = re.compile(HTML_TAG_RE.pattern.removeprefix("^"))


def _extract_names(text: str) -> set[str]:
    return {
        marker.name
        for marker in analyze_marker_context(text).markers
        if marker.name is not None
    }


@pytest.mark.parametrize("size", [100, 200, 400])
def test_flat_quoted_html_collection_scans_container_lines_once(
    monkeypatch: pytest.MonkeyPatch, size: int
) -> None:
    calls = 0
    original = document_blocks.container_content_start

    def counted(
        line: str, steps: tuple[int, ...], *, partial: bool = False
    ) -> int | None:
        nonlocal calls
        calls += 1
        return original(line, steps, partial=partial)

    monkeypatch.setattr(document_blocks, "container_content_start", counted)
    assert _extract_names("> text <n> {{x}}\n" * size) == {"x"}
    assert size <= calls <= 4 * size


@pytest.mark.parametrize("depth", [256, 1024, 4096])
def test_partial_ancestor_recovery_bounds_repeated_prefix_scans(
    monkeypatch: pytest.MonkeyPatch, depth: int
) -> None:
    """A dedent must not retry every ancestor of deeply nested authored content."""
    calls = work = 0
    original = document_blocks.container_content_info

    def counted(
        line: str, steps: tuple[int, ...], *, partial: bool = False
    ) -> tuple[int, int] | None:
        nonlocal calls, work
        calls += 1
        work += len(steps)
        return original(line, steps, partial=partial)

    monkeypatch.setattr(document_blocks, "container_content_info", counted)
    remaining = depth // 2
    source = "> " * depth + "paragraph\n" + "> " * remaining + "continuation\n"
    blocks = DocumentBlocks(source, HTML_PATTERN)
    assert blocks.projected_line(1) == "continuation"
    assert blocks.container_steps[1] == (0,) * remaining
    assert calls <= 2 * depth.bit_length()
    assert work <= depth * (depth.bit_length() + 4)


@pytest.mark.parametrize("size", [100, 200, 400])
@pytest.mark.parametrize(
    "unit",
    [
        "> <!-- x -->\n",
        "> <!--\n> x -->\n",
        "> <script>x</script>\n",
        "> <script>\n> x</script>\n",
    ],
)
def test_literal_projection_reuses_bounds_before_future_context_is_known(
    monkeypatch: pytest.MonkeyPatch, size: int, unit: str
) -> None:
    """Discovering successive quoted blocks must not rescan the remaining document."""
    calls = 0
    original = document_blocks.container_content_start

    def counted(
        line: str, steps: tuple[int, ...], *, partial: bool = False
    ) -> int | None:
        nonlocal calls
        calls += 1
        return original(line, steps, partial=partial)

    monkeypatch.setattr(document_blocks, "container_content_start", counted)
    blocks = DocumentBlocks(unit * size, HTML_PATTERN)
    assert calls <= 8 * len(blocks.lines)


@pytest.mark.parametrize("reverse", [False, True])
def test_container_queries_reuse_safe_suffixes_in_either_order(
    monkeypatch: pytest.MonkeyPatch, reverse: bool
) -> None:
    size = 400
    text = "> text\n" * size + "Outside"
    blocks = DocumentBlocks(text, HTML_PATTERN)
    calls = 0
    original = document_blocks.container_content_start

    def counted(
        line: str, steps: tuple[int, ...], *, partial: bool = False
    ) -> int | None:
        nonlocal calls
        calls += 1
        return original(line, steps, partial=partial)

    monkeypatch.setattr(document_blocks, "container_content_start", counted)
    order = list(range(size))
    if reverse:
        order.reverse()
    for index in order:
        assert blocks.container_end(index) == text.index("Outside")
    assert calls <= 2 * size


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    ("lines", "queries"),
    [
        (["> a", "plain", "> b"], [(0, 1), (2, None), (0, 1)]),
        (
            ["- first", "- second", "  tail", "Outside"],
            [(1, 3), (0, 1), (2, 3), (1, 3)],
        ),
        (
            ["> a", "> > b", "> > c", "> d", "Outside", "> reopened", "> end"],
            [(0, 4), (1, 3), (2, 3), (3, 4), (5, None), (6, None)],
        ),
        (["> - x", ">", ">   y", "Outside"], [(0, 3), (1, 3), (2, 3)]),
        (["> - a", ">"], [(0, None), (1, None)]),
        (["> - a", "> "], [(0, None), (1, None)]),
        (["> - a", "> X"], [(0, 1), (1, None)]),
    ],
)
@pytest.mark.parametrize("flags", [(False, True), (True, False)])
def test_cached_bounds_preserve_steps_partial_lines_and_dedent(
    newline: str,
    lines: list[str],
    queries: list[tuple[int, int | None]],
    flags: tuple[bool, bool],
) -> None:
    text = newline.join(lines)
    blocks = DocumentBlocks(text, HTML_PATTERN)
    for final in flags:
        for index, ending in queries:
            expected = len(text) if ending is None else blocks.lines[ending].start
            assert blocks.container_end(index, final=final) == expected


def test_final_and_partial_queries_have_independent_cache_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "> - a\n>   b\n> "
    blocks = DocumentBlocks(text, HTML_PATTERN)
    calls = 0
    original = document_blocks.container_content_start

    def counted(
        line: str, steps: tuple[int, ...], *, partial: bool = False
    ) -> int | None:
        nonlocal calls
        calls += 1
        return original(line, steps, partial=partial)

    monkeypatch.setattr(document_blocks, "container_content_start", counted)
    assert blocks.container_end(0, final=False) == len(text)
    first = calls
    assert first > 0
    assert blocks.container_end(0, final=False) == len(text)
    assert calls == first
    assert blocks.container_end(0, final=True) == len(text)
    assert calls > first
    first = calls
    assert blocks.container_end(0, final=True) == len(text)
    assert calls == first
