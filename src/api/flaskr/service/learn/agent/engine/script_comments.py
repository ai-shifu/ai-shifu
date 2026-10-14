"""Remove authored HTML comments while retaining Markdown code examples."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .script_code_spans import build_code_span_index

_FENCE = re.compile(r"[ ]{0,3}(`{3,}|~{3,})([^\r\n]*)")
_BACKTICKS = re.compile(r"`+")
_LINEBREAKS = re.compile(r"\r\n|\r|\n")
_LIST_ITEM = re.compile(r"([-+*]|\d{1,9}[.)])([ ]+)")
_PARAGRAPH_BREAK = re.compile(
    r"(?:#{1,6}(?:[ ]|$)|(?:\*[ ]*){3,}$|(?:_[ ]*){3,}$|(?:-[ ]*){3,}$|<!--|>)"
)
_HTML_TAG = re.compile(
    r"</[A-Za-z][A-Za-z0-9-]*\s*>"
    r"|<[A-Za-z][A-Za-z0-9-]*"
    r"(?:\s+[A-Za-z_:][A-Za-z0-9:._-]*"
    r"(?:\s*=\s*(?:[^\"'=<>`\x00-\x20]+|'[^']*'|\"[^\"]*\"))?)*\s*/?>"
)


@dataclass
class _BlockContext:
    """Distinguish indented examples from paragraph and list continuations."""

    paragraph_open: bool = False
    indented_code: bool = False
    list_indents: list[int] = field(default_factory=list)

    def consume(self, line: str) -> bool:
        """Report whether the line belongs to an indented code block."""
        expanded = line.expandtabs(4).rstrip("\r\n")
        content = expanded.lstrip(" ")
        if not content:
            self.paragraph_open = False
            return self.indented_code

        indent = len(expanded) - len(content)
        block_break = _PARAGRAPH_BREAK.match(content)
        item = (
            None
            if block_break and block_break.end() == len(content)
            else _LIST_ITEM.match(content)
        )
        in_list = bool(self.list_indents)
        # Unindented text can be a lazy continuation of a list paragraph.
        if not self.paragraph_open or item or block_break:
            while self.list_indents and indent < self.list_indents[-1]:
                self.list_indents.pop()
        base_indent = self.list_indents[-1] if self.list_indents else 0
        relative_indent = indent - base_indent
        # Code needs four spaces beyond its container and cannot interrupt a
        # paragraph. Four document-margin spaces are often only list alignment.
        self.indented_code = relative_indent >= 4 and (
            self.indented_code or not self.paragraph_open
        )
        if self.indented_code:
            return True
        if (
            item
            and relative_indent < 4
            and (
                not self.paragraph_open
                or in_list
                or item[1] in "-+*"
                or item[1][:-1] == "1"
            )
        ):
            # Five or more spaces after a marker begin a code example, with
            # only one of those spaces contributing to the list indentation.
            list_padding = 1 if len(item[2]) > 4 else len(item[2])
            self.list_indents.append(indent + len(item[1]) + list_padding)
            if len(item[2]) > 4:
                self.indented_code = True
                self.paragraph_open = False
                return True
            content = content[item.end() :]
            block_break = _PARAGRAPH_BREAK.match(content)
        self.paragraph_open = bool(content) and not (
            block_break and relative_indent < 4
        )
        return False


def _line_end(text: str, start: int) -> int:
    """Return the end of the physical line, including its line break."""
    linebreak = _LINEBREAKS.search(text, start)
    return linebreak.end() if linebreak else len(text)


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
    blocks = _BlockContext()
    code_spans = build_code_span_index(text)
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
                    blocks.paragraph_open = False
                cursor = end
                continue
            if blocks.consume(line):
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
        elif text[cursor] == "<" and (tag := _HTML_TAG.match(text, cursor)):
            # Quoted HTML attributes may contain backticks, but cannot open a
            # Markdown code span that protects a later author comment.
            result.append(tag[0])
            cursor = tag.end()
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
