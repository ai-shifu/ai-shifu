"""HTML attributes cannot turn authored notes into Markdown code examples."""

from __future__ import annotations

import pytest
from flaskr.service.learn.agent.engine.script import (
    ScriptBundle,
    collected_names,
    render_first_prompt,
)
from flaskr.service.learn.agent.engine.script_comments import strip_comments
from flaskr.service.learn.agent.engine.script_html_tags import html_tag_end


@pytest.mark.parametrize("quote", ["'", '"'])
@pytest.mark.parametrize("attribute", ["title", "data-hint"])
def test_attribute_backticks_do_not_protect_comments(
    quote: str, attribute: str
) -> None:
    first = f"<span {attribute}={quote}`>{quote}>One</span>"
    second = f"<span {attribute}={quote}`{quote}>Two</span>"
    source = first + "<!-- private %{{hidden}} {{secret}} -->" + second
    bundle = ScriptBundle(script=source)
    assert strip_comments(source) == first + second
    assert collected_names(source) == frozenset()
    prompt = render_first_prompt(bundle, {})
    assert first + second in prompt
    assert "private" not in prompt
    assert "hidden" not in prompt
    assert "secret" not in prompt
    assert bundle.script == source


def test_html_attribute_comment_notation_is_literal_attribute_data() -> None:
    source = '<span title="<!-- literal -->`">Visible</span><!-- private -->'
    assert strip_comments(source) == source.removesuffix("<!-- private -->")


def test_html_inside_markdown_code_remains_literal() -> None:
    source = '``<span title="`">One</span><!-- literal -->`` <!-- private -->'
    assert strip_comments(source) == source.removesuffix("<!-- private -->")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("<A>", 3),
        ("</A >", 5),
        ("<a-1/>", 6),
        ("<A disabled other >", 19),
        ("<A _name:value-1.2='`' :x=unquoted/>", 36),
        ('<A title="<!-- literal > -->`">tail', 31),
        ("<A title='line\n>value'>", 23),
        ("<A value=one\u00a0other=two>", 23),
        ("<A value=\u00a0>", 11),
        ("<A value=\x00>", None),
        ("<A value=>", None),
        ("<A value='unclosed>", None),
        ('<A value="unclosed>', None),
        ("<A 1name=value>", None),
        ("<A .name=value>", None),
        ("<A value='one'other=two>", None),
        ("</A value=one>", None),
        ("<é>", None),
        ("<1A>", None),
    ],
)
def test_inline_tag_scanning_preserves_commonmark_attribute_grammar(
    source: str, expected: int | None
) -> None:
    assert html_tag_end(source, 0) == expected


def test_malformed_attributes_visit_each_character_once() -> None:
    reads = 0

    class CountingText(str):
        __slots__ = ()

        def __getitem__(self, key: int | slice) -> str:
            nonlocal reads
            if isinstance(key, int):
                reads += 1
            return super().__getitem__(key)

    # Nested optional whitespace/assignments caused exponential regex retries.
    source = CountingText("<A\t:=" + "!\t\t:=" * 5000 + "!")
    assert html_tag_end(source, 0) is None
    assert reads == len(source) - 1


def test_malformed_long_attributes_do_not_block_comment_filtering() -> None:
    malformed = "<A\t:=" + "!\t\t:=" * 5000 + "!"
    assert strip_comments(malformed + "<!-- private -->") == malformed


def test_long_valid_quoted_attributes_keep_literal_comment_notation() -> None:
    tag = '<span title="' + "<!-- literal -->` " * 1000 + '">'
    source = tag + "Visible</span><!-- private -->"
    assert strip_comments(source) == source.removesuffix("<!-- private -->")
