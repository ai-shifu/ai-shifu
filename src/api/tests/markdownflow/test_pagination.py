"""Require 2.0 content to use the same typed stream parts as MarkdownFlow 1.0."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import pytest
from markdownflow import StreamFormatter
from markdownflow.pagination import LessonPager

if TYPE_CHECKING:
    from collections.abc import Iterable

LESSON = (
    "First page of prose.\n\n"
    "---\n\n"
    '<div class="card">\n  <p>A cover card</p>\n</div>\n\n'
    "Second page of prose, after the card.\n\n"
    "---\n\n"
    "Third page."
)


def _format(chunks: Iterable[str]) -> list[tuple[str, str, int]]:
    """Collect the exact parts produced by the 1.0 package's formatter."""
    formatter = StreamFormatter()
    pieces: list[tuple[str, str, int]] = []
    for chunk in chunks:
        pieces.extend(
            (element.content, str(element.type), element.number)
            for element in formatter.process(chunk)
        )
    pieces.extend(
        (element.content, str(element.type), element.number)
        for element in formatter.flush()
    )
    return pieces


def _page(chunks: Iterable[str]) -> list[tuple[str, str, int]]:
    pager = LessonPager()
    pieces: list[tuple[str, str, int]] = []
    for chunk in chunks:
        pieces.extend(pager.add(chunk))
    pieces.extend(pager.flush())
    return pieces


def _random_chunks(text: str, seed: int) -> list[str]:
    rng = random.Random(seed)  # noqa: S311 -- chunk sizes, not secrets
    chunks: list[str] = []
    index = 0
    while index < len(text):
        step = rng.randint(1, 9)
        chunks.append(text[index : index + step])
        index += step
    return chunks


def _shape(pieces: list[tuple[str, str, int]]) -> tuple[tuple[str, int, str], ...]:
    """Ignore where blank lines ride while preserving typed element identity."""
    grouped: dict[tuple[str, int], list[str]] = {}
    for content, stream_type, number in pieces:
        grouped.setdefault((stream_type, number), []).append(content)
    return tuple(
        (
            stream_type,
            number,
            "\n".join(line for line in "".join(parts).splitlines() if line.strip()),
        )
        for (stream_type, number), parts in grouped.items()
    )


def test_stream_parts_match_the_legacy_formatter_for_random_chunks() -> None:
    for seed in range(20):
        chunks = _random_chunks(LESSON, seed)
        assert _page(chunks) == _format(chunks), f"seed {seed}"


def test_a_card_keeps_its_legacy_type_and_number() -> None:
    pieces = _page([LESSON])
    assert pieces == _format([LESSON])
    assert {stream_type for _, stream_type, _ in pieces} >= {"html", "text"}


@pytest.mark.parametrize("rule", ["---", "***", "___"])
def test_separator_lines_are_preserved_as_the_legacy_formatter_classifies_them(
    rule: str,
) -> None:
    content = f"Before.\n{rule}\nAfter.\n"
    pieces = _page([content])
    assert pieces == _format([content])
    assert "".join(text for text, _, _ in pieces) == content
    assert {number for _, _, number in pieces} == {0}


@pytest.mark.parametrize("rule", ["---", "***", "___"])
@pytest.mark.parametrize(
    ("opening", "closing", "stream_type"),
    [
        ("```text", "```", "code"),
        ("<div>", "</div>", "html"),
        ("<svg>", "</svg>", "svg"),
    ],
)
def test_literal_rules_do_not_split_or_change_visual_content(
    opening: str, closing: str, stream_type: str, rule: str
) -> None:
    content = f"Intro.\n{opening}\n{rule}\n{closing}\n"
    chunks = list(content)
    pieces = _page(chunks)
    assert pieces == _format(chunks)
    visual_pieces = [part for part in pieces if part[1] == stream_type]
    assert "".join(text for text, _, _ in visual_pieces) == (
        f"{opening}\n{rule}\n{closing}\n"
    )
    assert {number for _, _, number in visual_pieces} == {1}


@pytest.mark.parametrize("tag", ["style", "script"])
def test_html_append_keeps_the_legacy_number_across_a_separator(tag: str) -> None:
    """Script/style must retain the preceding HTML identity, even when numbers go back."""
    content = f"<div>Card</div>\n---\nText.\n<{tag}>body</{tag}>\n"
    for chunks in ([content], content.splitlines(keepends=True), list(content)):
        pieces = _page(chunks)
        assert pieces == _format(chunks)
        html_numbers = [number for _, kind, number in pieces if kind == "html"]
        assert html_numbers == [0, 0]
        assert [number for _, _, number in pieces] == [0, 1, 1, 0]


def test_the_last_line_is_released_when_the_turn_ends() -> None:
    pager = LessonPager()
    assert pager.add("No newline yet") == []
    assert pager.flush() == [("No newline yet", "text", 0)]


@pytest.mark.parametrize("opening", ["<div>", "<svg>", "```python"])
def test_a_question_block_does_not_inherit_unfinished_visual_syntax(
    opening: str,
) -> None:
    pager = LessonPager()
    narration = pager.add(opening + "\nUnfinished") + pager.start_block()
    assert "".join(text for text, _, _ in narration) == opening + "\nUnfinished"
    question = pager.add("Which example?") + pager.flush()
    assert question == [("Which example?", "text", 1)]


def test_block_numbering_advances_past_every_prior_element_and_html_append() -> None:
    pager = LessonPager()
    pieces = pager.add("<div>Card</div>\nNarration.\n<style>.card{}</style>\n")
    assert [number for _, _, number in pieces] == [0, 1, 0]
    assert pager.start_block() == []
    assert pager.add("Question.\n") == [("Question.\n", "text", 2)]
    assert pager.start_block() == []
    # Consecutive prose keeps the existing history/audio grouping.
    assert pager.add("Another question.\n") == [("Another question.\n", "text", 2)]


def test_the_pieces_are_the_same_at_every_character_boundary() -> None:
    """A model's arbitrary chunk boundaries cannot change element content or identity."""
    lesson = (
        "First page.\n\n---\n\n"
        '<div class="card">A cover</div>\n\n'
        "```js\nif (a === b) {}\n---\n```\n\n"
        "![图](http://example.com/y.png)\n\nLast page.\n"
        "<svg>\n---\n</svg>\n"
        "<style>.card { color: red; }</style>\n"
        "<script>window.card = true;</script>"
    )
    whole = _shape(_format([lesson]))
    for cut in range(len(lesson) + 1):
        chunks = [lesson[:cut], lesson[cut:]]
        pieces = _page(chunks)
        assert pieces == _format(chunks), f"cut at {cut} changed the protocol"
        assert _shape(pieces) == whole, f"cut at {cut} changed the elements"
    assert {stream_type for stream_type, _, _ in whole} >= {
        "html",
        "code",
        "img",
        "svg",
    }
