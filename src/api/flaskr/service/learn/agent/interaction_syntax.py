r"""Catch an interaction the model wrote into its narration instead of asking for one.

The contract says a question reaches the learner by calling `interact`. Models write it as text
anyway: of twelve turns whose narration carried `?[...]`, eleven had made no tool call at all --
in a real course, across six of its lessons.

Left alone the lesson looks right and behaves wrongly. The browser renders any `?[...]` it finds
in content, so the learner sees controls and can press them; but the engine never asked, so there
is no pending interaction, and the turn ends on text rather than on a question. A turn ending on
text is the host's signal to carry on by itself -- so the lesson asks, and then runs past its own
question while the learner is still reading it.

So the spans are taken out of the narration as they stream, and what happens to them is decided
when the turn ends and it is known whether the model also called the tool:

* it called the tool -- the spans are dropped. The tool call is the real question; the narrated
  copy was a second set of controls under the first, with the question wedged between them.
* it never called the tool -- the last span is sent as a real interaction. The learner gets the
  question the model meant to ask, and the turn ends on it, so nothing runs past it.

A span is not turned back into a pending question inside the engine: the engine did not ask, and
an answer arrives as a remark for it to react to. That is a lesser wrong than a lesson that
sprints past a question it just put on the screen.

What counts as code is approximated, not parsed: fenced blocks and four-space indents, which
is what a lesson showing the notation uses. Markdown has other ways to make something code --
a list item holding an indented block, an HTML block -- and inside those a question would still
be taken as one. The approximation is worth naming rather than hiding: getting it exactly right
means running the browser's Markdown parser here, and the failure it leaves is the one that
existed before any of this.

`\?[` is left exactly as it is. The grammar treats it as text rather than an interaction, which
is how a lesson about the syntax shows the syntax.
"""

from __future__ import annotations

import re

_OPEN = "?["
_FENCE_OPEN = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})", re.MULTILINE)
# A block closes only on a line of its own fence character, at least as long, with nothing after
# it but whitespace. `` ```not-a-close `` opens nothing and closes nothing; it is code.
_FENCE_CLOSE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})[ \t]*$")
# A line still arriving that may yet become one.
_MAY_BE_FENCE = re.compile(r"^[ ]{0,3}[`~]", re.MULTILINE)
_CLOSE = "]"


class InteractionSyntaxFilter:
    """Pull whole `?[...]` spans out of streamed narration, remembering each one."""

    def __init__(self) -> None:
        """Start with nothing held and nothing seen."""
        self._held = ""
        self._inside = False
        # The code fence we are inside, as its character and length, or None. A lesson about the
        # notation shows the notation in a code block, and the grammar does not read one as an
        # interaction either.
        self._fence: tuple[str, int] | None = None
        # The last character already sent out. An opener is escaped by the character before it,
        # and that character may have left in an earlier chunk, so it has to be remembered.
        self._previous = ""
        # What has already gone out on the line being built, so an indent that left in an
        # earlier chunk still counts as the start of its line.
        self._line_so_far = ""
        self.spans: list[str] = []

    def feed(self, text: str) -> str:
        """Return `text` with any complete span removed, holding back an unfinished one."""
        if not text:
            return ""
        out: list[str] = []
        self._held += text
        while self._held:
            if self._inside:
                end = self._held.find(_CLOSE)
                if end < 0:
                    return "".join(out)
                if len(self._held) == end + 1:
                    # The character after the bracket decides whether this is a question or a
                    # link, and it has not arrived yet.
                    return "".join(out)
                if self._held[end + 1] == "(":
                    self._emit(out, self._held[: end + 1])
                    self._held = self._held[end + 1 :]
                    self._inside = False
                    continue
                self.spans.append(self._held[: end + 1])
                self._held = self._held[end + 1 :]
                self._inside = False
                continue
            fence = self._next_fence_line(self._held)
            start = (
                -1
                if self._fence is not None
                else self._find_open(self._held, self._previous)
            )
            if (
                fence is not None
                and fence[1] is None
                and (start < 0 or fence[0] < start)
            ):
                # A line that could still turn out to open or close a code block waits for its
                # end. Released as ordinary text, the block would never be recognised and the
                # example inside it would be taken for a question.
                #
                # Only when nothing before it is already a question. Waiting first meant an
                # unfinished fence line further on could keep a question that preceded it from
                # ever being recognised, which is decided by where the stream happened to break.
                self._emit(out, self._held[: fence[0]])
                self._held = self._held[fence[0] :]
                return "".join(out)
            if (
                fence is not None
                and fence[1] is not None
                and (start < 0 or fence[0] < start)
            ):
                line_end = fence[1]
                self._toggle_fence(self._held[fence[0] : line_end])
                self._emit(out, self._held[:line_end])
                self._held = self._held[line_end:]
                continue
            if start >= 0 and self._in_indented_code(self._held, start):
                # Four spaces of indent is a code block of its own in Markdown, and the browser
                # renders its contents as code rather than as controls. Left as text.
                line_end = self._held.find("\n", start)
                if line_end < 0:
                    return "".join(out)
                self._emit(out, self._held[: line_end + 1])
                self._held = self._held[line_end + 1 :]
                continue
            if start < 0 and self._fence is not None:
                # Inside a code block with no fence in sight: all text, but a line that may yet
                # close the block waits for its end.
                cut = self._held.rfind("\n") + 1
                self._emit(out, self._held[:cut])
                self._held = self._held[cut:]
                return "".join(out)
            if start < 0:
                # A trailing `?` waits for the next chunk, which may turn it into an opener.
                # Without this the same output is handled differently depending on where the
                # network split it, which is the one thing a filter like this must not do. It
                # costs nothing a learner can see: consecutive pieces of a turn's text are
                # written as one element, so a passage released in two parts still arrives whole.
                if self._held.endswith("?"):
                    self._emit(out, self._held[:-1])
                    self._held = self._held[-1:]
                else:
                    self._emit(out, self._held)
                    self._held = ""
                return "".join(out)
            close = self._held.find(_CLOSE, start)
            if close >= 0 and self._held[close + 1 : close + 2] == "(":
                # `?[text](link)` is a link, not a question: the grammar's own pattern ends in a
                # negative lookahead for the bracket, and a lesson may well write one.
                self._emit(out, self._held[: close + 1])
                self._held = self._held[close + 1 :]
                continue
            if (
                close < 0
                and self._held.endswith(_CLOSE) is False
                and len(self._held) - start < 2
            ):
                return "".join(out)
            self._emit(out, self._held[:start])
            self._held = self._held[start:]
            self._inside = True
        return "".join(out)

    def _emit(self, out: list[str], text: str) -> None:
        """Send text on, remembering its last character for the next escape check."""
        if not text:
            return
        out.append(text)
        self._previous = text[-1]
        cut = text.rfind("\n")
        self._line_so_far = text[cut + 1 :] if cut >= 0 else self._line_so_far + text

    def flush(self) -> str:
        """Release what is still held, because no more text is coming.

        A span waiting only to find out whether a bracket follows it is settled here: nothing
        follows it, so it is a question and not a link. An opener that never closed was never a
        span at all -- it is text, and it goes out as text.
        """
        if self._inside and self._held.endswith(_CLOSE):
            self.spans.append(self._held)
            self._held = ""
        tail, self._held = self._held, ""
        self._inside = False
        self._fence = None
        return tail

    def _next_fence_line(self, text: str) -> tuple[int, int | None] | None:
        """Where the next fence line starts in `text`, and where it ends.

        The end is None when the line has not finished arriving, which is the caller's cue to
        wait for it rather than let it out as ordinary text. Fences are line-based, so this
        looks at every line start in what is held, not only at the first.
        """
        for match in _FENCE_OPEN.finditer(text):
            if not self._at_line_start(text, match.start()):
                continue
            line_end = text.find("\n", match.start())
            if line_end < 0:
                return (match.start(), None)
            if self._fence is not None and not self._closes_here(
                text[match.start() : line_end]
            ):
                # Inside a block, a line that is not a valid closer is part of the code.
                continue
            return (match.start(), line_end + 1)
        for partial in _MAY_BE_FENCE.finditer(text):
            if (
                self._at_line_start(text, partial.start())
                and "\n" not in text[partial.start() :]
            ):
                return (partial.start(), None)
        return None

    def _in_indented_code(self, text: str, at: int) -> bool:
        """Whether the line `at` sits on is indented far enough to be a code block."""
        before = text[:at]
        cut = before.rfind("\n")
        line = before[cut + 1 :] if cut >= 0 else self._line_so_far + before
        indent = len(line) - len(line.lstrip(" "))
        return line[:indent] == line and indent >= 4

    def _at_line_start(self, text: str, at: int) -> bool:
        """Whether `at` really begins a line, counting what has already been sent out.

        Position zero of what is held is only a line start when nothing was emitted on that line
        before it. Treating it as one made the same input behave differently depending on where
        the stream was cut: `prefix` and three backticks on one line opened a block when the cut
        fell between them, and did not when it did not.
        """
        if at > 0:
            before = text[:at]
            line = before[before.rfind("\n") + 1 :]
        else:
            line = self._line_so_far
        # A fence may be indented by up to three spaces, so what stands before it on its line
        # counts as nothing only when it is that indent. The indent may have left in an earlier
        # chunk, which is why this is tracked rather than read off the character before.
        return line == "" or (len(line) <= 3 and line.isspace() and "\n" not in line)

    @staticmethod
    def _closes_here(line: str) -> bool:
        """Whether this line is a valid closing fence, rather than code that starts like one."""
        return _FENCE_CLOSE.match(line) is not None

    def _toggle_fence(self, line: str) -> None:
        """Open a code block on this fence line, or close the one it ends."""
        match = _FENCE_OPEN.match(line)
        if match is None:
            return
        run = match.group(1)
        if self._fence is None:
            self._fence = (run[0], len(run))
        elif (
            _FENCE_CLOSE.match(line) is not None
            and run[0] == self._fence[0]
            and len(run) >= self._fence[1]
        ):
            self._fence = None

    @staticmethod
    def _find_open(text: str, previous: str) -> int:
        """Index of the next unescaped `?[`, or -1.

        `previous` is the character before `text`, which decides the case where an opener sits at
        the very start of what is left to scan.
        """
        at = 0
        while True:
            at = text.find(_OPEN, at)
            if at < 0:
                return -1
            before = text[at - 1] if at else previous
            if before != "\\":
                return at
            at += len(_OPEN)
