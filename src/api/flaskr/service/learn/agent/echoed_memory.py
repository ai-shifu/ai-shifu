"""Keep the model's copy of the engine's `<memory>` section out of the lesson.

The engine opens every lesson with a message whose first section is the learner's memory, framed
as `<memory>` followed by a JSON object and `</memory>`. A model that wants to record something
is meant to call `remember`. Some write it in the format they were shown instead: a lesson
that had just asked about the learner's experience put this at the top of its reply, and the
learner read it --

    <memory>
    {"key": "experience", "value": "never written code", "scope": "session"}
    </memory>

The system prompt says the section is input; this is what makes that hold when the model does not
listen. `<memory>` is the engine's own framing and not an HTML element, so a lesson has no
reason to put one at the start of a line of prose. What is removed is only that: a block opened
by `<memory>` at the start of a line, outside code, up to its `</memory>`, and the blank lines
right after it. A lesson about prompts that shows the tag inside a code block, or mid-sentence,
keeps it.

Text arrives in chunks that can split the tag, so a line that could still turn out to open a block
is held until it is known, and an open block is held until it closes. A block that never closes
is released as it is when the turn ends: dropping it would take the rest of the lesson with it.
"""

from __future__ import annotations

import re

_OPEN = "<memory>"
_CLOSE = "</memory>"
# CommonMark: a backtick fence's info string cannot itself contain a backtick; a tilde fence's can.
_CODE_FENCE_OPEN = re.compile(r"^[ ]{0,3}(?:(`{3,})(?![^\n]*`)|(~{3,}))")
_CODE_FENCE_CLOSE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})[ \t]*$")
# An unfinished line that may still become a code fence, and so decide what the lines after it are.
_MAY_BE_FENCE = re.compile(r"^[ ]{0,3}[`~]")


# Up to three spaces of indent: four is an indented code block in Markdown, where a lesson showing
# the format puts it.
_INDENT = re.compile(r"^[ ]{0,3}")


def _opens_block(line: str) -> bool:
    return line[_INDENT.match(line).end() :].startswith(_OPEN)


def _may_open_block(partial: str) -> bool:
    """Whether a line still arriving could turn out to open a block."""
    rest = partial[_INDENT.match(partial).end() :]
    if rest.startswith((" ", "\t")):
        return False
    return _OPEN.startswith(rest) or rest.startswith(_OPEN)


class EchoedMemoryFilter:
    """Remove `<memory>` blocks from streamed text, one chunk at a time."""

    def __init__(self) -> None:
        """Start with nothing held, outside any block or code fence."""
        self._line = ""
        self._released_some_of_line = False
        self._block: list[str] | None = None
        self._fence: tuple[str, int] | None = None
        self._after_block = False

    def feed(self, text: str) -> str:
        """Return `text` with any finished block removed, holding back what is undecided."""
        if not text:
            return ""
        out: list[str] = []
        self._line += text
        while "\n" in self._line:
            line, self._line = self._line.split("\n", 1)
            out.append(self._complete_line(line + "\n"))
            self._released_some_of_line = False
        if self._line and self._block is None and not self._holds(self._line):
            out.append(self._line)
            self._line = ""
            self._released_some_of_line = True
            self._after_block = False
        return "".join(out)

    def flush(self) -> str:
        """Release what is still held, because no more text is coming.

        The last line is read as a line first: a turn may end on `</memory>`, or on a whole
        block, without a newline after it. Only a block still open after that is released.
        """
        tail = self._complete_line(self._line) if self._line else ""
        held = "".join(self._block or [])
        self._line = ""
        self._block = None
        self._released_some_of_line = False
        self._after_block = False
        return tail + held

    def _holds(self, partial: str) -> bool:
        if self._released_some_of_line:
            return False
        if self._fence is not None:
            # Inside code nothing opens a block, but a line that may be the closing fence waits
            # for its end: released in part, it could no longer close the code.
            return _MAY_BE_FENCE.match(partial) is not None
        if self._after_block and not partial.strip():
            return True
        return _may_open_block(partial) or _MAY_BE_FENCE.match(partial) is not None

    def _complete_line(self, line: str) -> str:
        if self._block is not None:
            end = line.find(_CLOSE)
            if end < 0:
                self._block.append(line)
                return ""
            self._block = None
            self._after_block = True
            rest = line[end + len(_CLOSE) :]
            return rest if rest.strip() else ""
        whole_line = not self._released_some_of_line
        if self._fence is not None:
            if whole_line and self._closes_fence(line):
                self._fence = None
            return line
        if whole_line and _opens_block(line):
            start = line.find(_OPEN)
            end = line.find(_CLOSE, start)
            if end < 0:
                self._block = [line]
                return ""
            self._after_block = True
            rest = line[end + len(_CLOSE) :]
            return rest if rest.strip() else ""
        if self._after_block and whole_line and not line.strip():
            return ""
        self._after_block = False
        if whole_line:
            opened = _CODE_FENCE_OPEN.match(line)
            if opened:
                fence = opened.group(1) or opened.group(2)
                self._fence = (fence[0], len(fence))
        return line

    def _closes_fence(self, line: str) -> bool:
        closing = _CODE_FENCE_CLOSE.match(line.rstrip("\n"))
        if not closing or self._fence is None:
            return False
        char, length = self._fence
        return closing.group(1)[0] == char and len(closing.group(1)) >= length
