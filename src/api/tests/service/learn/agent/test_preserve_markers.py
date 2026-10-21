"""Cover the removal of verbatim markers from the engine's streamed text."""

from __future__ import annotations

import random

import pytest
from flaskr.service.learn.agent.preserve_markers import PreserveMarkerFilter


def _through(text: str, seed: int) -> str:
    """Push the text through in random-sized chunks, the way a model streams it."""
    rng = random.Random(seed)  # noqa: S311 -- chunk sizes, not secrets
    marker_filter = PreserveMarkerFilter()
    out: list[str] = []
    index = 0
    while index < len(text):
        step = rng.randint(1, 6)
        out.append(marker_filter.feed(text[index : index + step]))
        index += step
    out.append(marker_filter.flush())
    return "".join(out)


def test_inline_markers_are_removed_and_the_content_between_them_kept() -> None:
    """A listener heard the markers read aloud; what they wrap is the lesson."""
    text = (
        "我给自己定下了一个目标： ===帮助 100 万人顺利走进 AGI 时代=== 这就是原因。\n"
    )
    for seed in range(30):
        assert (
            _through(text, seed)
            == "我给自己定下了一个目标： 帮助 100 万人顺利走进 AGI 时代 这就是原因。\n"
        ), f"seed {seed}"


def test_fence_lines_are_dropped_with_their_newline() -> None:
    text = "before\n!===\nkept exactly\n!===\nafter\n"
    for seed in range(30):
        assert _through(text, seed) == "before\nkept exactly\nafter\n", f"seed {seed}"


def test_code_is_left_alone() -> None:
    """`===` inside a code fence is an operator, not a marker."""
    text = "```js\nif (a === b) {}\n```\nprose ===kept=== end\n"
    for seed in range(30):
        assert (
            _through(text, seed) == "```js\nif (a === b) {}\n```\nprose kept end\n"
        ), f"seed {seed}"


def test_a_marker_split_across_chunks_is_still_removed() -> None:
    marker_filter = PreserveMarkerFilter()
    out = marker_filter.feed("x =")
    out += marker_filter.feed("=")
    out += marker_filter.feed("=y===")
    out += marker_filter.flush()
    assert out == "x y"


def test_a_fragment_that_never_becomes_a_marker_is_released_as_text() -> None:
    """Held back only while it could still be a marker; text once the turn ends."""
    marker_filter = PreserveMarkerFilter()
    assert marker_filter.feed("score: a ==") == "score: a "
    assert marker_filter.flush() == "=="


def test_nothing_else_is_touched() -> None:
    text = "Plain prose, with = signs, a == b, and a line\n\n---\n\nof more prose.\n"
    for seed in range(30):
        assert _through(text, seed) == text, f"seed {seed}"


def test_a_fence_closes_only_with_its_own_kind_and_length() -> None:
    """CommonMark: a tilde line does not close a backtick fence, nor a shorter fence a longer one.

    Closed early, the rest of the block was read as prose and its `===` operators removed.
    """
    text = (
        "````js\n"
        "~~~\n"  # a tilde line inside a backtick block is code
        "```\n"  # too short to close a four-backtick fence
        "if (a === b) {}\n"
        "````\n"  # this one closes it
        "prose ===kept===\n"
    )
    for seed in range(30):
        assert _through(text, seed) == text.replace("===kept===", "kept"), (
            f"seed {seed}"
        )


def test_a_fence_line_with_trailing_text_does_not_close_the_block() -> None:
    text = "```\n``` not a closer\na === b\n```\nafter ===x===\n"
    for seed in range(30):
        assert _through(text, seed) == text.replace("===x===", "x"), f"seed {seed}"


def test_the_output_is_the_same_wherever_the_stream_is_cut() -> None:
    """Every character boundary, not a sample of them: a cut inside a marker is the hard case."""
    lesson = (
        "Prose with ===kept=== inline.\n\n"
        "!===\nverbatim block\n!===\n\n"
        "```js\nif (a === b) {}\n```\n\nEnd.\n"
    )

    def filtered(cut: int) -> str:
        marker_filter = PreserveMarkerFilter()
        return (
            marker_filter.feed(lesson[:cut])
            + marker_filter.feed(lesson[cut:])
            + marker_filter.flush()
        )

    whole = filtered(len(lesson))
    for cut in range(len(lesson) + 1):
        assert filtered(cut) == whole, f"cut at {cut} changed the output"
    assert "kept" in whole
    assert "verbatim block" in whole
    # The operator inside the code fence survives; the markers around prose do not.
    assert "a === b" in whole
    assert "===kept===" not in whole


def _from_chunks(chunks: list[str]) -> str:
    marker_filter = PreserveMarkerFilter()
    return (
        "".join(marker_filter.feed(chunk) for chunk in chunks) + marker_filter.flush()
    )


def _assert_streaming_output(text: str, expected: str) -> None:
    """Check each two-part cut, single-character delivery, and sampled model chunks."""
    for cut in range(len(text) + 1):
        assert _from_chunks([text[:cut], text[cut:]]) == expected, f"cut at {cut}"
    assert _from_chunks(list(text)) == expected, "single-character chunks"
    for seed in range(10):
        assert _through(text, seed) == expected, f"seed {seed}"


@pytest.mark.parametrize(
    ("tag", "body"),
    [
        ("script", "const isPick = (candidate === selected);"),
        ("style", '.candidate::after { content: "===selected==="; }'),
    ],
)
def test_html_raw_text_preserves_code_and_filters_neighboring_prose(
    tag: str, body: str
) -> None:
    text = f"===before===<{tag}>{body}</{tag}>===after==="
    expected = f"before<{tag}>{body}</{tag}>after"
    _assert_streaming_output(text, expected)


def test_raw_text_ends_before_another_block_on_the_same_line() -> None:
    text = (
        "===before===<script>const equal = a === b;</script>"
        '===between===<style>p::after { content: "==="; }</style>===after==='
    )
    expected = (
        "before<script>const equal = a === b;</script>"
        'between<style>p::after { content: "==="; }</style>after'
    )
    _assert_streaming_output(text, expected)


@pytest.mark.parametrize(
    "opening",
    [
        '<ScRiPt type="text/javascript" data-note="> <style>">',
        "<script data-note='> <style>'>",
        '<script\n type="text/javascript"\n data-note="a > b">',
    ],
    ids=["mixed-case-double-quotes", "single-quotes", "multiline-attributes"],
)
def test_script_attributes_do_not_end_or_nest_the_raw_text_tag(opening: str) -> None:
    protected = opening + "const equal = a === b;</sCrIpT>"
    _assert_streaming_output(protected + "===after===", protected + "after")


@pytest.mark.parametrize(
    "opening",
    [
        "<script =>",
        "<script a= >",
        "<script value=`bad`>",
        "<script / >",
        "<style =>",
        "<textarea =>",
        "<title =>",
        "<iframe =>",
    ],
)
def test_invalid_inline_raw_text_openers_do_not_hide_prose_markers(
    opening: str,
) -> None:
    """Markdown renders malformed inline tags as ordinary lesson text."""
    text = f"Explain {opening} literally. ===after==="
    _assert_streaming_output(text, text.replace("===after===", "after"))


@pytest.mark.parametrize("indent", ["    ", "\t"])
def test_a_malformed_tag_in_an_indented_paragraph_continuation_is_literal(
    indent: str,
) -> None:
    text = f"Paragraph\n{indent}<script => literal\n===after==="
    _assert_streaming_output(text, text.replace("===after===", "after"))


@pytest.mark.parametrize("parent", ["textarea", "title"])
def test_a_literal_parent_opener_does_not_hide_a_later_real_script(parent: str) -> None:
    text = (
        f"Explain <{parent} =><script>const equal = a === b;</{parent}> "
        "===source===</script> ===after==="
    )
    _assert_streaming_output(text, text.replace("===after===", "after"))


@pytest.mark.parametrize("prefix", ["", "   ", "==="])
@pytest.mark.parametrize("tag", ["script", "style"])
def test_raw_html_blocks_allow_browser_recoverable_attribute_syntax(
    prefix: str, tag: str
) -> None:
    """CommonMark's script/style blocks do not require valid inline attributes."""
    html = f"<{tag} =>const equal = a === b;</{tag}>\n"
    _assert_streaming_output(
        prefix + html + "===after===", prefix.strip("=") + html + "after"
    )


def test_a_malformed_textarea_block_still_ignores_fake_nested_script_tags() -> None:
    text = "<textarea =><script>literal ===body===</textarea>\n===after==="
    expected = text.replace("===body===", "body").replace("===after===", "after")
    _assert_streaming_output(text, expected)


@pytest.mark.parametrize("tag", ["script", "style"])
def test_html_visuals_preserve_scripts_with_browser_recoverable_attributes(
    tag: str,
) -> None:
    html = f"<div>\n    <{tag} =>const equal = a === b;</{tag}>\n</div>\n"
    _assert_streaming_output(html + "===after===", html + "after")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "<!-- <script> -->===after===",
            "<!-- <script> -->after",
        ),
        (
            "<!--\n<script>\n-->===after===",
            "<!--\n<script>\n-->after",
        ),
        (
            '<div title="<script>">===body===</div>===after===',
            '<div title="<script>">body</div>after',
        ),
        (
            "<div title='<style>'>===body===</div>===after===",
            "<div title='<style>'>body</div>after",
        ),
        (
            "<scripture>===body===</scripture>===after===",
            "<scripture>body</scripture>after",
        ),
        (
            "&lt;script&gt;===body===&lt;/script&gt;===after===",
            "&lt;script&gt;body&lt;/script&gt;after",
        ),
    ],
    ids=[
        "comment",
        "multiline-comment",
        "double-quoted-attribute",
        "single-quoted-attribute",
        "longer-tag-name",
        "escaped-tag",
    ],
)
def test_html_lookalikes_do_not_protect_prose(text: str, expected: str) -> None:
    _assert_streaming_output(text, expected)


@pytest.mark.parametrize(
    "text",
    [
        'Explain <span title="unfinished ===after===',
        "Explain <!-- unfinished ===after===",
        "Explain <?instruction unfinished ===after===",
        "Explain <![CDATA[unfinished ===after===",
        'Explain <script data-note="unfinished ===after===',
        "Explain </svg ===after===",
        '<span title="unfinished ===after===',
        'Explain <span title="unfinished\nmore ===after===',
        'Explain <span title="unfinished `a === b` ===after===',
        "Paragraph\n12. <!-- unfinished ===after===",
    ],
)
def test_unfinished_inline_html_is_replayed_as_literal_markdown(text: str) -> None:
    _assert_streaming_output(text, text.replace("===after===", "after"))


@pytest.mark.parametrize("opener", ["<!-- unfinished ", "<?instruction ", "<![CDATA["])
def test_literal_unfinished_html_can_be_followed_by_a_real_script(opener: str) -> None:
    text = f"Explain {opener}<script>const equal = a === b;</script> ===after==="
    _assert_streaming_output(text, text.replace("===after===", "after"))


@pytest.mark.parametrize(
    "html",
    [
        '<div title="unfinished ===attribute===',
        '<script data-note="unfinished ===attribute===',
        '<style data-note="unfinished ===attribute===',
        '<textarea data-note="unfinished ===attribute===',
        '<title data-note="unfinished ===attribute===',
        "<!-- unfinished ===attribute===",
        "<?instruction unfinished ===attribute===",
        "<![CDATA[unfinished ===attribute===",
        "<!DOCTYPE html unfinished ===attribute===",
        "> <!-- unfinished ===attribute===",
        '- <div title="unfinished ===attribute===',
        'Intro <svg title="unfinished ===attribute===',
        '<div>Intro <span title="unfinished ===attribute===',
        '<svg><g></g><span title="unfinished ===attribute===',
        "<script>const equal = a === b; </scr",
        '<style>.node { content: "==="; } </sty',
    ],
)
def test_unfinished_real_html_keeps_its_original_source(html: str) -> None:
    _assert_streaming_output(html, html)


def test_unfinished_inline_html_preserves_the_prefix_already_streamed() -> None:
    marker_filter = PreserveMarkerFilter()
    prefix = marker_filter.feed("Explain ")
    assert prefix == "Explain "
    assert marker_filter.feed('<span title="unfinished ===after===') == ""
    assert prefix + marker_filter.flush() == 'Explain <span title="unfinished after'
    assert marker_filter.flush() == ""


@pytest.mark.parametrize(
    "opaque",
    [
        "<![CDATA[<script> a === b > <style>]]>",
        "<?instruction <script> a === b > <style> ?>",
        "<![CDATA[\n<script> a === b;\n]]>",
        "<?instruction\n<style> a === b;\n?>",
    ],
)
def test_opaque_html_constructs_do_not_open_raw_text(opaque: str) -> None:
    text = f"<svg>{opaque}</svg>\n===after==="
    _assert_streaming_output(text, text.replace("===after===", "after"))


@pytest.mark.parametrize("opener", ["<![CDATA[", "<?instruction "])
def test_unclosed_opaque_html_is_preserved_until_end_of_stream(opener: str) -> None:
    text = f"===before==={opener}<script> ===literal==="
    _assert_streaming_output(text, text.replace("===before===", "before"))


@pytest.mark.parametrize(
    "opaque", ["<![CDATA[` <script>]]>", "<?instruction ` <script> ?>"]
)
def test_opaque_html_blocks_end_unmatched_inline_candidates(opaque: str) -> None:
    text = f"Press the ` key.\n{opaque}\n===after==="
    _assert_streaming_output(text, text.replace("===after===", "after"))


@pytest.mark.parametrize(
    ("opener", "closer"),
    [("<![CDATA[", "]]>"), ("<?instruction", "?>"), ("<!--", "-->")],
)
def test_multiline_opaque_block_allows_following_indented_code(
    opener: str, closer: str
) -> None:
    text = f"{opener}\n<script> literal\n{closer}\n    <script> literal\n===after==="
    _assert_streaming_output(text, text.replace("===after===", "after"))


@pytest.mark.parametrize(
    ("opener", "closer"),
    [("<![CDATA[", "]]>"), ("<?instruction", "?>"), ("<!--", "-->")],
)
def test_inline_opaque_markup_does_not_end_a_prose_paragraph(
    opener: str, closer: str
) -> None:
    text = (
        f"Paragraph {opener}\n<script> fake\n{closer}\n"
        "    <script> literal\n===source==="
    )
    _assert_streaming_output(text, text)


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_html_inside_a_markdown_code_fence_does_not_leak_raw_text_state(
    fence: str,
) -> None:
    code = f"{fence}html\n<script>const equal = a === b;\n{fence}\n"
    _assert_streaming_output(code + "===after===\n", code + "after\n")


@pytest.mark.parametrize("tag", ["script", "style"])
def test_markdown_fences_and_marker_lines_inside_raw_text_are_literal(tag: str) -> None:
    protected = f"<{tag}>\n```\n!===\na === b\n~~~\n</{tag}>\n"
    _assert_streaming_output(protected + "===after===\n", protected + "after\n")


@pytest.mark.parametrize(
    "protected",
    [
        '<script>const equal = a === b; const unfinished = "===',
        "<script>const equal = a === b;</scr",
        '<style>p::after { content: "===',
        '<style>p::after { content: "==="; }</sty',
    ],
    ids=["script-body", "script-close-prefix", "style-body", "style-close-prefix"],
)
def test_unclosed_raw_text_is_preserved_when_the_stream_ends(protected: str) -> None:
    _assert_streaming_output(protected, protected)


@pytest.mark.parametrize("tag", ["script", "style"])
def test_raw_text_closing_tag_requires_a_name_boundary(tag: str) -> None:
    protected = f"<{tag}>a === b;</{tag}ure>c === d;</{tag}>"
    _assert_streaming_output(protected + "===after===", protected + "after")


@pytest.mark.parametrize("tag", ["script", "style"])
def test_html_self_closing_syntax_still_opens_nonvoid_raw_text(tag: str) -> None:
    protected = f"<{tag}/>a === b;</{tag}>"
    _assert_streaming_output(protected + "===after===", protected + "after")


@pytest.mark.parametrize(
    "tag", ["textarea", "title", "iframe", "xmp", "noembed", "noframes"]
)
def test_html_text_parent_does_not_open_nested_script_or_style(tag: str) -> None:
    parent = f"<{tag}><script> literal </div> ===sample=== <style> literal</{tag}>"
    html = "<div>" + parent + "</div>\n"
    markdown = "Use `<script>` and \\<style>. ===after===\n"
    expected = html.replace("===sample===", "sample")
    _assert_streaming_output(
        html + markdown, expected + markdown.replace("===after===", "after")
    )


@pytest.mark.parametrize(
    "tag", ["textarea", "title", "iframe", "xmp", "noembed", "noframes"]
)
def test_html_text_parent_ends_before_real_script_and_following_prose(tag: str) -> None:
    parent = (
        f"<{tag}><script>literal</script><style>literal ===sample===</{tag}ure>"
        f"more literal</{tag.upper()}>"
    )
    script = "<script>const equal = a === b;</script>"
    expected = parent.replace("===sample===", "sample")
    _assert_streaming_output(
        parent + script + "===after===", expected + script + "after"
    )


@pytest.mark.parametrize(
    "tag", ["textarea", "title", "iframe", "xmp", "noembed", "noframes"]
)
def test_html_text_parent_is_preserved_when_its_close_is_unfinished(tag: str) -> None:
    parent = f"<{tag}><script>literal</script><style>literal===sample===</{tag[:3]}"
    _assert_streaming_output(parent, parent.replace("===sample===", "sample"))


@pytest.mark.parametrize(
    "code",
    [
        "`<script> a === b`",
        "``<style> a === b``",
        "``<script> ` a === b``",
        "`<style> `` a === b`",
        "`<script>\na === b`",
    ],
    ids=[
        "single-run",
        "double-run",
        "shorter-run-is-content",
        "longer-run-is-content",
        "multiline",
    ],
)
def test_html_lookalikes_inside_inline_code_do_not_protect_following_prose(
    code: str,
) -> None:
    text = f"===before=== Use {code} here. ===after==="
    expected = f"before Use {code} here. after"
    _assert_streaming_output(text, expected)


def test_a_closing_backtick_run_split_between_chunks_must_match_the_opener() -> None:
    chunks = ["Use `<script> first `", "` a === b`", " ===after==="]
    expected = "Use `<script> first `` a === b` after"
    assert _from_chunks(chunks) == expected
    _assert_streaming_output("".join(chunks), expected)


@pytest.mark.parametrize("tag", ["script", "style"])
@pytest.mark.parametrize("backslash_count", [1, 2, 3, 4])
def test_only_an_odd_backslash_run_escapes_an_html_opening(
    tag: str, backslash_count: int
) -> None:
    prefix = "Use " + "\\" * backslash_count
    if backslash_count % 2:
        text = prefix + f"<{tag}> ===after==="
        expected = prefix + f"<{tag}> after"
    else:
        protected = prefix + f"<{tag}>a === b;</{tag}>"
        text = protected + " ===after==="
        expected = protected + " after"
    _assert_streaming_output(text, expected)


def test_html_escape_detection_uses_source_characters_before_marker_removal() -> None:
    text = "Use \\===<script>a === b;</script> ===after==="
    expected = "Use \\<script>a === b;</script> after"
    _assert_streaming_output(text, expected)


@pytest.mark.parametrize("backslash_count", [1, 3])
def test_an_escaped_backtick_does_not_hide_a_real_script(
    backslash_count: int,
) -> None:
    prefix = "Use " + "\\" * backslash_count + "`"
    protected = "<script>const label = `value`; const equal = a === b;</script>"
    _assert_streaming_output(
        prefix + protected + " ===after===", prefix + protected + " after"
    )


def test_a_backslash_inside_inline_code_does_not_escape_the_closer() -> None:
    code = "`<script> a === b \\`"
    _assert_streaming_output("Use " + code + " ===after===", "Use " + code + " after")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Use ` unmatched <script>a === b;</script> ===after===",
            "Use ` unmatched <script>a === b;</script> after",
        ),
        (
            "Use `` unmatched\n!===\n===kept===\n!===\n",
            "Use `` unmatched\nkept\n",
        ),
        (
            "Use ` unmatched\n~~~js\n<script>a === b;\n~~~\n===after===\n",
            "Use ` unmatched\n~~~js\n<script>a === b;\n~~~\nafter\n",
        ),
        (
            "Use ` unmatched ``<style> a === b`` ===after===",
            "Use ` unmatched ``<style> a === b`` after",
        ),
    ],
    ids=["real-script", "marker-fences", "code-fence", "later-paired-span"],
)
def test_an_unmatched_inline_opener_does_not_change_later_markup(
    text: str, expected: str
) -> None:
    _assert_streaming_output(text, expected)


@pytest.mark.parametrize(
    "html",
    [
        "<div>`<script>const label = `value`; const equal = a === b;</script></div>",
        "<div>\\<script>const equal = a === b;</script></div>",
        "<div>\\<style>p::after { content: '===literal==='; }</style></div>",
    ],
    ids=[
        "backtick-text-before-script",
        "backslash-before-script",
        "backslash-before-style",
    ],
)
def test_markdown_delimiters_in_an_html_container_do_not_hide_raw_text(
    html: str,
) -> None:
    _assert_streaming_output(html + "\n===after===", html + "\nafter")


def test_markers_around_an_html_container_do_not_hide_its_block_context() -> None:
    html = "<div>`<script>const label = `value`; const equal = a === b;</script></div>"
    _assert_streaming_output("===" + html + "===\n===after===", html + "\nafter")


@pytest.mark.parametrize(
    ("prefix", "container"),
    [("<!DOCTYPE html>", "html"), ("<!-- visual -->", "div")],
    ids=["doctype", "comment"],
)
def test_html_metadata_does_not_hide_the_following_container(
    prefix: str, container: str
) -> None:
    html = (
        f"{prefix}<{container}>`<script>"
        f"const label = `value`; const equal = a === b;</script></{container}>"
    )
    _assert_streaming_output(html + "\n===after===", html + "\nafter")


def test_nested_html_containers_keep_scripts_protected_until_the_outer_close() -> None:
    html = (
        "<div>\n<div>===inner===</div>\n"
        "`<script>const markup = `<div>`; const equal = a === b;</script>\n"
        "===outer===</div>\n"
    )
    expected = html.replace("===inner===", "inner").replace("===outer===", "outer")
    _assert_streaming_output(html + "===after===", expected + "after")


def test_markdown_literals_resume_after_an_html_container_closes() -> None:
    html = "<div>===body===<script>const equal = a === b;</script></div>\n"
    markdown = "Use `<script>` and \\<style> here. ===after===\n"
    _assert_streaming_output(
        html + markdown,
        html.replace("===body===", "body") + markdown.replace("===after===", "after"),
    )


@pytest.mark.parametrize("tag", ["<br>", "<br />"])
def test_a_void_html_tag_does_not_disable_markdown_literal_tags(tag: str) -> None:
    markdown = "Use `<script>` and \\<style> here. ===after==="
    _assert_streaming_output(
        tag + "\n" + markdown, tag + "\n" + markdown.replace("===after===", "after")
    )


@pytest.mark.parametrize(
    ("opening", "closing"),
    [
        ("<div>", "</div>"),
        ("<!DOCTYPE html><html><body>", "</body></html>"),
        ("<!-- visual --><div>", "</div>"),
        ("===<div>", "</div>==="),
    ],
    ids=[
        "container",
        "doctype-root",
        "comment-container",
        "marker-wrapped-container",
    ],
)
def test_a_new_html_block_interrupts_an_unmatched_inline_opener(
    opening: str, closing: str
) -> None:
    script = "\\<script>const label = `value`; const equal = a === b;</script>"
    html = opening + script + closing
    expected_html = html.removeprefix("===").removesuffix("===")
    _assert_streaming_output(
        "Use ` unmatched\n" + html + "\n===after===\n",
        "Use ` unmatched\n" + expected_html + "\nafter\n",
    )


@pytest.mark.parametrize("blank", ["", " ", "\t"], ids=["empty", "space", "tab"])
def test_a_blank_line_interrupts_an_unmatched_inline_opener(blank: str) -> None:
    text = f"Press the ` key.\n{blank}\n===Important=== Use `x`.\n"
    expected = f"Press the ` key.\n{blank}\nImportant Use `x`.\n"
    _assert_streaming_output(text, expected)


def test_a_blank_line_releases_unmatched_source_before_the_stream_ends() -> None:
    marker_filter = PreserveMarkerFilter()
    text = "Press the ` key.\n\n===Important=== Use `x`.\n"
    expected = "Press the ` key.\n\nImportant Use `x`.\n"
    assert marker_filter.feed(text) == expected
    assert marker_filter.flush() == ""


def test_an_html_block_releases_unmatched_source_before_the_stream_ends() -> None:
    marker_filter = PreserveMarkerFilter()
    html = "<div><script>const equal = a === b;</script></div>\n"
    text = "Press the ` key.\n" + html + "===after===\n"
    expected = "Press the ` key.\n" + html + "after\n"
    assert marker_filter.feed(text) == expected
    assert marker_filter.flush() == ""


def test_released_paragraphs_and_html_blocks_preserve_source_order() -> None:
    html = "<div><script>const equal = a === b;</script></div>\n"
    text = (
        "Press the ` key.\n\n===First=== Use `x`.\n\n"
        "Press the `` key.\n" + html + "===Last===\n"
    )
    expected = (
        "Press the ` key.\n\nFirst Use `x`.\n\nPress the `` key.\n" + html + "Last\n"
    )
    _assert_streaming_output(text, expected)
    for chunks in ([text], list(text)):
        marker_filter = PreserveMarkerFilter()
        assert "".join(marker_filter.feed(chunk) for chunk in chunks) == expected
        assert marker_filter.flush() == ""


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_an_inline_opener_cannot_pair_with_backticks_inside_a_code_fence(
    fence: str,
) -> None:
    code = f"{fence}js\nconst x = `foo`; a === b;\n{fence}\n"
    text = "Press the ` key.\n" + code + "===after===\n"
    expected = "Press the ` key.\n" + code + "after\n"
    _assert_streaming_output(text, expected)
    marker_filter = PreserveMarkerFilter()
    assert marker_filter.feed(text) == expected
    assert marker_filter.flush() == ""


@pytest.mark.parametrize(
    "fence", ["!===", " \t!=====\t "], ids=["plain", "padded-long"]
)
def test_a_marker_fence_interrupts_an_unmatched_inline_opener(fence: str) -> None:
    text = (
        f"Press the ` key.\n{fence}\n===Important=== Use `x`.\n{fence}\n===after===\n"
    )
    expected = "Press the ` key.\nImportant Use `x`.\nafter\n"
    _assert_streaming_output(text, expected)
    marker_filter = PreserveMarkerFilter()
    assert marker_filter.feed(text) == expected
    assert marker_filter.flush() == ""


@pytest.mark.parametrize(
    "line", ["!=== =", "!=== \t=", " \t!===== ", "!=== = still text"]
)
def test_a_partial_marker_fence_cannot_end_a_valid_inline_code_span(line: str) -> None:
    text = "``\n" + line + "``"
    _assert_streaming_output(text, text)


def test_a_partial_marker_fence_cannot_end_a_valid_link_title() -> None:
    text = '[docs](url "title\n!=== =") ===after==='
    _assert_streaming_output(text, text.replace("===after===", "after"))


@pytest.mark.parametrize("ending", ["", "\n"])
def test_a_real_marker_fence_at_eof_still_ends_an_unmatched_span(ending: str) -> None:
    text = "Press the ` key.\n!===" + ending
    _assert_streaming_output(text, "Press the ` key.\n")


def test_a_complete_marker_fence_keeps_following_html_outside_the_span() -> None:
    html = "<div><script>const label = `value`; const equal = a === b;</script></div>\n"
    text = "Press the ` key.\n!===\n" + html + "===after==="
    _assert_streaming_output(text, "Press the ` key.\n" + html + "after")


def test_a_partial_marker_fence_keeps_held_code_until_the_turn_finishes() -> None:
    marker_filter = PreserveMarkerFilter()
    out = marker_filter.feed("``\n!=== =")
    out += marker_filter.feed("``")
    out += marker_filter.flush()
    assert out == "``\n!=== =``"
    assert marker_filter.flush() == ""


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ('[===docs===](url "<script>")', '[docs](url "<script>")'),
        ("![===image===](url '<style>')", "![image](url '<style>')"),
        ("[docs](url (<script>))", "[docs](url (<script>))"),
        ('[docs](docs(a(b)c) "<style>")', '[docs](docs(a(b)c) "<style>")'),
        (
            r'[docs](docs\(part\) "<script> \"quoted\"")',
            r'[docs](docs\(part\) "<script> \"quoted\"")',
        ),
        (
            r"[docs](<docs/\<script\>> '<style>')",
            r"[docs](<docs/\<script\>> '<style>')",
        ),
        ("[docs](docs<script>)", "[docs](docs<script>)"),
        ('[[===docs===]](url "<script>")', '[[docs]](url "<script>")'),
        (r'[===docs\]===](url "<style>")', r'[docs\]](url "<style>")'),
        ('[docs](url\n "<script>")', '[docs](url\n "<script>")'),
        (
            '[<script>a === b;</script>](url "<style>")',
            '[<script>a === b;</script>](url "<style>")',
        ),
    ],
    ids=[
        "link-title",
        "image-title",
        "parenthesized-title",
        "nested-destination",
        "escaped-parentheses-and-quotes",
        "escaped-angle-destination",
        "bare-destination",
        "nested-label",
        "escaped-label-bracket",
        "multiline-title",
        "actual-html-in-label",
    ],
)
def test_inline_link_metadata_does_not_open_html_raw_text(
    link: str, expected: str
) -> None:
    _assert_streaming_output(link + " ===after===\n", expected + " after\n")


@pytest.mark.parametrize(
    "prefix",
    [
        '[docs](url "',
        "[docs](url ",
        r'\[docs](url "',
        '[docs\n\n](url "',
    ],
    ids=["unfinished-title", "invalid-title", "escaped-label", "broken-label"],
)
def test_invalid_or_unfinished_links_do_not_hide_real_html(prefix: str) -> None:
    script = "<script>const equal = a === b;</script>"
    text = prefix + script + " ===after===\n"
    _assert_streaming_output(text, prefix + script + " after\n")


def test_an_escaped_space_does_not_make_a_bare_link_destination_valid() -> None:
    prefix = r'[docs](url\ space "===title=== '
    script = "<script>const equal = a === b;</script>"
    _assert_streaming_output(
        prefix + script + '") ===after===\n',
        prefix.replace("===title===", "title") + script + '") after\n',
    )


@pytest.mark.parametrize("inner", ["[inner](url)", r"\![inner](url)"])
def test_a_nested_link_disables_the_outer_link_metadata(inner: str) -> None:
    text = f'[outer {inner}](url "===title=== <script>a === b;</script>") ===after==='
    expected = text.replace("===title===", "title").replace("===after===", "after")
    _assert_streaming_output(text, expected)


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        (
            '[![===alt===](image)](url "<script>")',
            '[![alt](image)](url "<script>")',
        ),
        (
            '![[===label===](url)](image "<style>")',
            '![[label](url)](image "<style>")',
        ),
        (
            '[outer ![image [===inner===](i)](p)](o "<script>")',
            '[outer ![image [inner](i)](p)](o "<script>")',
        ),
    ],
)
def test_images_keep_valid_nested_link_labels(link: str, expected: str) -> None:
    _assert_streaming_output(link + " ===after===", expected + " after")


def test_an_invalid_image_label_propagates_its_inner_link_to_the_outer_label() -> None:
    text = (
        '[outer ![image [inner](i)]broken](o "===title=== <script>a === b;</script>")'
    )
    _assert_streaming_output(
        text + " ===after===", text.replace("===title===", "title") + " after"
    )


@pytest.mark.parametrize(
    ("definition", "expected"),
    [
        ("[===docs===]: <script>\n", "[docs]: <script>\n"),
        ('[docs]: url "<script>"\n', '[docs]: url "<script>"\n'),
        ("[docs]: <url> '<style>'\n", "[docs]: <url> '<style>'\n"),
        ('   [docs]: url\n  "<script>"\n', '   [docs]: url\n  "<script>"\n'),
        ("[docs]: url\n (<style>)\n", "[docs]: url\n (<style>)\n"),
    ],
    ids=[
        "angle-destination",
        "title",
        "angle-and-title",
        "next-line-title",
        "paren-title",
    ],
)
def test_reference_link_metadata_does_not_open_html_raw_text(
    definition: str, expected: str
) -> None:
    _assert_streaming_output(definition + "\n===after===\n", expected + "\nafter\n")


@pytest.mark.parametrize(
    "following",
    [
        "<script>const equal = a === b;</script>\n",
        "```js\nconst value = `literal`; a === b;\n```\n",
    ],
    ids=["html-block", "code-fence"],
)
def test_reference_definitions_do_not_consume_the_following_block(
    following: str,
) -> None:
    definition = "[docs]: <script>\n"
    text = definition + following + "===after===\n"
    expected = definition + following + "after\n"
    _assert_streaming_output(text, expected)
    marker_filter = PreserveMarkerFilter()
    assert marker_filter.feed(text) == expected
    assert marker_filter.flush() == ""


@pytest.mark.parametrize(
    "prefix",
    [
        "[docs]: url ===junk=== ",
        '[docs]: url\n"',
        "[]: url ===junk=== ",
        "[  ]: url ===junk=== ",
    ],
)
def test_invalid_reference_titles_do_not_hide_real_html(prefix: str) -> None:
    script = "<script>const equal = a === b;</script>"
    text = prefix + script + " ===after===\n"
    expected = prefix.replace("===junk===", "junk") + script + " after\n"
    _assert_streaming_output(text, expected)


def test_an_invalid_next_line_title_keeps_the_valid_reference_destination() -> None:
    text = "[docs]: <script>\n (===title=== (bad))\n\n===after===\n"
    _assert_streaming_output(text, "[docs]: <script>\n (title (bad))\n\nafter\n")


def test_a_valid_next_line_reference_title_is_preserved_at_eof() -> None:
    text = '[docs]: url\n "===title=== <script>"'
    _assert_streaming_output(text, text)


@pytest.mark.parametrize(
    "definition",
    ["[<script>]: /url", "[===<script>===]: /url", "[<SCRIPT>]: /url"],
)
@pytest.mark.parametrize("defined_first", [False, True])
def test_full_reference_labels_use_actual_definitions_at_turn_end(
    definition: str, defined_first: bool
) -> None:
    reference = "[docs][<script>] ===after==="
    text = (
        definition + "\n\n" + reference
        if defined_first
        else reference + "\n\n" + definition
    )
    expected = text.replace("===after===", "after").replace(
        "===<script>===", "<script>"
    )
    _assert_streaming_output(text, expected)


def test_duplicate_reference_definitions_keep_all_their_labels_out_of_html() -> None:
    text = "[<script>]: /first\n[<script>]: /second\n\n[docs][<script>] ===after===\n"
    _assert_streaming_output(text, text.replace("===after===", "after"))


@pytest.mark.parametrize(
    "reference",
    [
        "[docs][<script>/*]*/ const eq = a === b;</script>",
        "[docs][<script>const eq = a === b;</script>",
        "[docs][nested[<script>const eq = a === b;</script>]]",
        "[<script>const eq = a === b;</script>](url)",
        "[<script>const eq = a === b;</script>]",
    ],
    ids=["undefined", "unfinished", "nested-invalid", "visible-label", "shortcut"],
)
def test_unresolved_reference_candidates_preserve_real_script_operators(
    reference: str,
) -> None:
    text = reference + " ===after===\n"
    _assert_streaming_output(text, reference + " after\n")


def test_fake_definitions_in_code_do_not_resolve_html_looking_references() -> None:
    reference = "[docs][<script>/*]*/ const eq = a === b;</script>"
    text = reference + " ===after===\n\n```md\n[<script>/*]: /url\n```\n"
    _assert_streaming_output(text, text.replace("===after===", "after"))


def test_reference_replay_preserves_existing_private_use_characters() -> None:
    text = "\ue000 ===before=== [docs][<script>] ===after===\n\n[<script>]: /url"
    expected = text.replace("===before===", "before").replace("===after===", "after")
    _assert_streaming_output(text, expected)


def test_only_the_ambiguous_reference_suffix_waits_for_a_future_definition() -> None:
    marker_filter = PreserveMarkerFilter()
    emitted = marker_filter.feed("===before=== [docs][<script>] ===after===\n\n")
    assert emitted == "before [docs]["
    assert marker_filter.feed("[<script>]: /url") == ""
    assert emitted + marker_filter.flush() == (
        "before [docs][<script>] after\n\n[<script>]: /url"
    )
    assert marker_filter.flush() == ""


def test_ordinary_references_continue_streaming_without_waiting_for_definitions() -> (
    None
):
    marker_filter = PreserveMarkerFilter()
    emitted = marker_filter.feed("[docs][ordinary] ===after===\n\n")
    assert emitted == "[docs][ordinary] after\n\n"
    assert marker_filter.feed("[ordinary]: /url\n\n") == "[ordinary]: /url\n\n"
    assert marker_filter.flush() == ""


def test_a_full_reference_label_can_continue_on_the_next_line() -> None:
    text = "[docs][<script>\n name] ===after===\n\n[<script> name]: /url\n"
    _assert_streaming_output(text, text.replace("===after===", "after"))


def test_an_escaped_separator_cannot_make_a_full_reference_label() -> None:
    reference = r"[docs]\\[<script>]const equal = a === b;</script>"
    text = reference + " ===after===\n\n[<script>]: /url\n"
    _assert_streaming_output(text, text.replace("===after===", "after"))


def test_a_defined_reference_image_keeps_its_nested_link_out_of_the_outer_link() -> (
    None
):
    text = (
        '[outer ![image [inner](i)][<script>]](o "<style>") ===after===\n\n'
        "[<script>]: /url\n"
    )
    _assert_streaming_output(text, text.replace("===after===", "after"))


def test_a_reference_image_does_not_restore_an_already_invalid_outer_link() -> None:
    text = (
        '[outer [a](u) ![image [inner](i)][<script>]](o "===title=== '
        '<style>a === b;</style>") ===after===\n\n[<script>]: /url\n'
    )
    expected = text.replace("===title===", "title").replace("===after===", "after")
    _assert_streaming_output(text, expected)


def test_reference_definition_metadata_inside_a_container_cannot_open_raw_html() -> (
    None
):
    text = (
        "[docs][<script>] ===after===\n\n"
        '> [<script>]: url "<style> ===title==="\n\n===tail==='
    )
    expected = text.replace("===after===", "after").replace("===tail===", "tail")
    _assert_streaming_output(text, expected)


def test_reference_replay_can_use_supplementary_private_use_characters() -> None:
    prefix = "".join(chr(code) for code in range(0xE000, 0xF900)) + "\n\n"
    reference = "[docs][<script>] ===after===\n\n[<script>]: /url\n"
    marker_filter = PreserveMarkerFilter()
    out = marker_filter.feed(prefix) + marker_filter.feed(reference)
    out += marker_filter.flush()
    assert out == prefix + reference.replace("===after===", "after")


@pytest.mark.parametrize(
    "candidate",
    [
        "[docs][<script>] ===after===\n\n[<script>]: /url\n",
        "Use ` unmatched [docs][<script>const eq = a === b;</script>] ===after===",
        '[broken](url "[docs][<script>const eq = a === b;</script>] ===after===',
    ],
    ids=["future-definition", "flush-unmatched-code", "flush-invalid-link"],
)
def test_reference_replay_does_not_change_metadata_already_streamed(
    candidate: str,
) -> None:
    prefix = "[`===id===`]: url\n\n"
    text = prefix + candidate
    expected = prefix + candidate.replace("===after===", "after")
    _assert_streaming_output(text, expected)


@pytest.mark.parametrize("tag", ["script", "style"])
def test_a_definition_title_cannot_hide_a_real_raw_html_closer(tag: str) -> None:
    text = (
        f"[<{tag}>]const equal = a === b;\n\n"
        f'[id]: /url "</{tag}><style>"\n\n===after===\n'
    )
    _assert_streaming_output(text, text.replace("===after===", "after"))


@pytest.mark.parametrize("tag", ["textarea", "title"])
def test_definition_metadata_inside_text_only_html_keeps_prose_marker_cleanup(
    tag: str,
) -> None:
    text = f'[<{tag}>]===body===\n\n[id]: /url "===title==="\n\n</{tag}>\n===after===\n'
    expected = (
        text.replace("===body===", "body")
        .replace("===title===", "title")
        .replace("===after===", "after")
    )
    _assert_streaming_output(text, expected)


@pytest.mark.parametrize(
    "svg", ['<svg viewBox="0 0 1 1" />', '<SVG viewBox="0 0 1 1"/>']
)
@pytest.mark.parametrize("prefix", ["", "Intro "])
def test_a_self_closing_svg_does_not_disable_following_markdown(
    svg: str, prefix: str
) -> None:
    markdown = "Use `<script>` literally. ===after===\n"
    _assert_streaming_output(
        prefix + svg + "\n" + markdown,
        prefix + svg + "\n" + markdown.replace("===after===", "after"),
    )


@pytest.mark.parametrize("prefix", ["", "Intro "])
def test_a_nested_self_closing_svg_does_not_keep_the_outer_svg_open(
    prefix: str,
) -> None:
    svg = (
        prefix
        + '<svg>\n<svg viewBox="0 0 1 1" />\n<text>===caption===</text>\n</svg>\n'
    )
    markdown = "Use `<script>` literally. ===after===\n"
    expected = svg.replace("===caption===", "caption") + markdown.replace(
        "===after===", "after"
    )
    _assert_streaming_output(svg + markdown, expected)
    marker_filter = PreserveMarkerFilter()
    assert marker_filter.feed(svg + markdown) == expected
    assert marker_filter.flush() == ""


@pytest.mark.parametrize("prefix", ["Intro ", "===Intro=== "])
@pytest.mark.parametrize(
    "body",
    [
        "<g></g><script =>const equal = a === b;</script>\n",
        "<g></g>`<script =>const label = `value`; const equal = a === b;</script>\n"
        '\\<style =>.node::after { content: "==="; }</style>\n',
    ],
    ids=["recoverable-script-attributes", "literal-backtick-and-backslash"],
)
def test_svg_after_inline_prose_keeps_its_html_body(prefix: str, body: str) -> None:
    svg = prefix + "<svg>\n" + body + "</svg>\n"
    markdown = "Use `<script>` literally. ===after===\n"
    expected = svg.replace("===Intro===", "Intro") + markdown.replace(
        "===after===", "after"
    )
    _assert_streaming_output(svg + markdown, expected)


@pytest.mark.parametrize(
    "literal",
    [
        "Intro `<svg>` literally.\n",
        "Intro \\<svg> literally.\n",
        "Intro <!--<svg>--> literally.\n",
        "```html\nIntro <svg>\n```\n",
        "<textarea>Intro <svg></textarea>\n",
    ],
    ids=["inline-code", "escaped", "comment", "fenced-code", "text-only-html"],
)
def test_literal_svg_tags_do_not_open_an_html_visual(literal: str) -> None:
    markdown = "Explain <script => literally. ===after===\n"
    _assert_streaming_output(
        literal + markdown, literal + markdown.replace("===after===", "after")
    )


@pytest.mark.parametrize("tag", ["script", "style"])
@pytest.mark.parametrize(
    "wrapper",
    [
        "<svg>{empty}</svg>",
        "<div><svg>{empty}</svg></div>",
        "Intro <svg><g>{empty}</g></svg>",
        "<svg><svg>{empty}</svg></svg>",
        "<svg><foreignObject/>{empty}</svg>",
    ],
    ids=[
        "svg-root",
        "html-parent",
        "prose-prefix",
        "nested-svg",
        "empty-integration-point",
    ],
)
def test_self_closing_svg_script_and_style_do_not_consume_following_prose(
    tag: str, wrapper: str
) -> None:
    html = wrapper.format(empty=f"<{tag} />")
    _assert_streaming_output(html + "\n===after===", html + "\nafter")


@pytest.mark.parametrize("tag", ["script", "style"])
@pytest.mark.parametrize("parent", ["foreignObject", "desc", "title"])
def test_svg_html_integration_points_keep_html_raw_text_semantics(
    tag: str, parent: str
) -> None:
    html = f"<svg><{parent}><{tag}/>const equal = a === b;</{tag}></{parent}></svg>"
    _assert_streaming_output(html + "\n===after===", html + "\nafter")


def test_nested_svg_restores_the_surrounding_html_integration_point() -> None:
    html = (
        "<svg><foreignObject><svg><script /></svg>"
        "<script/>const equal = a === b;</script>"
        "</foreignObject><style /></svg>"
    )
    _assert_streaming_output(html + "\n===after===", html + "\nafter")


@pytest.mark.parametrize("tag", ["script", "style"])
@pytest.mark.parametrize(
    "wrapper",
    [
        "<math>{empty}</math>",
        "<div><math>{empty}</math></div>",
        "<math><mrow>{empty}</mrow></math>",
        "<svg><foreignObject><math>{empty}</math></foreignObject></svg>",
    ],
)
def test_self_closing_mathml_script_and_style_do_not_consume_prose(
    tag: str, wrapper: str
) -> None:
    html = wrapper.format(empty=f"<{tag} />")
    _assert_streaming_output(html + "\n===after===", html + "\nafter")


@pytest.mark.parametrize("parent", ["mi", "mo", "mn", "ms", "mtext"])
@pytest.mark.parametrize("tag", ["script", "style"])
def test_mathml_text_integration_points_keep_html_raw_text_semantics(
    parent: str, tag: str
) -> None:
    html = f"<math><{parent}><{tag}/>const equal = a === b;</{tag}></{parent}></math>"
    _assert_streaming_output(html + "\n===after===", html + "\nafter")


@pytest.mark.parametrize("exception", ["mglyph", "malignmark"])
def test_mathml_text_integration_exceptions_keep_their_foreign_children(
    exception: str,
) -> None:
    html = (
        f"<math><mtext><{exception}><script /></{exception}>"
        "===visible===<script/>const equal = a === b;</script></mtext></math>"
    )
    _assert_streaming_output(
        html + "\n===after===", html.replace("===visible===", "visible") + "\nafter"
    )


@pytest.mark.parametrize(
    ("attributes", "html_children"),
    [
        ('encoding="text/html"', True),
        ("encoding='APPLICATION/XHTML+XML'", True),
        ('encoding="text&#x2f;html"', True),
        ("", False),
        ('encoding="text/plain"', False),
        ("title='encoding=\"text/html\"'", False),
        ("encoding='text/plain' encoding='text/html'", False),
        ("encoding=' text/html '", False),
    ],
)
def test_mathml_annotation_encoding_controls_its_html_integration(
    attributes: str, html_children: bool
) -> None:
    script = (
        "<script/>const equal = a === b;</script>" if html_children else "<script />"
    )
    html = f"<math><annotation-xml {attributes}>{script}</annotation-xml></math>"
    _assert_streaming_output(html + "\n===after===", html + "\nafter")


@pytest.mark.parametrize(
    "html",
    [
        "<svg><math><mi><script /></mi></math></svg>",
        "<math><svg><foreignObject><script /></foreignObject></svg></math>",
        "<math><annotation-xml encoding='text/plain'><svg><foreignObject>"
        "<script/>const equal = a === b;</script>"
        "</foreignObject></svg></annotation-xml></math>",
        "<svg><foreignObject><math><mi><script/>const equal = a === b;</script>"
        "</mi></math></foreignObject></svg>",
        "<math><mtext><div><mglyph><script/>const equal = a === b;</script>"
        "</mglyph></div></mtext></math>",
    ],
)
def test_nested_foreign_elements_keep_their_inherited_namespace(html: str) -> None:
    _assert_streaming_output(html + "\n===after===", html + "\nafter")


@pytest.mark.parametrize("literal", ["`<math>`", "\\<math>", "<!--<math>-->"])
def test_literal_mathml_does_not_change_later_html_raw_text(literal: str) -> None:
    html = "<script/>const equal = a === b;</script>"
    _assert_streaming_output(
        literal + "\n" + html + "\n===after===", literal + "\n" + html + "\nafter"
    )


@pytest.mark.parametrize(
    "literal",
    [
        "`<svg>`",
        "\\<svg>",
        "<!--<svg>-->",
        "<textarea><svg></textarea>",
        "```html\n<svg>\n```",
    ],
    ids=["inline-code", "escaped", "comment", "text-only-html", "fenced-code"],
)
def test_literal_svg_does_not_make_later_html_scripts_self_closing(
    literal: str,
) -> None:
    html = "<script/>const equal = a === b;</script>"
    _assert_streaming_output(
        literal + "\n" + html + "\n===after===", literal + "\n" + html + "\nafter"
    )


def test_self_closing_syntax_still_opens_a_nonvoid_html_container() -> None:
    html = (
        "<div/>`<script>const label = `value`; const equal = a === b;</script></div>\n"
    )
    markdown = "Use `<script>` literally. ===after===\n"
    _assert_streaming_output(
        html + markdown, html + markdown.replace("===after===", "after")
    )


@pytest.mark.parametrize("indent", ["    ", "\t", "  \t"])
def test_indented_code_does_not_open_html_or_markdown_fences(indent: str) -> None:
    code = (
        f"{indent}<script> literal\n"
        f"{indent}const equal = a === b;\n\n"
        f"{indent}```\n{indent}!===\n"
    )
    _assert_streaming_output(code + "\n===after===\n", code + "\nafter\n")


def test_indented_code_is_preserved_when_the_stream_ends_without_a_newline() -> None:
    code = "    <script> literal ===source==="
    _assert_streaming_output(code, code)


def test_an_indented_line_continuing_a_paragraph_can_contain_real_html() -> None:
    text = "Paragraph\n    <script>literal\n===source===\n"
    _assert_streaming_output(text, text)


def test_indented_scripts_inside_an_html_visual_remain_real_scripts() -> None:
    html = (
        "<div>\n    `<script>const label = `value`; const equal = a === b;</script>\n"
        "</div>\n"
    )
    _assert_streaming_output(html + "===after===\n", html + "after\n")


@pytest.mark.parametrize(
    "previous",
    [
        "Paragraph\n\n",
        "```js\nconst equal = a === b;\n```\n",
        "<div>visual</div>\n",
        "<script>const equal = a === b;</script>\n",
        "# Heading\n",
        "<div>\nvisual\n</div>\n",
        "===<div>visual</div>===\n",
        "===<script>const equal = a === b;</script>===\n",
        "===# Heading===\n",
    ],
    ids=[
        "paragraph-break",
        "fenced-code",
        "html-visual",
        "raw-script",
        "heading",
        "multiline-visual",
        "marked-visual",
        "marked-script",
        "marked-heading",
    ],
)
def test_indented_code_can_start_after_a_completed_block(previous: str) -> None:
    code = "    <script>literal\n    const equal = a === b;\n"
    expected = (
        previous.replace("===<", "<")
        .replace(">===", ">")
        .replace("===# Heading===", "# Heading")
    )
    _assert_streaming_output(
        previous + code + "===after===\n", expected + code + "after\n"
    )


@pytest.mark.parametrize(
    "code",
    [
        ">     <script> literal\n>     const equal = a === b;\n",
        "> ~~~\n> <script> literal\n> a === b;\n> !===\n> ~~~\n",
        "- ~~~\n  <style> literal\n  a === b;\n  ~~~\n",
        "1. ```js\n   <script> literal\n   a === b;\n   ```\n",
        "> -     <script> literal\n>       a === b;\n",
        "- >     <script> literal\n  >     a === b;\n",
        "-     <script> literal\n      a === b;\n",
        "-\n      <script> literal\n      a === b;\n",
        "- item\n\n      <script> literal\n      a === b;\n",
        ">\t  <script> literal\n>\t  a === b;\n",
    ],
)
def test_code_inside_markdown_containers_preserves_its_source(code: str) -> None:
    _assert_streaming_output(code + "\n===after===\n", code + "\nafter\n")


@pytest.mark.parametrize(
    "code",
    [
        ">     const equal = a === b;",
        "-     const equal = a === b;",
        "-\n      const equal = a === b;",
    ],
)
def test_container_code_without_a_final_newline_is_preserved(code: str) -> None:
    _assert_streaming_output(code, code)


@pytest.mark.parametrize(
    "paragraph",
    [
        "> prose\n>     <script>const equal = a === b;</script>\n",
        "> \t<script>const equal = a === b;</script>\n",
        "Paragraph\n    <script>const equal = a === b;</script>\n",
    ],
)
def test_container_candidates_keep_real_html_in_a_paragraph(paragraph: str) -> None:
    _assert_streaming_output(paragraph + "===after===\n", paragraph + "after\n")


def test_a_container_code_block_ends_an_unmatched_inline_candidate() -> None:
    text = "Press the ` key.\n> ~~~\n> a === b;\n> ~~~\n===Important=== Use `x`.\n"
    _assert_streaming_output(text, text.replace("===Important===", "Important"))


def test_a_container_code_block_ends_unmatched_link_metadata() -> None:
    text = '[broken](url "pending\n> ~~~\n> a === b;\n> ~~~\n===Important=== Use `x`.\n'
    _assert_streaming_output(text, text.replace("===Important===", "Important"))


def test_indentation_in_the_same_quote_can_continue_a_code_span() -> None:
    text = "> Paragraph `code\n>     a === b`\n===after===\n"
    _assert_streaming_output(text, text.replace("===after===", "after"))


def test_container_candidates_inside_an_html_visual_remain_real_html() -> None:
    html = "<div>\n> ~~~\n> <script>a === b;</script>\n> ~~~\n</div>\n"
    _assert_streaming_output(html + "===after===\n", html + "after\n")


def test_ordinary_container_prose_is_emitted_at_the_end_of_its_line() -> None:
    marker_filter = PreserveMarkerFilter()
    assert marker_filter.feed("> ===quote===\n- ===list===\n") == "> quote\n- list\n"
    assert marker_filter.flush() == ""


@pytest.mark.parametrize(
    ("definition", "expected_definition"),
    [
        ("> [docs]: <script>\n", "> [docs]: <script>\n"),
        ("- [docs]: <script>\n", "- [docs]: <script>\n"),
        (
            '> [docs]: /===url=== "===title=== <style>"\n',
            '> [docs]: /===url=== "===title=== <style>"\n',
        ),
        (
            '> [===docs===]: /===url=== "===title=== <style>"\n',
            '> [docs]: /===url=== "===title=== <style>"\n',
        ),
        (
            '> [docs]: /===url===\n> "===title=== <style>"\n',
            '> [docs]: /===url===\n> "===title=== <style>"\n',
        ),
    ],
    ids=["blockquote", "list", "metadata-markers", "marked-label", "next-line-title"],
)
def test_container_reference_definitions_preserve_metadata_and_clean_following_prose(
    definition: str, expected_definition: str
) -> None:
    _assert_streaming_output(
        definition + "\n===after===\n", expected_definition + "\nafter\n"
    )


@pytest.mark.parametrize(
    "prefix",
    [
        'Prose [docs]: /===url=== "',
        '> [docs]: /===url=== "unfinished ',
        '> ![docs]: /===url=== "',
    ],
    ids=["midline", "invalid-title", "image"],
)
def test_invalid_container_definition_candidates_preserve_real_script_code(
    prefix: str,
) -> None:
    script = "<script>const equal = a === b;</script>"
    text = prefix + script + " ===after===\n"
    expected = prefix.replace("===url===", "url") + script + " after\n"
    _assert_streaming_output(text, expected)


@pytest.mark.parametrize(
    "html",
    [
        '<div>\n[docs]: /url "<script>const equal = a === b;</script>"\n</div>\n',
        '<script>\n[docs]: /url "const equal = a === b;"\n</script>\n',
    ],
    ids=["html-visual", "raw-body"],
)
def test_definition_looking_source_in_real_html_keeps_html_semantics(html: str) -> None:
    _assert_streaming_output(html + "===after===\n", html + "after\n")


def test_a_container_definition_holds_metadata_before_it_can_be_streamed() -> None:
    marker_filter = PreserveMarkerFilter()
    first = marker_filter.feed("===before===\n\n")
    assert first == "before\n\n"
    assert marker_filter.feed("> [===docs===]") == ""
    first += marker_filter.feed(': /===url=== "===title=== <style>"\n\n===after===')
    assert first == "before\n\n> [docs"
    assert first + marker_filter.flush() == (
        'before\n\n> [docs]: /===url=== "===title=== <style>"\n\nafter'
    )
    assert marker_filter.flush() == ""


@pytest.mark.parametrize("tag", ["script", "style", "textarea"])
@pytest.mark.parametrize(
    ("placement", "block"),
    [
        ("inline", False),
        ("inline-multiline", False),
        ("paragraph-indent", False),
        ("leading", True),
        ("leading-multiline", True),
        ("marked-leading", True),
    ],
)
def test_only_leading_raw_html_blocks_allow_following_indented_code(
    tag: str, placement: str, block: bool
) -> None:
    html = f"<{tag}>content</{tag}>\n"
    if placement == "inline":
        html = "Text " + html
    elif placement == "inline-multiline":
        html = f"Text <{tag}>\ncontent\n</{tag}>\n"
    elif placement == "paragraph-indent":
        html = "Paragraph\n    " + html
    elif placement == "leading-multiline":
        html = f"<{tag}>\ncontent\n</{tag}>\n"
    elif placement == "marked-leading":
        html = f"===<{tag}>content</{tag}>===\n"
    source = html + "    ===lesson===\n===after===\n"
    expected_html = html.replace("===<", "<").replace(">===", ">")
    lesson = "    ===lesson===\n" if block else "    lesson\n"
    _assert_streaming_output(source, expected_html + lesson + "after\n")


@pytest.mark.parametrize("tag", ["script", "style", "textarea"])
def test_inline_raw_html_after_code_does_not_keep_the_previous_code_context(
    tag: str,
) -> None:
    code = "<div>visual</div>\n    const equal = a === b;\n"
    inline = f"Text <{tag}>content</{tag}>\n"
    text = code + inline + "    ===lesson===\n===after===\n"
    _assert_streaming_output(text, code + inline + "    lesson\nafter\n")


@pytest.mark.parametrize(
    "html", ["<title>content</title>\n", "<title>\ncontent\n</title>\n"]
)
def test_title_markup_keeps_following_indented_html_text_as_prose(html: str) -> None:
    text = html + "    ===lesson===\n===after===\n"
    _assert_streaming_output(text, html + "    lesson\nafter\n")


@pytest.mark.parametrize("prefix", ["> ", "- ", "12. ", "> - ", "- > ", ">\t"])
@pytest.mark.parametrize("tag", ["script", "style"])
def test_raw_html_blocks_in_containers_preserve_recoverable_attributes(
    prefix: str, tag: str
) -> None:
    text = f"{prefix}<{tag} =>const equal = a === b;</{tag}>\n\n===after===\n"
    _assert_streaming_output(text, text.replace("===after===", "after"))


@pytest.mark.parametrize("prefix", ["> ", "- "])
def test_container_textarea_blocks_ignore_nested_fake_script_tags(prefix: str) -> None:
    text = f"{prefix}<textarea =><script>fake ===body===</textarea>\n\n===after===\n"
    expected = text.replace("===body===", "body").replace("===after===", "after")
    _assert_streaming_output(text, expected)


@pytest.mark.parametrize(
    "prefix",
    ["Paragraph\n12. ", "> Explain ", "- Explain ", "> Paragraph\n>     "],
)
def test_container_prefixes_do_not_make_invalid_inline_tags_into_blocks(
    prefix: str,
) -> None:
    text = f"{prefix}<script =>const equal = a === b;</script>\n===after===\n"
    expected = text.replace("a === b", "a  b").replace("===after===", "after")
    _assert_streaming_output(text, expected)


@pytest.mark.parametrize("prefix", ["Use ` unmatched\n", '[broken](url "pending\n'])
def test_container_raw_html_blocks_end_unmatched_inline_candidates(prefix: str) -> None:
    text = (
        prefix + "> <script =>const equal = a === b;</script>\n===after=== Use `x`.\n"
    )
    _assert_streaming_output(text, text.replace("===after===", "after"))


def test_container_raw_block_attributes_can_continue_on_the_next_line() -> None:
    text = "> <script\n> =>const equal = a === b;</script>\n===after===\n"
    _assert_streaming_output(text, text.replace("===after===", "after"))


@pytest.mark.parametrize(
    "block",
    [
        "# ===Important=== `x`\n",
        "- ===Important=== `x`\n",
        "1. ===Important=== `x`\n",
        "> ===Important=== `x`\n",
        "***\n===Important=== `x`\n",
        "---\n===Important=== `x`\n",
        "===\n===Important=== `x`\n",
    ],
    ids=[
        "atx",
        "bullet",
        "ordered",
        "quote",
        "thematic",
        "setext-dash",
        "setext-equal",
    ],
)
def test_markdown_blocks_end_an_unmatched_code_span(block: str) -> None:
    text = "Press the ` key.\n" + block
    expected = text.replace("===Important===", "Important").replace("\n===\n", "\n\n")
    _assert_streaming_output(text, expected)


@pytest.mark.parametrize(
    "continuation",
    [
        "#not-heading ===literal=== `x`\n",
        "####### heading ===literal=== `x`\n",
        "    # heading ===literal=== `x`\n",
        "2. item ===literal=== `x`\n",
        "+ \n===literal=== `x`\n",
    ],
)
def test_potential_block_starts_can_continue_the_same_code_span(
    continuation: str,
) -> None:
    text = "Use `code\n" + continuation
    _assert_streaming_output(text, text)


@pytest.mark.parametrize(
    "text",
    [
        "> Use `code\n> ordinary ===literal=== `x`\n",
        "> Use `code\nlazy ===literal=== `x`\n",
        "Use `code\nordinary ===literal=== `x`\n---\n",
    ],
)
def test_inline_spans_within_a_single_parser_block_remain_paired(text: str) -> None:
    _assert_streaming_output(text, text)


@pytest.mark.parametrize(
    ("body", "expected_body"),
    [
        ("`a === b` ===after===\n", "`a === b` after\n"),
        (
            '[===label===](url "<style>") ===after===\n',
            '[label](url "<style>") after\n',
        ),
        (
            "<script>a === b;</script> ===after===\n",
            "<script>a === b;</script> after\n",
        ),
        (
            "<textarea>===body===</textarea> ===after===\n",
            "<textarea>body</textarea> after\n",
        ),
        (r"\<script> ===after===" + "\n", r"\<script> after" + "\n"),
    ],
    ids=["code", "link", "script", "textarea", "escape"],
)
def test_a_new_paragraph_keeps_its_original_inline_opener(
    body: str, expected_body: str
) -> None:
    prefix = "Press the ` key.\n***\n"
    _assert_streaming_output(prefix + body, prefix + expected_body)


def test_a_heading_ends_unmatched_link_metadata() -> None:
    text = '[broken](url "pending\n# ===Important=== `x`\n'
    _assert_streaming_output(text, text.replace("===Important===", "Important"))


def test_a_list_child_heading_can_have_more_than_three_source_indent_columns() -> None:
    text = "- text ` key\n    # ===Heading=== `x`\n"
    _assert_streaming_output(text, text.replace("===Heading===", "Heading"))


def test_real_raw_html_keeps_priority_over_parser_inline_boundaries() -> None:
    html = "[<script>]const eq = a === b;\n***\n===literal===\n</script>\n"
    _assert_streaming_output(html + "===after===\n", html + "after\n")


def test_a_matched_inline_span_without_block_candidates_streams_immediately() -> None:
    marker_filter = PreserveMarkerFilter()
    assert marker_filter.feed("Use `a === b` ===after===\n") == "Use `a === b` after\n"
    assert marker_filter.flush() == ""


@pytest.mark.parametrize("tag", ["script", "style", "textarea"])
def test_a_valid_image_description_keeps_html_inert_and_cleans_alt_text(
    tag: str,
) -> None:
    text = f"![===caption=== <{tag}>===body===</{tag}>](/img) ===after===\n"
    expected = text.replace("===caption===", "caption").replace("===body===", "body")
    _assert_streaming_output(text, expected.replace("===after===", "after"))


@pytest.mark.parametrize(
    "text",
    [
        "![<script>][pic] ===after===\n\n[pic]: /img\n",
        "[pic]: /img\n\n![<script>][pic] ===after===\n",
        "![<script>][] ===after===\n\n[<script>]: /img\n",
        "![<script>] ===after===\n\n[<script>]: /img\n",
        "![outer ![inner <script>](/inner) <style>](/outer) ===after===\n",
        '[outer ![<script>](/img)](url "<style>") ===after===\n',
        "![outer [inner <script>](url)](/img) ===after===\n",
        r"![caption \] <script>](/img) ===after===" + "\n",
        "> ![caption\n> more <script>](/img) ===after===\n",
        "- ![caption\n  more <script>](/img) ===after===\n",
        "# ![caption <script>](/img) ===after===\n",
    ],
)
def test_parser_confirmed_image_descriptions_do_not_open_raw_html(text: str) -> None:
    _assert_streaming_output(text, text.replace("===after===", "after"))


@pytest.mark.parametrize(
    "image",
    [
        "![<script>const eq = a === b;</script>]",
        "![<script>const eq = a === b;</script>][missing]",
        '![<script>const eq = a === b;</script>](url "unfinished)',
        r"\![<script>const eq = a === b;</script>](/img)",
        r"!\[<script>const eq = a === b;</script>](/img)",
    ],
)
def test_invalid_or_escaped_images_keep_visible_html_semantics(image: str) -> None:
    _assert_streaming_output(image + " ===after===\n", image + " after\n")


@pytest.mark.parametrize(
    "image",
    [
        "`![<script> a === b;](/img)`",
        "![`<script> ] a === b;`](/img)",
    ],
)
def test_image_lookalikes_in_code_keep_code_literals(image: str) -> None:
    _assert_streaming_output(image + " ===after===\n", image + " after\n")


@pytest.mark.parametrize("valid", [False, True])
def test_image_descriptions_are_not_limited_to_reference_label_length(
    valid: bool,
) -> None:
    image = "![" + "long caption " * 85 + "<script>const eq = a === b;</script>]"
    if valid:
        image += "(/img)"
    expected = image.replace("a === b", "a  b") if valid else image
    _assert_streaming_output(image + " ===after===\n", expected + " after\n")


@pytest.mark.parametrize(
    "tag",
    ['<script title="`">', '<script data-note="===hidden===">'],
)
def test_image_html_attributes_remain_opaque_while_alt_text_is_cleaned(
    tag: str,
) -> None:
    image = f"![{tag}===visible===</script>](/img)"
    text = image + " ===after=== Use `x`\n"
    expected = image.replace("===visible===", "visible") + " after Use `x`\n"
    _assert_streaming_output(text, expected)


@pytest.mark.parametrize("alt", ["<svg>", "<svg><script/>"])
def test_image_alt_cannot_open_an_svg_visual(alt: str) -> None:
    text = f"![{alt}](/img) ===after===\nUse `<script>` literally. ===last===\n"
    expected = text.replace("===after===", "after").replace("===last===", "last")
    _assert_streaming_output(text, expected)


def test_actual_html_visual_has_priority_over_parser_image_metadata() -> None:
    prefix = "![<script>](/img) ===before===\n\n"
    visual = "<div>\n\n![<script>const equal = a === b;</script>](/img)\n</div>\n"
    text = prefix + visual + "===after===\n"
    _assert_streaming_output(
        text, prefix.replace("===before===", "before") + visual + "after\n"
    )
