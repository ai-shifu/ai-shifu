"""Incomplete HTML attributes cannot consume later Markdown blocks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from flaskr.service.learn.agent.engine.script import ScriptBundle, render_first_prompt
from flaskr.service.learn.agent.engine.script_comments import (
    comment_ranges,
    strip_comments,
)
from flaskr.service.learn.agent.engine.script_html_tags import (
    HtmlTagScanner,
    html_tag_end,
)

if TYPE_CHECKING:
    import re


@pytest.mark.parametrize("linebreak", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    "boundary", ["# Next", "- Item", "> Quote", "---", "", "<div>"]
)
def test_interrupted_quoted_tag_does_not_protect_a_later_comment(
    boundary: str, linebreak: str
) -> None:
    source = (
        "Visible <A title='unfinished\n"
        + boundary
        + "\n<!-- private instruction -->\n'> tail"
    ).replace("\n", linebreak)
    assert strip_comments(source) == source.replace("<!-- private instruction -->", "")
    assert "private instruction" not in render_first_prompt(
        ScriptBundle(script=source), {}
    )


@pytest.mark.parametrize("linebreak", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("quote", ["'", '"'])
def test_true_multiline_inline_attributes_keep_their_original_bytes(
    linebreak: str, quote: str
) -> None:
    tag = (
        f"Visible <A title={quote}first\n"
        "continued <!-- literal attribute -->\n"
        f"last{quote}> tail"
    ).replace("\n", linebreak)
    source = tag + "<!-- private instruction -->"
    assert strip_comments(source) == tag


@pytest.mark.parametrize("linebreak", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("quote", ["'", '"'])
def test_true_multiline_raw_html_attributes_keep_their_original_bytes(
    linebreak: str, quote: str
) -> None:
    tag = (
        f"<div title={quote}first\n"
        "<!-- literal attribute -->\n"
        f"last{quote}> tail</div>\n\n"
    ).replace("\n", linebreak)
    source = tag + "<!-- private instruction -->"
    assert strip_comments(source) == tag


def test_blank_line_ends_the_raw_html_block_before_a_later_closing_quote() -> None:
    source = "<div title='unfinished\n\n<!-- private instruction -->\n'> tail"
    assert strip_comments(source) == source.replace("<!-- private instruction -->", "")


def test_bounded_tag_recognition_never_reads_the_next_block() -> None:
    source = "<A title='unfinished\n# Next\n<!-- private -->\n'>"
    boundary = source.index("# Next")

    class BoundedText(str):
        __slots__ = ()

        def __getitem__(self, key: int | slice) -> str:
            if isinstance(key, int):
                assert key < boundary
            return super().__getitem__(key)

    assert html_tag_end(BoundedText(source), 0, boundary) is None


def test_outside_block_tag_candidates_reuse_the_physical_line_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.learn.agent.engine import script_html_tags

    source = "<A invalid= " * 1000
    linebreaks = script_html_tags._LINEBREAKS
    searches = 0

    class CountingLinebreaks:
        def search(self, text: str, start: int) -> re.Match[str] | None:
            nonlocal searches
            searches += 1
            return linebreaks.search(text, start)

    monkeypatch.setattr(script_html_tags, "_LINEBREAKS", CountingLinebreaks())
    scanner = HtmlTagScanner(source, [])
    for start in range(0, len(source), len("<A invalid= ")):
        assert scanner.end(start) is None
    assert searches == 1


def test_canonical_comment_ranges_refer_to_original_source_offsets() -> None:
    source = "Intro `<!-- literal -->` <!-- note\r\nmore --> tail <!-- unclosed"
    first = source.index("<!-- note")
    second = source.index("<!-- unclosed")
    assert comment_ranges(source) == [
        (first, second - len(" tail ")),
        (second, len(source)),
    ]
    assert strip_comments(source) == "Intro `<!-- literal -->` \r\n tail "
