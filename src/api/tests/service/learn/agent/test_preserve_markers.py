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
    "svg", ['<svg viewBox="0 0 1 1" />', '<SVG viewBox="0 0 1 1"/>']
)
def test_a_self_closing_svg_does_not_disable_following_markdown(svg: str) -> None:
    markdown = "Use `<script>` literally. ===after===\n"
    _assert_streaming_output(
        svg + "\n" + markdown,
        svg + "\n" + markdown.replace("===after===", "after"),
    )


def test_a_nested_self_closing_svg_does_not_keep_the_outer_svg_open() -> None:
    svg = '<svg>\n<svg viewBox="0 0 1 1" />\n<text>===caption===</text>\n</svg>\n'
    markdown = "Use `<script>` literally. ===after===\n"
    expected = svg.replace("===caption===", "caption") + markdown.replace(
        "===after===", "after"
    )
    _assert_streaming_output(svg + markdown, expected)
    marker_filter = PreserveMarkerFilter()
    assert marker_filter.feed(svg + markdown) == expected
    assert marker_filter.flush() == ""


def test_self_closing_syntax_still_opens_a_nonvoid_html_container() -> None:
    html = (
        "<div/>`<script>const label = `value`; const equal = a === b;</script></div>\n"
    )
    markdown = "Use `<script>` literally. ===after===\n"
    _assert_streaming_output(
        html + markdown, html + markdown.replace("===after===", "after")
    )
