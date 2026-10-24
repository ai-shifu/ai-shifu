"""Clean MDF syntax in prose while preserving the formatter's opaque elements verbatim."""

from __future__ import annotations

import random

import pytest
from markdownflow.preserve_markers import PreserveMarkerFilter

HTML = (
    '<div data-value="===attribute===">===visible==='
    "<script>const equal = a === b;</script><!-- ===comment=== --></div>"
)
OPAQUE = [
    pytest.param(HTML, id="html"),
    pytest.param(
        "<svg><text>===label===</text><script>a === b;</script></svg>", id="svg"
    ),
    pytest.param("```js\nconst equal = a === b;\n!===\n===literal===\n```", id="code"),
    pytest.param('```mermaid\ngraph TD; A["===label==="] --> B\n```', id="mermaid"),
    pytest.param("!+++\n+ ===added===\n- ===removed===\n!+++", id="diff"),
    pytest.param("![===alt===](https://example/image.png)", id="image"),
    pytest.param("| ===heading=== |\n| --- |\n| ===cell=== |", id="table"),
    pytest.param("$$\n===formula===\n$$", id="latex"),
]


def _from_chunks(chunks: list[str]) -> str:
    """Collect one turn and verify that a repeated flush cannot duplicate its tail."""
    marker_filter = PreserveMarkerFilter()
    output = (
        "".join(marker_filter.feed(chunk) for chunk in chunks) + marker_filter.flush()
    )
    assert marker_filter.flush() == ""
    return output


def _assert_streaming_output(source: str, expected: str) -> None:
    """Check whole input, every two-part cut, individual characters and model-sized chunks."""
    assert _from_chunks([source]) == expected
    for cut in range(len(source) + 1):
        assert _from_chunks([source[:cut], source[cut:]]) == expected, f"cut at {cut}"
    assert _from_chunks(list(source)) == expected, "character chunks"
    for seed in range(5):
        rng = random.Random(seed)  # noqa: S311 -- chunk sizes, not secrets
        chunks: list[str] = []
        index = 0
        while index < len(source):
            length = rng.randint(1, 9)
            chunks.append(source[index : index + length])
            index += length
        assert _from_chunks(chunks) == expected, f"seed {seed}"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("My goal: ===help a million people===.", "My goal: help a million people."),
        ("!===exact=== and ====also exact====", "exact and also exact"),
        ("===one======two===", "onetwo"),
        ("# ===Heading===\n===body===", "# Heading\nbody"),
        ("before\n===\nafter\n", "before\n\nafter\n"),
        ("No marker: a = b and c == d.", "No marker: a = b and c == d."),
    ],
)
def test_only_mdf_marker_tokens_are_removed_from_prose(
    source: str, expected: str
) -> None:
    _assert_streaming_output(source, expected)


@pytest.mark.parametrize("tail", ["=", "==", "!", "!=", "!=="])
def test_a_fragment_that_never_becomes_a_marker_is_released_at_eof(tail: str) -> None:
    _assert_streaming_output("Plain text " + tail, "Plain text " + tail)


@pytest.mark.parametrize("ending", ["\n", "\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize("opaque", OPAQUE)
def test_every_nonprose_element_keeps_its_entire_original_source(
    opaque: str, ending: str
) -> None:
    opaque = opaque.replace("\n", ending)
    source = "===before===" + ending + opaque + ending + "===after==="
    _assert_streaming_output(source, "before" + ending + opaque + ending + "after")


@pytest.mark.parametrize(
    "opaque",
    [
        "<div>\n===visible===<script>const equal = a === b;",
        "<svg>\n<text>===label===",
        "```js\nconst equal = a === b;\n!===\n===literal===",
    ],
    ids=["unfinished-html", "unfinished-svg", "unfinished-code"],
)
def test_unfinished_opaque_elements_are_still_preserved_when_the_turn_ends(
    opaque: str,
) -> None:
    _assert_streaming_output(opaque, opaque)


@pytest.mark.parametrize("indent", ["", " \t"])
@pytest.mark.parametrize("ending", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_standalone_mdf_fences_outside_opaque_elements_are_removed(
    indent: str, ending: str
) -> None:
    fence = indent + "!====\t" + ending
    source = "before" + ending + fence + "===wrapped===" + ending + fence + "after"
    _assert_streaming_output(source, "before" + ending + "wrapped" + ending + "after")


@pytest.mark.parametrize("ending", ["\n", "\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize(
    "opaque",
    [HTML, "<svg><text>===label===</text></svg>"],
    ids=["html", "svg"],
)
def test_inline_mdf_wrappers_are_outside_the_opaque_element(
    opaque: str, ending: str
) -> None:
    source = "===before===" + ending + "===" + opaque + "===" + ending + "===after==="
    _assert_streaming_output(source, "before" + ending + opaque + ending + "after")


@pytest.mark.parametrize("ending", ["\n", "\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize("opaque", [HTML, "```js\n!===\nconst equal = a === b;\n```"])
def test_mdf_fences_can_wrap_an_opaque_element_without_changing_its_body(
    opaque: str, ending: str
) -> None:
    opaque = opaque.replace("\n", ending)
    source = "!===" + ending + opaque + ending + "!===" + ending + "===after==="
    _assert_streaming_output(source, opaque + ending + "after")


@pytest.mark.parametrize("ending", ["\n", "\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize("fence", ["```", "~~~"], ids=["backticks", "tildes"])
def test_an_inline_mdf_envelope_ends_with_its_code_fence(
    ending: str, fence: str
) -> None:
    code = ending.join([fence + "js", "a===b;", "===literal===", "!===", fence])
    source = "===" + code + "===" + ending + "===After===" + ending
    _assert_streaming_output(source, code + ending + "After" + ending)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Use `a === b` and ===remember===.", "Use `a === b` and remember."),
        ("Use ``a ` === b`` and ===remember===.", "Use ``a ` === b`` and remember."),
        ("Use `<script>` literally. ===after===", "Use `<script>` literally. after"),
        (
            "<git+ssh://example/a!===b> ===after===",
            "<git+ssh://example/a!===b> after",
        ),
        (
            '[===label===](https://example/a===b "===title===") ===after===',
            '[label](https://example/a===b "===title===") after',
        ),
    ],
)
def test_native_markdown_inline_metadata_is_protected_inside_prose(
    source: str, expected: str
) -> None:
    _assert_streaming_output(source, expected)


@pytest.mark.parametrize("source", ["<x:a===b>", "<javascript:alert(===body===)>"])
def test_invalid_native_inline_candidates_remain_plain_prose(source: str) -> None:
    _assert_streaming_output(
        source + " ===after===", source.replace("===", "") + " after"
    )


def test_native_reference_metadata_is_protected_while_visible_prose_is_cleaned() -> (
    None
):
    source = '[===caption===][id]\n\n[id]: <https://example/a===b> "===title==="\n\n===after==='
    expected = source.replace("===caption===", "caption").replace(
        "===after===", "after"
    )
    _assert_streaming_output(source, expected)


def test_ordinary_complete_lines_are_released_before_the_turn_ends() -> None:
    marker_filter = PreserveMarkerFilter()
    assert marker_filter.feed("===first===\n") == "first\n"
    assert marker_filter.feed("Plain second line.\n") == "Plain second line.\n"
    assert marker_filter.flush() == ""
    assert marker_filter.flush() == ""


def test_a_trailing_marker_is_cleaned_once_at_flush() -> None:
    marker_filter = PreserveMarkerFilter()
    output = marker_filter.feed("===first===\n===last===") + marker_filter.flush()
    assert output == "first\nlast"
    assert marker_filter.flush() == ""


def test_crlf_and_trailing_blank_lines_are_not_rewritten_or_discarded() -> None:
    source = "===before===\r\n\r\n" + HTML + "\r\n\r\n\r\n"
    expected = "before\r\n\r\n" + HTML + "\r\n\r\n\r\n"
    _assert_streaming_output(source, expected)


def test_mixed_element_content_keeps_source_order_without_reentering_prose_cleanup() -> (
    None
):
    code = "```text\n!===\n===literal===\n```"
    svg = "<svg><text>===label===</text></svg>"
    source = f"===intro===\n{HTML}\n===middle===\n{svg}\n{code}\n===end==="
    expected = f"intro\n{HTML}\nmiddle\n{svg}\n{code}\nend"
    _assert_streaming_output(source, expected)


def test_a_paragraph_break_releases_unmatched_inline_source_without_flush() -> None:
    marker_filter = PreserveMarkerFilter()
    source = "Press the ` key.\n\n===After===\n"
    assert marker_filter.feed(source) == "Press the ` key.\n\nAfter\n"
    assert marker_filter.flush() == ""


def test_an_opaque_boundary_releases_unmatched_inline_source_without_flush() -> None:
    marker_filter = PreserveMarkerFilter()
    source = "Press the ` key.\n<div>a===b;</div>\n"
    assert marker_filter.feed(source) == source
    assert marker_filter.flush() == ""


@pytest.mark.parametrize("fence", ["!===", " 	!====	"])
def test_a_standalone_marker_inside_a_native_multiline_code_span_is_literal(
    fence: str,
) -> None:
    source = f"Use ``line\n{fence}\nend`` and ===after===\n"
    _assert_streaming_output(source, source.replace("===after===", "after"))


@pytest.mark.parametrize("opening", ["``` `", "````lang`info", "   ```lang\\`info"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("final_newline", [False, True])
def test_backtick_info_cannot_start_a_code_fence(
    opening: str, newline: str, final_newline: bool
) -> None:
    text = opening + newline + "===AfterInvalid===" + (newline if final_newline else "")
    _assert_streaming_output(text, text.replace("===AfterInvalid===", "AfterInvalid"))


@pytest.mark.parametrize("opening", ["``` `", "````lang`info"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_invalid_info_before_a_real_fence_does_not_expose_lesson_markers(
    opening: str, newline: str
) -> None:
    text = newline.join(
        [
            "===Before===",
            "",
            opening,
            "===AfterInvalid===",
            "```",
            "const equal = a === b;",
            "```",
            "",
            "===After===",
        ]
    )
    expected = (
        text.replace("===Before===", "Before")
        .replace("===AfterInvalid===", "AfterInvalid")
        .replace("===After===", "After")
    )
    _assert_streaming_output(text, expected)


@pytest.mark.parametrize("ending", ["", "\n===After==="])
def test_invalid_block_info_can_instead_be_a_valid_inline_code_span(
    ending: str,
) -> None:
    text = "```lang`info ===inside===```" + ending
    _assert_streaming_output(text, text.replace("===After===", "After"))


def test_invalid_info_does_not_end_a_multiline_inline_code_span() -> None:
    text = "``before\n```lang`info ===inside===\nclosing`` ===After==="
    _assert_streaming_output(text, text.replace("===After===", "After"))


def test_invalid_info_does_not_end_a_multiline_link_title() -> None:
    text = '[docs](url "title\n```lang`info ===hidden===") ===After==='
    _assert_streaming_output(text, text.replace("===After===", "After"))


def test_a_later_backtick_in_invalid_info_can_close_an_inline_span() -> None:
    text = "Press the ` key.\n```lang`info\n===After==="
    _assert_streaming_output(text, text.replace("===After===", "After"))


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_forward_reference_context_does_not_restore_invalid_info_fences(
    newline: str,
) -> None:
    text = newline.join(
        [
            "[docs][<script>]",
            "",
            "```lang`info",
            "===AfterInvalid===",
            "",
            "[<script>]: /docs",
            "",
        ]
    )
    _assert_streaming_output(text, text.replace("===AfterInvalid===", "AfterInvalid"))


@pytest.mark.parametrize("opening", ["```js", "~~~~lang`info"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_valid_fences_keep_code_with_either_line_ending(
    opening: str, newline: str
) -> None:
    closing = "````" if opening.startswith("`") else "~~~~"
    code = newline.join(
        [opening, "const equal = a === b;", "===literal===", closing, ""]
    )
    _assert_streaming_output(code + "===After===", code + "After")


def test_invalid_info_in_quoted_prose_uses_native_inline_rules() -> None:
    text = "> ```lang`info\n> ===body===\n"
    _assert_streaming_output(text, text.replace("===body===", "body"))


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_invalid_opener_text_inside_a_real_fence_stays_literal(newline: str) -> None:
    code = newline.join(["```js", "```bad`info", "===literal===", "```", ""])
    _assert_streaming_output(code + "===After===", code + "After")


@pytest.mark.parametrize("ending", ["\n", "\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize(
    "uri",
    [
        "git+ssh://example/a===b",
        "foo.bar:!===payload===",
        "AB:a===b",
        "a" * 32 + ":a===b",
        "a0+.-://example/a!===b===",
        "https://example/a===b",
        r"git+ssh://example/a`[x]\!===b===",
        "git+ssh://example/\u00a0===body===",
        "data:image/png;base64,a===b",
        "ab:",
    ],
)
def test_native_uri_autolinks_keep_source_across_stream_chunks(
    uri: str, ending: str
) -> None:
    """Native schemes and URI punctuation stay literal in classified prose."""
    source = f"===before=== <{uri}> ===after==={ending}"
    _assert_streaming_output(source, f"before <{uri}> after{ending}")
    _assert_streaming_output(f"===before==={ending}<{uri}>", f"before{ending}<{uri}>")


@pytest.mark.parametrize(
    "source",
    [
        "<x:a===b>",
        "<1ab:a===b>",
        "<git_ssh:a===b>",
        "<" + "a" * 33 + ":a===b>",
        "<git+ssh://a===b c>",
        "<git+ssh://a===b\tc>",
        "<git+ssh://a===b\nc>",
        "<git+ssh://a===b\x1fc>",
        "<git+ssh://a===b<c>",
        "<git+ssh://a===b",
        "<javascript:alert(===body===)>",
        "<vbscript:alert(===body===)>",
        "<file:a===b>",
        "<data:===body===>",
    ],
)
def test_rejected_uri_autolinks_keep_native_prose_cleanup(source: str) -> None:
    """Malformed, incomplete and rejected URI candidates remain ordinary prose."""
    _assert_streaming_output(
        source + " ===after===", source.replace("===", "") + " after"
    )


@pytest.mark.parametrize("ending", ["\n", "\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize(
    "source",
    [
        "[docs][<script>] ===before===\n\n[<script>]: /url\n\n"
        "<git+ssh://example/a===b> ===after===",
        "<git+ssh://example/a===b> ===before===\n\n"
        "[docs][<script>] ===after===\n\n[<script>]: /url",
        "![===caption=== <git+ssh://example/a===b>](/img) ===after===",
        "![<script>===caption===</script> <git+ssh://example/a===b>](/img) ===after===",
        "![===caption=== <git+ssh://example/a===b>][pic] ===after===\n\n[pic]: /img",
        "![outer ![<script>===caption=== <git+ssh://example/a===b>](/inner)]"
        "(/outer) ===after===",
        '[outer <git+ssh://example/a===b>](url "<script>") ===after===',
    ],
)
def test_native_uri_autolinks_keep_source_in_images_and_reference_paragraphs(
    source: str, ending: str
) -> None:
    """Image descriptions and deferred references use the same native URI grammar."""
    source = source.replace("\n", ending)
    expected = (
        source.replace("===before===", "before")
        .replace("===after===", "after")
        .replace("===caption===", "caption")
    )
    _assert_streaming_output(source + ending, expected + ending)
    if ending == "\n":
        _assert_streaming_output(source, expected)
