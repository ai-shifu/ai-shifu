"""Cover the removal of verbatim markers from the engine's streamed text."""

from __future__ import annotations

import random

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
