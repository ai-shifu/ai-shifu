"""Verify visual elements are withheld until a complete streaming boundary."""

import pytest
from flaskr.service.tts.boundary_strategies import (
    BOUNDARY_STRATEGIES,
    find_boundary_end,
)


@pytest.mark.parametrize(
    ("kind", "element"),
    [
        ("fence", "```python\nprint(1)\n```"),
        ("svg", "<svg><path /></svg>"),
        ("iframe", '<iframe src="https://example.test"></iframe>'),
        ("video", '<video src="clip.mp4"></video>'),
        ("html_table", "<table><tr></tr></table>"),
        ("sandbox", "<div><section>Text</section></div>"),
        ("img", '<img src="image.png">'),
        ("md_img", "![Description](image.png)"),
    ],
)
def test_complete_element_boundary_excludes_following_narration(
    kind: str, element: str
) -> None:
    raw = element + "\nFollowing narration"
    boundary = find_boundary_end(kind, raw)
    assert boundary is not None
    assert raw[:boundary].rstrip() == element
    assert raw[boundary:].lstrip() == "Following narration"


@pytest.mark.parametrize("kind", list(BOUNDARY_STRATEGIES))
def test_empty_visual_stream_has_no_boundary(kind: str) -> None:
    assert find_boundary_end(kind, "") is None


@pytest.mark.parametrize(
    ("kind", "partial"),
    [
        ("fence", "```python\nprint(1)"),
        ("svg", "<svg><path />"),
        ("iframe", '<iframe src="example">'),
        ("video", "<video>"),
        ("html_table", "<table><tr></tr>"),
        ("sandbox", "<div><section>text"),
        ("img", '<img src="image.png"'),
        ("md_img", "unrelated text"),
        ("md_img", "![Description]"),
        ("md_img", "![Description](image.png"),
        ("md_table", "| A | B |\n"),
        ("md_table", "unrelated prose"),
    ],
)
def test_partial_visual_stream_does_not_consume_following_chunks(
    kind: str, partial: str
) -> None:
    assert find_boundary_end(kind, partial) is None


def test_markdown_table_closes_only_when_following_non_table_line_arrives() -> None:
    table = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
    assert find_boundary_end("md_table", table) is None
    end = find_boundary_end("md_table", table + "\nFollowing narration\n")
    assert end is not None
    assert (table + "\nFollowing narration\n")[end:].lstrip().startswith("Following")


def test_markdown_table_inside_code_fence_is_not_a_table_boundary() -> None:
    raw = "```text\n| A | B |\n| --- | --- |\n| 1 | 2 |\n```\n\nFollowing\n"
    assert find_boundary_end("md_table", raw) is None
    assert find_boundary_end("unknown", raw) is None
