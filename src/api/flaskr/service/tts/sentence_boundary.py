"""Find punctuation boundaries without moving opening quotes to the prior sentence.

Quotation direction is contextual: ``“`` can close German ``„`` or open an
English quotation. This scanner tracks unmatched opening marks and otherwise
keeps opening quotes with the following text. It deliberately does not infer
sentence boundaries from language or resolve every use of an apostrophe.
"""

import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TypeAlias

import regex

QuoteState: TypeAlias = tuple[str, ...]

# Some writing systems reverse quotation direction or use alternative closing
# forms. Match an existing frame before treating a mark as a new opening.
_QUOTE_PAIRS: dict[str, tuple[str, ...]] = {
    '"': ('"',),
    "'": ("'",),
    "\u00ab": ("\u00bb",),
    "\u00bb": ("\u00ab",),
    "\u2018": ("\u2019",),
    "\u2019": ("\u2019",),
    "\u201a": ("\u2018", "\u2019"),
    "\u201b": ("\u2019",),
    "\u201c": ("\u201d",),
    "\u201d": ("\u201d",),
    "\u201e": ("\u201c", "\u201d"),
    "\u201f": ("\u201d",),
    "\u2039": ("\u203a",),
    "\u203a": ("\u2039",),
    "\u2e42": ("\u201c", "\u201d"),
    "\u300c": ("\u300d",),
    "\u300e": ("\u300f",),
    "\u301d": ("\u301e", "\u301f"),
    "\uff02": ("\uff02",),
    "\uff07": ("\uff07",),
    "\uff62": ("\uff63",),
}
_QUOTATION_MARK = regex.compile(r"\p{Quotation_Mark}")
_APOSTROPHES = frozenset({"'", "\u2019", "\uff07"})
_ASCII_SYMMETRIC_QUOTES = frozenset({'"', "'"})
_WORD_FINAL_QUOTE_MARKS = _APOSTROPHES | frozenset({'"', "\uff02", "\u201d"})


def _is_word_character(char: str) -> bool:
    return bool(char) and (char.isalnum() or unicodedata.category(char).startswith("M"))


def _is_in_word_apostrophe(text: str, index: int) -> bool:
    return (
        text[index] in _APOSTROPHES
        and index > 0
        and index + 1 < len(text)
        and _is_word_character(text[index - 1])
        and _is_word_character(text[index + 1])
    )


def _is_apostrophe_before_word(text: str, index: int) -> bool:
    return (
        text[index] in _APOSTROPHES
        and index + 1 < len(text)
        and _is_word_character(text[index + 1])
    )


def _closes_pending_quote(char: str, state: list[str]) -> bool:
    return bool(state) and char in _QUOTE_PAIRS.get(state[-1], ())


@dataclass(frozen=True)
class SentenceBoundaryMatch:
    """The source span of a terminal run and its closing punctuation."""

    _source: str
    _start: int
    _end: int
    quote_state_before: QuoteState
    quote_state: QuoteState

    def start(self) -> int:
        """Return the terminal run's original source offset."""
        return self._start

    def end(self) -> int:
        """Return the exclusive original source offset after closing marks."""
        return self._end

    def group(self) -> str:
        """Return punctuation and closers, like a regular-expression match."""
        return self._source[self._start : self._end]


class SentenceBoundaryPattern:
    """Provide ``finditer`` with quote context and unchanged source offsets.

    ``terminal_pattern`` is a complete regular expression matching a terminal
    run; ``legacy_closer_pattern`` matches one previously supported closer.
    Initial quote state comes from the last boundary consumed by a stream.
    """

    def __init__(self, terminal_pattern: str, legacy_closer_pattern: str) -> None:
        """Compile the existing terminal and closing-punctuation contracts."""
        self._terminals = regex.compile(terminal_pattern)
        self._legacy_closer = regex.compile(legacy_closer_pattern)

    def _is_unmatched_closer(self, text: str, index: int) -> bool:
        char = text[index]
        if unicodedata.category(char) in {"Pi", "Ps"}:
            return False
        if not self._legacy_closer.fullmatch(char):
            return False
        # Preserve an unpaired legacy closing mark at a boundary, but avoid
        # borrowing a quote that directly introduces the next sentence.
        return not (
            char in _QUOTE_PAIRS
            and index + 1 < len(text)
            and _is_word_character(text[index + 1])
        )

    def _consume_quote(self, text: str, index: int, state: list[str]) -> None:
        char = text[index]
        if _is_in_word_apostrophe(text, index):
            return
        if _closes_pending_quote(char, state):
            if _is_apostrophe_before_word(text, index):
                return
            state.pop()
        elif (
            char in _WORD_FINAL_QUOTE_MARKS
            and index > 0
            and _is_word_character(text[index - 1])
        ):
            # Possessive apostrophes and measurement marks do not open quotes.
            return
        elif char in _QUOTE_PAIRS:
            state.append(char)

    def finditer(
        self,
        text: str,
        *,
        initial_quote_state: QuoteState = (),
        is_final: bool = True,
    ) -> Iterator[SentenceBoundaryMatch]:
        """Yield boundaries, retaining ambiguous trailing quotes in live streams.

        A live buffer ending is not necessarily a text ending. An unmatched
        ASCII quote in its trailing punctuation run may open the next sentence;
        leave that run outside the boundary until more text or finalization.
        """
        state = list(initial_quote_state)
        state_before = tuple(state)
        trailing_quote_start = len(text)
        if not is_final:
            while trailing_quote_start > 0:
                char = text[trailing_quote_start - 1]
                if not (
                    char.isspace()
                    or _QUOTATION_MARK.fullmatch(char)
                    or self._legacy_closer.fullmatch(char)
                ):
                    break
                trailing_quote_start -= 1
        cursor = 0
        while cursor < len(text):
            terminal = self._terminals.match(text, cursor)
            if terminal is None:
                if _QUOTATION_MARK.fullmatch(text[cursor]):
                    self._consume_quote(text, cursor, state)
                cursor += 1
                continue

            start = cursor
            cursor = terminal.end()
            while cursor < len(text):
                char = text[cursor]
                if char.isspace():
                    next_mark = cursor + 1
                    while next_mark < len(text) and text[next_mark].isspace():
                        next_mark += 1
                    if (
                        next_mark == len(text)
                        or not _closes_pending_quote(text[next_mark], state)
                        or _is_apostrophe_before_word(text, next_mark)
                    ):
                        break
                    # French quotation spacing belongs to this source span
                    # only when the following mark closes a known opener.
                    cursor = next_mark
                    char = text[cursor]
                if _QUOTATION_MARK.fullmatch(char):
                    if _is_apostrophe_before_word(text, cursor):
                        break
                    if _closes_pending_quote(char, state):
                        state.pop()
                    elif (
                        not is_final
                        and char in _ASCII_SYMMETRIC_QUOTES
                        and cursor >= trailing_quote_start
                    ) or not self._is_unmatched_closer(text, cursor):
                        break
                elif not self._legacy_closer.fullmatch(char):
                    break
                cursor += 1

            state_after = tuple(state)
            yield SentenceBoundaryMatch(text, start, cursor, state_before, state_after)
            state_before = state_after


def strip_leading_closing_quotes(text: str, quote_state: QuoteState) -> str:
    """Remove only leading quotes that close the prior consumed sentence.

    The caller still scans and consumes the original source to keep offsets and
    quote state intact. A straight or curly quote touching a following word may
    be an apostrophe; preserve that ambiguous content instead of guessing.
    """
    state = list(quote_state)
    cursor = 0
    removed_quote = False
    while cursor < len(text):
        if text[cursor].isspace():
            cursor += 1
            continue
        char = text[cursor]
        if not _QUOTATION_MARK.fullmatch(char) and unicodedata.category(char) in {
            "Pe",
            "Pf",
        }:
            # Nested brackets can arrive before the quote that proves this
            # prefix belongs to the prior sentence. Do not commit to removing
            # them unless a pending quote is actually closed below.
            cursor += 1
            continue
        if not _closes_pending_quote(char, state):
            break
        if _is_apostrophe_before_word(text, cursor):
            break
        state.pop()
        removed_quote = True
        cursor += 1
    return text[cursor:] if removed_quote else text
