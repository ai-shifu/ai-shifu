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
