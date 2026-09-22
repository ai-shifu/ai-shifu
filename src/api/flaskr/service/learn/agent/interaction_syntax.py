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

`\?[` is left exactly as it is. The grammar treats it as text rather than an interaction, which
is how a lesson about the syntax shows the syntax.
"""

from __future__ import annotations

_OPEN = "?["
_CLOSE = "]"


class InteractionSyntaxFilter:
    """Pull whole `?[...]` spans out of streamed narration, remembering each one."""

    def __init__(self) -> None:
        """Start with nothing held and nothing seen."""
        self._held = ""
        self._inside = False
        # The last character already sent out. An opener is escaped by the character before it,
        # and that character may have left in an earlier chunk, so it has to be remembered.
        self._previous = ""
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
                self.spans.append(self._held[: end + 1])
                self._held = self._held[end + 1 :]
                self._inside = False
                continue
            start = self._find_open(self._held, self._previous)
            if start < 0:
                # Keep back a trailing `?`, which the next chunk may turn into an opener.
                keep = 1 if self._held.endswith("?") else 0
                if keep:
                    self._emit(out, self._held[:-1])
                    self._held = self._held[-1:]
                else:
                    self._emit(out, self._held)
                    self._held = ""
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

    def flush(self) -> str:
        """Release what is still held, because no more text is coming.

        An opener that never closed was never a span: it is text, and it goes out as text.
        """
        tail, self._held = self._held, ""
        self._inside = False
        return tail

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
