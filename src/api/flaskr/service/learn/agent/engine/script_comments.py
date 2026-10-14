"""Remove authored HTML comments while retaining Markdown code examples."""

from __future__ import annotations

import re

from .script_code_blocks import build_block_indexes
from .script_code_spans import build_code_span_index
from .script_html_tags import html_tag_end

_BACKTICKS = re.compile(r"`+")
_LINEBREAKS = re.compile(r"\r\n|\r|\n")


def strip_comments(text: str) -> str:
    """Remove HTML comments outside Markdown code examples without moving lines.

    Unclosed comments extend to the end of the document. Retaining their line
    breaks keeps MarkdownFlow block separators and surrounding text in place.
    The stored author document and learner values are never changed by this
    source-text projection.
    """
    result: list[str] = []
    cursor = 0
    code_blocks, inline_blocks = build_block_indexes(text)
    code_spans = build_code_span_index(text, inline_blocks)
    while cursor < len(text):
        at_line_start = cursor == 0 or text[cursor - 1] in "\r\n"
        if at_line_start:
            end = code_blocks.get(cursor)
            if end is not None:
                result.append(text[cursor:end])
                cursor = end
                continue
        if text.startswith("<!--", cursor):
            closing = text.find("-->", cursor + 4)
            end = closing + 3 if closing >= 0 else len(text)
            result.extend(_LINEBREAKS.findall(text[cursor:end]))
            cursor = end
        elif text[cursor] == "<" and (tag_end := html_tag_end(text, cursor)):
            # Quoted HTML attributes may contain backticks, but cannot open a
            # Markdown code span that protects a later author comment.
            result.append(text[cursor:tag_end])
            cursor = tag_end
        elif text[cursor] == "`":
            marker = _BACKTICKS.match(text, cursor)
            if marker is not None:
                end = code_spans.get(cursor)
                if end is not None:
                    result.append(text[cursor:end])
                    cursor = end
                    continue
                result.append(marker[0])
                cursor = marker.end()
        elif (
            text[cursor] == "\\"
            and cursor + 1 < len(text)
            and text[cursor + 1] in "\\`<"
        ):
            result.append(text[cursor : cursor + 2])
            cursor += 2
        else:
            result.append(text[cursor])
            cursor += 1
    return "".join(result)
