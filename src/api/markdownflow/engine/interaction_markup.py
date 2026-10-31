"""Recognize standalone text imitations of interact, never execute their attributes."""

from __future__ import annotations

import re

_OPEN = re.compile(
    r"""[ ]{0,3}<interact(?=[ \t/>"'])(?:["'](?=>))?"""
    r"""(?:[^<>"'\n]|"[^"\n]*"|'[^'\n]*')*"""
    r"/?>"
)
_INCOMPLETE = re.compile(r"""[ ]{0,3}<interact(?=$|[ \t/"'])[^<>]*$""")
_PARAMETER = re.compile(r"[ \t]*<parameter(?=[ \t/>])")
_CLOSE = re.compile(r"""</interact["']?[ \t]*>""")
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
        line.strip()
        for line in script.splitlines()
        if contains_interaction_markup(line, frozenset())
    )


class InteractionMarkupFilter:
    """Hold only possible tag/fence lines; ordinary prose continues streaming.

    Standalone tags, malformed or unfinished openers, and their parameter bodies
    are refused at a Markdown line start. Inline examples, four-space code and
    fenced blocks are untouched. Parameter bodies are discarded through their
    closing tag or the response boundary, never accumulated as a whole.
    No attributes are parsed into interactions, variables or memory writes.
    """

    def __init__(self, literals: frozenset[str] = frozenset()) -> None:
        """Bind authored literal exceptions and start outside a Markdown fence."""
        self.literals = literals
        self.invalid = False
        self._line = ""
        self._sent = 0
        self._fence: str | None = None
        self._after_open = False
        self._parameter_block = False

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
        """End a response's protocol fragment without losing literal-code fences."""
        result = self._settle()
        self._after_open = False
        self._parameter_block = False
        return result

    def _could_be_control_line(self) -> bool:
        stripped = self._line.lstrip(" ")
        if self._parameter_block:
            return True
        if self._after_open:
            continuation = self._line.lstrip(" \t")
            if any(
                prefix.startswith(continuation) or continuation.startswith(prefix)
                for prefix in ("<parameter", "</interact")
            ):
                return True
        if len(self._line) - len(stripped) > 3:
            return False
        if not stripped:
            return True
        if "<interact".startswith(stripped):
            return True
        if stripped.startswith("<interact"):
            return len(stripped) == 9 or stripped[9] in " \t/>\"'"
        return stripped[0] in "`~" and all(c == stripped[0] for c in stripped)

    def _settle(self) -> str:
        line = self._line.rstrip("\r\n")
        result = self._line[self._sent :]
        suppressed = False
        if self._fence is None:
            opening = _OPEN.match(line)
            suffix = line[opening.end() :].strip() if opening else ""
            parameters = _PARAMETER.match(suffix) if opening else None
            invalid = line.strip() not in self.literals and (
                (
                    opening is not None
                    and (
                        not suffix
                        or _CLOSE.fullmatch(suffix) is not None
                        or parameters is not None
                    )
                )
                or _INCOMPLETE.fullmatch(line) is not None
            )
            if self._parameter_block:
                suppressed = True
            elif self._after_open and (
                _PARAMETER.match(line.lstrip()) or _CLOSE.fullmatch(line.strip())
            ):
                self._parameter_block = True
                suppressed = True
            elif invalid:
                self.invalid = True
                self._parameter_block = opening is None or bool(parameters)
                self._after_open = bool(
                    opening
                    and not opening.group().endswith("/>")
                    and not _CLOSE.fullmatch(suffix)
                )
                suppressed = True
            elif line.strip():
                self._after_open = False
        if suppressed:
            result = ""
            # A quoted argument may contain a closing-tag example; only the body ends here.
            body_start = opening.end() if opening and invalid else 0
            if closing := _CLOSE.search(self._line, body_start):
                result = self._line[closing.end() :]
                # A standalone closing tag consumes its newline just like an opener.
                if not result.strip():
                    result = ""
                self._parameter_block = False
                self._after_open = False
        match = _FENCE.fullmatch(line)
        if match and not suppressed:
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
