"""Index possible inline-code delimiters in one pass over authored Markdown."""

from __future__ import annotations

import re

_TOKENS = re.compile(r"`+|\r\n|[\r\n]")


def build_code_span_index(text: str) -> dict[int, int]:
    """Map possible opening offsets to the next equal-length delimiter's end.

    The index is lexical: the caller decides which openings occur outside
    comments and block code. Each run and possible opening is visited once,
    so unmatched delimiter lengths cannot trigger repeated suffix scans.
    Blank physical lines end a paragraph, including CRLF and whitespace-only
    lines. A single CRLF is one physical line break.
    """
    spans: dict[int, int] = {}
    pending: dict[int, list[int]] = {}
    linebreak_end: int | None = None
    for token in _TOKENS.finditer(text):
        start, end = token.span()
        if text[start] != "`":
            if linebreak_end is not None and not text[linebreak_end:start].strip(" \t"):
                pending.clear()
            linebreak_end = end
            continue

        linebreak_end = None
        length = end - start
        for opening in pending.pop(length, ()):
            spans[opening] = end
        pending[length] = [start]
        # Outside a span, escaping the first backtick leaves the run's suffix
        # available as an opening. Inside a span, backslashes are literal and
        # only a whole delimiter run can close it.
        if length > 1 and start > 0 and text[start - 1] == "\\":
            pending.setdefault(length - 1, []).append(start + 1)
    return spans
