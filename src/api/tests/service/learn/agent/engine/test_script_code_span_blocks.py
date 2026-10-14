"""Inline-code delimiters cannot cross CommonMark block boundaries."""

from __future__ import annotations

import pytest
from flaskr.service.learn.agent.engine.script_code_blocks import build_block_indexes
from flaskr.service.learn.agent.engine.script_code_spans import build_code_span_index
from flaskr.service.learn.agent.engine.script_comments import strip_comments
from markdown_it.parser_block import ParserBlock


@pytest.mark.parametrize("linebreak", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    "boundary",
    [
        "# Heading",
        "Heading\n=======",
        "- Item",
        "1. Item",
        "> Quote",
        "---",
        "~~~html\nExample\n~~~",
        "<div>",
        "<script>",
        "<?instruction?>",
        "<!DECLARATION>",
        "<![CDATA[payload]]>",
        "<!-- boundary -->",
    ],
)
def test_unmatched_delimiters_cannot_protect_notes_across_blocks(
    boundary: str, linebreak: str
) -> None:
    source = (
        "Intro `unmatched\n" + boundary + "\nVisible <!-- private -->\nClosing ` text"
    ).replace("\n", linebreak)
    expected = source.replace("<!-- private -->", "").replace("<!-- boundary -->", "")
    assert strip_comments(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "- `unmatched\n- Visible <!-- private -->`",
        "> `unmatched\n>\n> Visible <!-- private -->`",
        "- `unmatched\n\n  Visible <!-- private -->`",
        "<div>\n`unmatched\nVisible <!-- private -->`\n</div>",
    ],
)
def test_container_boundaries_and_raw_html_do_not_create_code_spans(
    source: str,
) -> None:
    assert strip_comments(source) == source.replace("<!-- private -->", "")


@pytest.mark.parametrize("container", ["", "> ", "- "])
def test_soft_linebreaks_within_one_paragraph_keep_true_code_spans(
    container: str,
) -> None:
    continuation = "  " if container == "- " else container
    source = (
        f"{container}`literal\n"
        f"{continuation}continued <!-- literal -->` <!-- private -->"
    )
    assert strip_comments(source) == source.removesuffix("<!-- private -->")


def test_lazy_quote_continuation_keeps_a_true_code_span() -> None:
    source = "> `literal\ncontinued <!-- literal -->` <!-- private -->"
    assert strip_comments(source) == source.removesuffix("<!-- private -->")


def test_comment_block_suffix_is_not_an_inline_code_example() -> None:
    source = "<!-- `private` --> `<!-- another private note -->`"
    assert strip_comments(source) == " ``"


def test_span_index_uses_original_offsets_for_each_inline_block() -> None:
    source = "`first`\r\n# `second`\r\n<div>\r\n`raw html`\r\n"
    code_blocks, inline_blocks = build_block_indexes(source)
    assert code_blocks == {}
    assert inline_blocks == [(0, 9), (9, 21)]
    assert build_code_span_index(source, inline_blocks) == {0: 7, 11: 19}


def test_comment_filter_reuses_one_block_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    parse = ParserBlock.parse

    def counted_parse(self: ParserBlock, *args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        parse(self, *args, **kwargs)

    monkeypatch.setattr(ParserBlock, "parse", counted_parse)
    source = "Intro `unmatched\n# Heading\n<!-- private -->\n`"
    assert strip_comments(source) == source.replace("<!-- private -->", "")
    assert calls == 1
