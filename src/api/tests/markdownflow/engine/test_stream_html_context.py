"""Keep native HTML continuations finite without changing their accepted suffixes."""

from unittest.mock import patch

import pytest
from markdownflow.engine import stream_html_context
from markdownflow.engine.stream_html_context import pending_html_prefix
from markdownflow.syntax.constants import COMPILED_INLINE_HTML_REGEX
from markdownflow.syntax.parser.document_blocks import HTML_BLOCK_TAGS

HTML_TAG_RE = COMPILED_INLINE_HTML_REGEX


@pytest.mark.parametrize(
    "token",
    [
        '<span title="{{ example }}">',
        "<span title='long example'>",
        "<script data-x=unicode😀 />",
        "<textarea>",
        "</SCRIPT \t>",
        "<!-->",
        "<!--->",
        "<!-- comments --- and --x end -->",
        "<?instruction ???>",
        "<!DOCTYPE html>",
        "<![CDATA[data ] ]] end]]>",
        "<!doctype html>",
        "<!DOCTYPEx>",
        "<b a=x\u0085汉\x01>",
        "<b\na=\r\n 'value'>",
        "<b \r\n a \n = \n'value' \r/>",
        "</b \r>",
    ],
)
def test_every_native_token_prefix_keeps_its_original_completion(token: str) -> None:
    assert HTML_TAG_RE.fullmatch(token)
    for cut in range(1, len(token)):
        result = pending_html_prefix(token[:cut], 0)
        assert result is not None, (token, cut)
        start, witness = result
        assert start == 0
        assert len(witness) <= 80
        assert HTML_TAG_RE.fullmatch(witness + token[cut:]), (token, cut, witness)


@pytest.mark.parametrize(
    "prefix", ["i<n 时", "a<b,", "<b =", "<b a='x'wrong", "</b/", "<![wrong"]
)
def test_invalid_tag_prefixes_do_not_accumulate(prefix: str) -> None:
    assert pending_html_prefix(prefix, prefix.find("<")) is None


@pytest.mark.parametrize(
    "prefix", ['<span a="', "<!--", "<?", "<![CDATA[", "<!A", "<span a="]
)
def test_long_native_content_has_a_bounded_continuation(prefix: str) -> None:
    source = prefix + "x" * 20000
    result = pending_html_prefix(source, 0, tokens="`x$[x")
    assert result is not None
    assert len(result[1]) < 100
    assert "`x$[x" in result[1]


def test_candidates_after_invalid_or_complete_tags_keep_original_offsets() -> None:
    source = 'a<b, <done> i<n 时 <span a="'
    result = pending_html_prefix(source, 1)
    assert result is not None
    assert result[0] == source.rfind("<")
    assert HTML_TAG_RE.fullmatch(result[1] + '">')


@pytest.mark.parametrize(
    "source", ["<!--" * 4096, "i<n 时 " * 4096, '<b a="' * 4096, "<![CDATA[" * 4096]
)
def test_repeated_candidates_have_bounded_lexer_work(source: str) -> None:
    with patch.object(
        stream_html_context, "_step", wraps=stream_html_context._step
    ) as step:
        pending_html_prefix(source, source.find("<"))
    assert step.call_count < 32 * len(source)


def test_raw_tag_name_prefixes_preserve_future_raw_block_identity() -> None:
    for tag in ("script", "style", "pre", "textarea"):
        for cut in range(1, len(tag) + 1):
            result = pending_html_prefix("<" + tag[:cut], 0)
            assert result is not None
            assert result[1] + tag[cut:] + ">" == "<" + tag + ">"
    assert pending_html_prefix("<script/", 0) == (0, "<script/")


@pytest.mark.parametrize("tag", sorted(HTML_BLOCK_TAGS))
@pytest.mark.parametrize("opening", ["<", "</"])
def test_native_block_tag_prefixes_preserve_their_classification(
    tag: str, opening: str
) -> None:
    for cut in range(1, len(tag) + 1):
        result = pending_html_prefix(opening + tag[:cut], 0)
        assert result is not None
        assert result[1] + tag[cut:] + ">" == opening + tag + ">"
        assert len(result[1]) <= 16


@pytest.mark.parametrize(
    "token",
    [
        "<b\u0085a=x>",
        "<b\u3000a=x>",
        "<b\x0ca=x>",
        "<b\n\na=x>",
        "<b \r\r a=x>",
        "<b a=\n \n'x'>",
        "</b\n\n>",
    ],
)
def test_tag_space_is_space_or_tab_with_at_most_one_line_ending(token: str) -> None:
    assert HTML_TAG_RE.fullmatch(token) is None
    # The lexer rejects the same token at the first character past the budget.
    assert pending_html_prefix(token[:-1], 0) is None


@pytest.mark.parametrize(
    ("prefix", "suffix"),
    [("<b\r", "\na=x>"), ("<b a\n", "='x'>"), ("<b a=x\r\n", " c>")],
)
def test_witness_keeps_a_spent_line_ending_budget(prefix: str, suffix: str) -> None:
    result = pending_html_prefix(prefix, 0)
    assert result is not None
    assert HTML_TAG_RE.fullmatch(prefix + suffix)
    assert HTML_TAG_RE.fullmatch(result[1] + suffix)
    assert not HTML_TAG_RE.fullmatch(result[1] + "\n" + suffix)
