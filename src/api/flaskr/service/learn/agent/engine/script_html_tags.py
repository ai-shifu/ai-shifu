"""Recognize inline HTML tags without backtracking over authored input."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

_LINEBREAKS = re.compile(r"\r\n|\r|\n")

# CommonMark's open/close-tag grammar from markdown_it.common.html_re, expressed
# as a fixed state machine. Optional whitespace and assignments must not retry
# earlier attribute partitions on malformed author input.
_HTML_TRANSITIONS = {
    "tag_start": (("letter", "tag_name"), ("/", "closing_tag_start")),
    "tag_name": (
        ("name", "tag_name"),
        ("space", "attribute_start"),
        ("/", "self_closing"),
        (">", "accepted"),
    ),
    "closing_tag_start": (("letter", "closing_tag_name"),),
    "closing_tag_name": (
        ("name", "closing_tag_name"),
        ("space", "closing_tag_space"),
        (">", "accepted"),
    ),
    "closing_tag_space": (("space", "closing_tag_space"), (">", "accepted")),
    "attribute_start": (
        ("space", "attribute_start"),
        ("attribute_first", "attribute_name"),
        ("/", "self_closing"),
        (">", "accepted"),
    ),
    "attribute_name": (
        ("attribute", "attribute_name"),
        ("space", "attribute_after_name"),
        ("=", "value_start"),
        ("/", "self_closing"),
        (">", "accepted"),
    ),
    "attribute_after_name": (
        ("space", "attribute_after_name"),
        ("attribute_first", "attribute_name"),
        ("=", "value_start"),
        ("/", "self_closing"),
        (">", "accepted"),
    ),
    "value_start": (
        ("space", "value_start"),
        ("unquoted", "unquoted_value"),
        ("'", "single_quoted_value"),
        ('"', "double_quoted_value"),
    ),
    "unquoted_value": (
        ("unquoted", "unquoted_value"),
        ("space", "attribute_start"),
        ("/", "self_closing"),
        (">", "accepted"),
    ),
    "single_quoted_value": (
        ("not_single_quote", "single_quoted_value"),
        ("'", "attribute_after_value"),
    ),
    "double_quoted_value": (
        ("not_double_quote", "double_quoted_value"),
        ('"', "attribute_after_value"),
    ),
    "attribute_after_value": (
        ("space", "attribute_start"),
        ("/", "self_closing"),
        (">", "accepted"),
    ),
    "self_closing": ((">", "accepted"),),
}


def _html_character_classes(char: str) -> set[str]:
    """Classify one character using the inline HTML grammar's exact rules."""
    classes = {char}
    letter = "A" <= char <= "Z" or "a" <= char <= "z"
    digit = "0" <= char <= "9"
    if letter:
        classes.add("letter")
    if letter or digit or char == "-":
        classes.add("name")
    if letter or char in "_:":
        classes.add("attribute_first")
    if letter or digit or char in ":._-":
        classes.add("attribute")
    if char.isspace():
        classes.add("space")
    if ord(char) > 32 and char not in "\"'=<>`":
        classes.add("unquoted")
    if char != "'":
        classes.add("not_single_quote")
    if char != '"':
        classes.add("not_double_quote")
    return classes


def html_tag_end(text: str, start: int, end: int | None = None) -> int | None:
    """Recognize a tag after ``<`` with bounded work per consumed character.

    Unicode whitespace can also occur inside an unquoted value. Keeping the
    fixed set of viable grammar states preserves both legal interpretations
    without backtracking or rescanning any character in this candidate tag.
    An exclusive end bounds recognition to the caller's Markdown block.
    """
    states = {"tag_start"}
    cursor = start + 1
    limit = len(text) if end is None else min(end, len(text))
    while states and cursor < limit:
        classes = _html_character_classes(text[cursor])
        following = {
            target
            for state in states
            for category, target in _HTML_TRANSITIONS[state]
            if category in classes
        }
        cursor += 1
        if "accepted" in following:
            return cursor
        states = following
    return None


class HtmlTagScanner:
    """Recognize tags within ordered Markdown blocks without repeating scans."""

    def __init__(self, text: str, tag_blocks: Iterable[tuple[int, int]]) -> None:
        """Reuse one ordered block traversal for this original source."""
        self._text = text
        self._blocks = iter(tag_blocks)
        self._block = next(self._blocks, None)
        self._line_end = 0

    def end(self, start: int) -> int | None:
        """Find a tag's end without crossing its current Markdown block.

        Calls must visit source offsets in order. Inline and raw HTML blocks
        may contain multiline attributes. Outside those ranges, only the
        current physical line is eligible; its end is cached for repeated
        malformed tag candidates on that line.
        """
        while self._block is not None and start >= self._block[1]:
            self._block = next(self._blocks, None)
        if self._block is not None and start >= self._block[0]:
            limit = self._block[1]
        else:
            if start >= self._line_end:
                linebreak = _LINEBREAKS.search(self._text, start)
                self._line_end = linebreak.start() if linebreak else len(self._text)
            limit = self._line_end
        return html_tag_end(self._text, start, limit)
