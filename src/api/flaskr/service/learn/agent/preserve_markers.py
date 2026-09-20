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
`a === b` inside a fence is an operator, not a marker.
"""

from __future__ import annotations

import re

# The same shapes `markdown_flow` recognises: a fence line of `!` and three or more `=`, and the
# inline tokens `!===` and `===`.
_FENCE_LINE = re.compile(r"^[ \t]*!={3,}[ \t]*$")
_CODE_FENCE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})")
_MARKERS = re.compile(r"!?={3,}")
# An unfinished line that may still become a fence line of either kind.
_MAY_BE_FENCE = re.compile(r"^[ ]{0,3}[`~]|^[ \t]*!?=*$")
# The tail of an unfinished line that may still become a marker once more text arrives.
_PARTIAL_TAIL = re.compile(r"!?=*$")


class PreserveMarkerFilter:
    """Remove verbatim markers from streamed text, one chunk at a time."""

    def __init__(self) -> None:
        """Start with nothing buffered and no code fence open."""
        self._line = ""
        self._released_some_of_line = False
        self._in_code = False

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
            out.append(head if self._in_code else _MARKERS.sub("", head))
        return "".join(out)

    def flush(self) -> str:
        """Release what was held back, because no more text is coming."""
        tail, self._line = self._line, ""
        self._released_some_of_line = False
        if not tail:
            return ""
        # A fragment that never became a marker is text, and is shown as it is.
        return tail if self._in_code else _MARKERS.sub("", tail)

    def _complete_line(self, line: str) -> str:
        whole_line = not self._released_some_of_line
        if whole_line and _CODE_FENCE.match(line):
            self._in_code = not self._in_code
            return line + "\n"
        if self._in_code:
            return line + "\n"
        if whole_line and _FENCE_LINE.match(line):
            # The fence line itself: not content. Its newline goes too, or every fenced block
            # would gain a blank line.
            return ""
        return _MARKERS.sub("", line) + "\n"

    def _split_partial(self, text: str) -> tuple[str, str]:
        """Split an unfinished line into what can go out now and what must wait."""
        if not text:
            return "", ""
        if not self._released_some_of_line and _MAY_BE_FENCE.match(text):
            return "", text
        if self._in_code:
            return text, ""
        match = _PARTIAL_TAIL.search(text)
        return text[: match.start()], text[match.start() :]
