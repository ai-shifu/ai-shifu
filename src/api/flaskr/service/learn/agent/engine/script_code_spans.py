"""Index possible inline-code delimiters in one pass over authored Markdown."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

_TOKENS = re.compile(r"`+|\r\n|[\r\n]")


def build_code_span_index(
    text: str, inline_blocks: Iterable[tuple[int, int]] | None = None
) -> dict[int, int]:
    """Map possible opening offsets to the next equal-length delimiter's end.

    The caller decides which openings occur outside comments and block code.
    When ordered inline-block ranges are provided, matching stays inside one
    CommonMark block; raw HTML and block-code contents are never inline code.
    Each run and possible opening is visited once, so unmatched delimiter
    lengths cannot trigger repeated suffix scans.
    Blank physical lines end a paragraph, including CRLF and whitespace-only
    lines. A single CRLF is one physical line break.
    """
    spans: dict[int, int] = {}
    pending: dict[int, list[int]] = {}
    linebreak_end: int | None = None
    blocks = iter(inline_blocks) if inline_blocks is not None else None
    block = next(blocks, None) if blocks is not None else None
    for token in _TOKENS.finditer(text):
        start, end = token.span()
        if blocks is not None:
            while block is not None and start >= block[1]:
                block = next(blocks, None)
                pending.clear()
                linebreak_end = None
            if block is None:
                break
            if start < block[0]:
                continue
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
