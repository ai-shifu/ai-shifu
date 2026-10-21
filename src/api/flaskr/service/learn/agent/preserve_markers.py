"""Strip MarkdownFlow's verbatim markers from what the engine says.

A script marks content the model must reproduce word for word with `===like this===`, or between
`!===` fence lines. A 1.0 lesson never shows those markers: the parser recognises the block, emits
its content as it is, and the model never sees it. The 2.0 engine hands the model the whole script
and asks it to reproduce such content exactly -- which it does, markers included. Left in, they are
rendered, spoken and subtitled: a listener heard "===帮助 100 万人顺利走进 AGI 时代===".

The markers are the script's syntax, not the lesson's content, so they are removed here from the
engine's text before it reaches anything that shows or speaks it, in every mode. What sits between
them is kept, untouched.

Text arrives in chunks that can split a marker, so a trailing run of `=` that could still become
one is held back until the next chunk, or released as it is when the turn ends. A line that could
still turn out to be a fence -- a code fence, or a `!===` line -- is held whole until its end, since
that is a decision about the line, not about a fragment of it. Code is passed through as it is:
`a === b` inside a fence or an HTML script is an operator, not a marker.
"""

from __future__ import annotations

import re

# The same shapes `markdown_flow` recognises: a fence line of `!` and three or more `=`, and the
# inline tokens `!===` and `===`.
_FENCE_LINE = re.compile(r"^[ \t]*!={3,}[ \t]*$")
# A code fence opens with three or more backticks or tildes; it closes only with a line of the
# same character, at least as long, and nothing after it (CommonMark). A tilde line does not
# close a backtick fence, a shorter fence does not close a longer one, and a line with trailing
# text is content inside the block.
_CODE_FENCE_OPEN = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})")
_CODE_FENCE_CLOSE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})[ \t]*$")
_MARKERS = re.compile(r"!?={3,}")
# An unfinished line that may still become a fence line of either kind.
_MAY_BE_FENCE = re.compile(r"^[ ]{0,3}[`~]|^[ \t]*!?=*$")
# The tail of an unfinished line that may still become a marker once more text arrives.
_PARTIAL_TAIL = re.compile(r"!?=*$")
_HTML_TAG_HEAD = re.compile(r"</?([a-zA-Z][a-zA-Z0-9:-]*)(?=[\s/>])")
_HTML_TAG_PREFIX = re.compile(r"</?[a-zA-Z][a-zA-Z0-9:-]*$")
_RAW_TEXT_END = {
    tag: re.compile(rf"</{tag}(?=[\s/>])", re.IGNORECASE) for tag in ("script", "style")
}


def _tag_end(text: str, start: int) -> int | None:
    """Find an HTML tag's end without treating a quoted '>' as its end."""
    quote: str | None = None
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == ">":
            return index + 1
    return None


class PreserveMarkerFilter:
    """Remove verbatim markers from streamed text, one chunk at a time."""

    def __init__(self) -> None:
        """Start with nothing buffered and no code fence open."""
        self._line = ""
        self._released_some_of_line = False
        # The fence that opened the code block we are in: its character and length, or None.
        self._fence: tuple[str, int] | None = None
        self._raw_tag: str | None = None
        # A tag/comment or raw-text closing tag may be split between chunks.
        self._html_tail = ""

    def feed(self, text: str) -> str:
        """Return `text` with markers removed, less any tail that might still become one."""
        if not text:
            return ""
        out: list[str] = []
        self._line += text
        while "\n" in self._line:
            line, self._line = self._line.split("\n", 1)
            out.append(self._complete_line(line))
            self._released_some_of_line = False
        head, held = self._split_partial(self._line)
        self._line = held
        if head:
            self._released_some_of_line = True
            out.append(head if self._fence else self._filter_html(head))
        return "".join(out)

    def flush(self) -> str:
        """Release what was held back, because no more text is coming."""
        tail, self._line = self._line, ""
        self._released_some_of_line = False
        # A fragment that never became a marker is text, and is shown as it is.
        out = tail if self._fence else self._filter_html(tail)
        # An unfinished tag is still source text, not a MarkdownFlow marker.
        html_tail, self._html_tail = self._html_tail, ""
        return out + html_tail

    def _complete_line(self, line: str) -> str:
        whole_line = not self._released_some_of_line
        if self._fence is not None:
            if whole_line and self._closes_fence(line):
                self._fence = None
            return line + "\n"
        in_html = self._raw_tag is not None or bool(self._html_tail)
        if whole_line and not in_html:
            opening = _CODE_FENCE_OPEN.match(line)
            if opening:
                run = opening.group(1)
                self._fence = (run[0], len(run))
                return line + "\n"
        if whole_line and not in_html and _FENCE_LINE.match(line):
            # The fence line itself: not content. Its newline goes too, or every fenced block
            # would gain a blank line.
            return ""
        return self._filter_html(line + "\n")

    def _filter_html(self, text: str) -> str:
        """Strip prose markers while copying HTML source and raw text unchanged."""
        text = self._html_tail + text
        self._html_tail = ""
        out: list[str] = []
        index = 0
        while index < len(text):
            if self._raw_tag is not None:
                match = _RAW_TEXT_END[self._raw_tag].search(text, index)
                if match is None:
                    # Keep only a possible closing-tag prefix; stream all other code.
                    last_lt = text.rfind("<", index)
                    closer = f"</{self._raw_tag}"
                    if last_lt >= index and closer.startswith(text[last_lt:].lower()):
                        out.append(text[index:last_lt])
                        self._html_tail = text[last_lt:]
                    else:
                        out.append(text[index:])
                    break
                end = _tag_end(text, match.end())
                if end is None:
                    out.append(text[index : match.start()])
                    self._html_tail = text[match.start() :]
                    break
                out.append(text[index:end])
                self._raw_tag = None
                index = end
                continue

            start = text.find("<", index)
            if start < 0:
                out.append(_MARKERS.sub("", text[index:]))
                break
            out.append(_MARKERS.sub("", text[index:start]))
            fragment = text[start:]
            if fragment.startswith("<!--"):
                end = text.find("-->", start + 4)
                end = end + 3 if end >= 0 else None
                tag = None
            else:
                match = _HTML_TAG_HEAD.match(text, start)
                if match is None:
                    if (
                        fragment in ("<", "</")
                        or "<!--".startswith(fragment)
                        or _HTML_TAG_PREFIX.fullmatch(fragment)
                    ):
                        self._html_tail = fragment
                        break
                    out.append("<")
                    index = start + 1
                    continue
                end = _tag_end(text, match.end())
                tag = match.group(1).lower() if not fragment.startswith("</") else None
            if end is None:
                self._html_tail = fragment
                break
            out.append(text[start:end])
            if tag in _RAW_TEXT_END:
                # In HTML, <script/> still opens a non-void raw-text element.
                self._raw_tag = tag
            index = end
        return "".join(out)

    def _split_partial(self, text: str) -> tuple[str, str]:
        """Split an unfinished line into what can go out now and what must wait."""
        if not text:
            return "", ""
        if not self._released_some_of_line and _MAY_BE_FENCE.match(text):
            return "", text
        if self._fence is not None:
            return text, ""
        match = _PARTIAL_TAIL.search(text)
        return text[: match.start()], text[match.start() :]

    def _closes_fence(self, line: str) -> bool:
        closing = _CODE_FENCE_CLOSE.match(line)
        if closing is None or self._fence is None:
            return False
        run = closing.group(1)
        char, length = self._fence
        return run[0] == char and len(run) >= length
