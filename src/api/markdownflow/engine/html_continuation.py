"""Restore a missing line break before a block opened by a new model response."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from markdown_it import MarkdownIt
from markdown_it.rules_inline.balance_pairs import link_pairs
from markdown_it.rules_inline.state_inline import StateInline

from markdownflow.preserve_markers import EnvelopeClassifier
from markdownflow.syntax.formatter.patterns import block_html_open_re
from markdownflow.syntax.formatter.types import is_text_family
from markdownflow.syntax.parser.marker_context import analyze_marker_context

if TYPE_CHECKING:
    from collections.abc import Sequence

    from markdown_it.token import Token

_MARKDOWN = MarkdownIt("commonmark")
# A streamed tag name can straddle several chunks. Limit lookahead to a short
# tag prefix, never its attributes or body.
_POSSIBLE_OPENER = re.compile(r" {0,3}(?:<[A-Za-z]{0,32})?")


def starts_html_root(text: str) -> bool:
    """Recognize a standalone opener shared by repeat trimming and display."""
    tag = text.lstrip(" ")
    opening = block_html_open_re.match(tag)
    return (
        opening is not None
        and len(text) - len(tag) <= 3
        and tag.startswith("<")
        and opening[1].lower() not in {"style", "script"}
    )


def _has_open_html(source: str, literals: list[tuple[int, int]], start: int) -> bool:
    """Catch block tags opened inline, where the pager still sees a prose line."""
    opened: list[str] = []
    for first, last in literals:
        if first < start or source[first] != "<":
            continue
        token = source[first:last]
        if (opening := block_html_open_re.match(token)) and not token.endswith("/>"):
            opened.append(opening[1].lower())
        elif (
            opened
            and token.startswith("</")
            and token.endswith(">")
            and token[2:-1].rstrip().lower() == opened[-1]
        ):
            opened.pop()
    return bool(opened)


def _has_open_emphasis(source: str, following: str) -> bool:
    """Look for an unmatched Markdown opener in the final inline block."""
    if "*" not in source and "_" not in source:
        return False
    if source.endswith(("*", "_")) and following == "<":
        # A delimiter at the end needs the opener's first character to
        # determine whether it can open emphasis in the combined text.
        source += following
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[Token] = []
    environment: dict = {}
    _MARKDOWN.block.parse(source, _MARKDOWN, environment, blocks)
    inline = next((token for token in reversed(blocks) if token.type == "inline"), None)
    if inline is None or not inline.map or inline.map[1] != source.count("\n") + 1:
        return False
    state = StateInline(inline.content, _MARKDOWN, environment, [])
    _MARKDOWN.inline.tokenize(state)
    link_pairs(state)
    closed = {delimiter.end for delimiter in state.delimiters if delimiter.end >= 0}
    return any(
        delimiter.open and delimiter.end < 0 and index not in closed
        for index, delimiter in enumerate(state.delimiters)
    )


def _ends_in_prose(source: str, following: str) -> bool:
    line = source.rsplit("\n", 1)[-1]
    if not line.strip() or line.endswith(("\r", "\\")):
        return False
    classifier = EnvelopeClassifier()
    offset = prose_start = 0
    for line in source.split("\n"):
        offset += len(line) + 1
        if not is_text_family(classifier.classify_line(line).type):
            prose_start = offset
    if prose_start == offset:
        return False
    # The formatter tracks top-level visuals. The document grammar also
    # recognizes nested fences, indented code and incomplete inline syntax.
    context = analyze_marker_context(source, final=False)
    if (
        context.pending_html_block
        and context.pending_block_start is not None
        and context.pending_block_start < prose_start
    ):
        # CommonMark HTML can extend through following prose until a blank
        # line. The pager ends a top-level visual at its closing tag.
        source = source[prose_start:]
        prose_start = 0
        context = analyze_marker_context(source, final=False)
    return (
        context.pending_block_start is None
        and context.pending_html_start is None
        and context.pending_reference_start is None
        and context.pending_resource_start is None
        and not context.pending_label_starts
        and not context.unmatched_backticks
        and not context.unmatched_math
        and not (context.markers and not context.markers[-1].complete)
        and not _has_open_html(source, context.literals, prose_start)
        and not _has_open_emphasis(source[prose_start:], following)
    )


class HtmlContinuation:
    """Look for a standalone HTML root at an accepted response boundary."""

    def __init__(self) -> None:
        """Start before the first response with no pending prefix."""
        self._response: int | None = None
        self._prefix: str | None = None

    def feed(self, text: str, response: int, shown: Sequence[str]) -> str:
        """Return visible text, deferring only a possible split opening tag."""
        preceding = ""
        if response != self._response:
            preceding = self.flush()
            self._response = response
            if (preceding or shown) and not (preceding or shown[-1]).endswith("\n"):
                self._prefix = ""
        if self._prefix is None:
            return preceding + text

        candidate = self._prefix + text
        if _POSSIBLE_OPENER.fullmatch(candidate):
            self._prefix = candidate
            return preceding

        self._prefix = None
        if starts_html_root(candidate) and _ends_in_prose(
            "".join(shown) + preceding, candidate[0]
        ):
            return preceding + "\n" + candidate
        return preceding + candidate

    def flush(self) -> str:
        """Release an unresolved response prefix without changing its bytes."""
        text, self._prefix = self._prefix or "", None
        return text
