"""Recognize standalone text imitations of interact, never execute their attributes."""

from __future__ import annotations

import re

_TAG = re.compile(r"[ ]{0,3}<interact\b[^<\n]*?/?>[ \t]*$")
_FENCE = re.compile(r"[ ]{0,3}(`{3,}|~{3,})(.*)$")
INTERACTION_MARKUP_RETRY = (
    "You wrote an <interact ...> tag as text instead of calling a tool. "
    "No question was created and no learner answer was received. "
    "Call the actual `interact` tool for that unanswered question now. "
    "Do not repeat the tag, assume an answer, advance or call `finish`."
)


def authored_interaction_markup(script: str) -> frozenset[str]:
    """Preserve exact literal tag examples present in the author's documents."""
    return frozenset(
        line.strip() for line in script.splitlines() if _TAG.fullmatch(line)
    )


class InteractionMarkupFilter:
    """Hold only possible tag/fence lines; ordinary prose continues streaming.

    Recognition is deliberately limited to complete single-line tags at a Markdown
    line start. Inline examples, four-space code and fenced blocks are untouched.
    No attributes are parsed into interactions, variables or memory writes.
    """

    def __init__(self, literals: frozenset[str] = frozenset()) -> None:
        """Bind authored literal exceptions and start outside a Markdown fence."""
        self.literals = literals
        self.invalid = False
        self._line = ""
        self._sent = 0
        self._fence: str | None = None

    def feed(self, text: str) -> str:
        """Return display text while retaining a potentially invalid tag line."""
        out: list[str] = []
        for part in text.splitlines(keepends=True):
            self._line += part
            if self._line.endswith("\n"):
                out.append(self._settle())
            elif self._fence is not None or not self._could_be_control_line():
                out.append(self._line[self._sent :])
                self._sent = len(self._line)
        return "".join(out)

    def flush(self) -> str:
        """Settle the last line at a model-response boundary without losing fences."""
        return self._settle()

    def _could_be_control_line(self) -> bool:
        stripped = self._line.lstrip(" ")
        if len(self._line) - len(stripped) > 3:
            return False
        if not stripped:
            return True
        if "<interact".startswith(stripped):
            return True
        if stripped.startswith("<interact"):
            return len(stripped) == 9 or stripped[9] in " \t/>"
        return stripped[0] in "`~" and all(c == stripped[0] for c in stripped)

    def _settle(self) -> str:
        line = self._line.rstrip("\r\n")
        invalid = (
            self._fence is None
            and _TAG.fullmatch(line) is not None
            and line.strip() not in self.literals
        )
        if invalid:
            self.invalid = True
        result = "" if invalid else self._line[self._sent :]
        match = _FENCE.fullmatch(line)
        if match:
            run, suffix = match.groups()
            if self._fence is None:
                self._fence = run
            elif (
                run[0] == self._fence[0]
                and len(run) >= len(self._fence)
                and not suffix.strip()
            ):
                self._fence = None
        self._line = ""
        self._sent = 0
        return result


def contains_interaction_markup(text: str, literals: frozenset[str]) -> bool:
    """Check the complete response with the same recognition as the stream filter."""
    filter_ = InteractionMarkupFilter(literals)
    filter_.feed(text)
    filter_.flush()
    return filter_.invalid
