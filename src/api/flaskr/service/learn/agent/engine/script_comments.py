"""Remove authored HTML comments while retaining Markdown code examples."""

from __future__ import annotations

import re
from heapq import merge

from .script_code_blocks import build_block_indexes
from .script_code_spans import build_code_span_index
from .script_html_tags import HtmlTagScanner

_BACKTICKS = re.compile(r"`+")
_LINEBREAKS = re.compile(r"\r\n|\r|\n")


def comment_ranges(text: str) -> list[tuple[int, int]]:
    """Locate authored comments using the canonical Markdown source scan.

    Returned offsets refer to the original source, including an unclosed
    comment's remaining suffix. Code examples and quoted HTML attributes are
    literal data. Recognition never crosses their CommonMark block boundaries.
    """
    ranges: list[tuple[int, int]] = []
    cursor = 0
    blocks = build_block_indexes(text)
    code_spans = build_code_span_index(text, blocks.inline_blocks)
    tags = HtmlTagScanner(text, merge(blocks.inline_blocks, blocks.html_blocks))
    while cursor < len(text):
        at_line_start = cursor == 0 or text[cursor - 1] in "\r\n"
        if at_line_start:
            end = blocks.code_blocks.get(cursor)
            if end is not None:
                cursor = end
                continue
        if text.startswith("<!--", cursor):
            closing = text.find("-->", cursor + 4)
            end = closing + 3 if closing >= 0 else len(text)
            ranges.append((cursor, end))
            cursor = end
        elif text[cursor] == "<" and (tag_end := tags.end(cursor)):
            # Quoted HTML attributes may contain backticks, but cannot open a
            # Markdown code span that protects a later author comment.
            cursor = tag_end
        elif text[cursor] == "`":
            marker = _BACKTICKS.match(text, cursor)
            if marker is not None:
                end = code_spans.get(cursor)
                if end is not None:
                    cursor = end
                    continue
                cursor = marker.end()
        elif (
            text[cursor] == "\\"
            and cursor + 1 < len(text)
            and text[cursor + 1] in "\\`<"
        ):
            cursor += 2
        else:
            cursor += 1
    return ranges


def strip_comments(text: str) -> str:
    """Remove authored comments while keeping their original line breaks.

    The stored author document and learner values are never changed by this
    source-text projection. Other consumers can use the same original-source
    comment ranges without independently interpreting Markdown syntax.
    """
    result: list[str] = []
    cursor = 0
    for start, end in comment_ranges(text):
        result.append(text[cursor:start])
        result.extend(_LINEBREAKS.findall(text[start:end]))
        cursor = end
    result.append(text[cursor:])
    return "".join(result)
