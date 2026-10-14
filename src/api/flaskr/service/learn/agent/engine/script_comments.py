"""Remove authored HTML comments while retaining Markdown code examples."""

from __future__ import annotations

import re

_FENCE = re.compile(r"[ ]{0,3}(`{3,}|~{3,})([^\r\n]*)")
_BACKTICKS = re.compile(r"`+")
_LINEBREAKS = re.compile(r"\r\n|\r|\n")


def _line_end(text: str, start: int) -> int:
    """Return the end of the physical line, including its line break."""
    linebreak = _LINEBREAKS.search(text, start)
    return linebreak.end() if linebreak else len(text)


def _code_span_end(text: str, start: int, marker: str) -> int | None:
    """Find a matching inline-code delimiter in the same Markdown paragraph."""
    for match in _BACKTICKS.finditer(text, start + len(marker)):
        if match[0] == marker:
            intervening = text[start + len(marker) : match.start()]
            if re.search(r"(?:\r\n|\r|\n)[ \t]*(?:\r\n|\r|\n)", intervening):
                return None
            return match.end()
    return None


def strip_comments(text: str) -> str:
    """Remove HTML comments outside Markdown code examples without moving lines.

    Unclosed comments extend to the end of the document. Retaining their line
    breaks keeps MarkdownFlow block separators and surrounding text in place.
    The stored author document and learner values are never changed by this
    source-text projection.
    """
    result: list[str] = []
    cursor = 0
    opening: str | None = None
    while cursor < len(text):
        at_line_start = cursor == 0 or text[cursor - 1] in "\r\n"
        if at_line_start:
            end = _line_end(text, cursor)
            line = text[cursor:end]
            fence = _FENCE.match(line)
            if opening is not None:
                result.append(line)
                if (
                    fence
                    and fence[1][0] == opening[0]
                    and len(fence[1]) >= len(opening)
                    and not fence[2].strip()
                ):
                    opening = None
                cursor = end
                continue
            if line.expandtabs(4).startswith("    "):
                result.append(line)
                cursor = end
                continue
            if fence and (fence[1][0] == "~" or "`" not in fence[2]):
                opening = fence[1]
                result.append(line)
                cursor = end
                continue
        if text.startswith("<!--", cursor):
            closing = text.find("-->", cursor + 4)
            end = closing + 3 if closing >= 0 else len(text)
            result.extend(_LINEBREAKS.findall(text[cursor:end]))
            cursor = end
        elif text[cursor] == "`":
            marker = _BACKTICKS.match(text, cursor)
            if marker is not None:
                end = _code_span_end(text, cursor, marker[0])
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
