"""Cover how a 2.0 turn is cut into the pieces a 1.0 lesson is delivered in.

The formatter itself is the MarkdownFlow package's and is not re-tested here. What is asserted is
the part this module adds: separator lines are dropped and start a new page, and nothing else is
lost or reordered however the text happens to be chunked.
"""

from __future__ import annotations

import random

from flaskr.service.learn.agent.pagination import LessonPager

LESSON = (
    "First page of prose.\n\n"
    "---\n\n"
    '<div class="card">\n  <p>A cover card</p>\n</div>\n\n'
    "Second page of prose, after the card.\n\n"
    "---\n\n"
    "Third page."
)


def _feed(text: str, seed: int) -> list[tuple[str, str, int]]:
    """Push the text through in random-sized chunks, the way a model streams it."""
    rng = random.Random(seed)  # noqa: S311 -- chunk sizes, not secrets
    pager = LessonPager()
    pieces: list[tuple[str, str, int]] = []
    index = 0
    while index < len(text):
        step = rng.randint(1, 9)
        pieces.extend(pager.add(text[index : index + step]))
        index += step
    pieces.extend(pager.flush())
    return pieces


def test_a_card_is_its_own_piece_with_its_own_type() -> None:
    """A text piece is spoken and not shown; a card is shown and not spoken.

    Tagged as text, the cover card inside a lesson is never rendered as a slide, which is what a
    listener saw: the title, and nothing else, while the narration played.
    """
    types = {stream_type for _, stream_type, _ in _feed(LESSON, seed=1)}
    assert "html" in types
    assert "text" in types


def test_separator_lines_are_neither_shown_nor_spoken() -> None:
    """The engine reproduces the script's `---`; a 1.0 lesson never shows one."""
    for seed in range(20):
        for content, _, _ in _feed(LESSON, seed=seed):
            assert content.strip() != "---", f"separator leaked with seed {seed}"


def test_a_separator_starts_a_new_page() -> None:
    """Prose on either side of `---` is the same type, so only the separator can divide it.

    Without that the whole lesson before the first card is one page, and a listener hears it
    against one unchanging slide. Asserted over random chunkings because a separator and the
    prose after it can arrive in the same chunk, where the formatter has already numbered them.
    """
    for seed in range(20):
        numbers_of_prose = [
            number
            for content, stream_type, number in _feed(LESSON, seed=seed)
            if stream_type == "text" and "page" in content
        ]
        assert len(set(numbers_of_prose)) == 3, (
            f"three pages of prose landed on {sorted(set(numbers_of_prose))} with seed {seed}"
        )


def test_nothing_but_separators_is_lost_and_nothing_is_reordered() -> None:
    """A learner watching the lesson write itself must see exactly what was written."""
    expected = LESSON.replace("---\n\n", "")
    for seed in range(20):
        joined = "".join(content for content, _, _ in _feed(LESSON, seed=seed))
        assert joined.replace("\n", "") == expected.replace("\n", ""), f"seed {seed}"


def test_piece_numbers_never_go_backwards() -> None:
    """The element adapter keys elements by number; a repeat would merge distant pieces."""
    for seed in range(20):
        numbers = [number for _, _, number in _feed(LESSON, seed=seed)]
        assert numbers == sorted(numbers), f"seed {seed}: {numbers}"


def test_the_last_line_is_released_when_the_turn_ends() -> None:
    """The formatter holds a line until it sees its end; a turn's end is that end."""
    pager = LessonPager()
    assert pager.add("No newline yet") == []
    assert [content for content, _, _ in pager.flush()] == ["No newline yet"]


def test_the_current_number_follows_the_last_piece() -> None:
    """Text that bypasses the formatter is put on the page the lesson is on."""
    pager = LessonPager()
    pager.add("Prose.\n\n---\n\nMore prose.\n")
    assert pager.number == 1
