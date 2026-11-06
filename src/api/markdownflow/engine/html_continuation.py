"""Restore a missing line break before a block opened by a new model response."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from markdownflow.preserve_markers import EnvelopeClassifier
from markdownflow.syntax.formatter.patterns import block_html_open_re, html_close_tag_re
from markdownflow.syntax.formatter.types import ElementType
from markdownflow.syntax.parser.marker_context import analyze_marker_context

if TYPE_CHECKING:
    from collections.abc import Sequence

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
            (closing := html_close_tag_re.fullmatch(token))
            and opened
            and opened[-1] == closing[1].lower()
        ):
            opened.pop()
    return bool(opened)


def _ends_in_prose(source: str) -> bool:
    line = source.rsplit("\n", 1)[-1]
    if not line.strip() or line.endswith(("\r", "\\")):
        return False
    classifier = EnvelopeClassifier()
    offset = prose_start = 0
    for line in source.split("\n"):
        offset += len(line) + 1
        if classifier.classify_line(line).type != ElementType.TEXT:
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
        if starts_html_root(candidate) and _ends_in_prose("".join(shown) + preceding):
            return preceding + "\n" + candidate
        return preceding + candidate

    def flush(self) -> str:
        """Release an unresolved response prefix without changing its bytes."""
        text, self._prefix = self._prefix or "", None
        return text
