"""Recognize standalone text imitations of interact, never execute their attributes."""

from __future__ import annotations

import re

_OPEN = re.compile(r"""[ ]{0,3}<interact(?=$|[ \t\r\n/>"'])""")
_PARAMETER = re.compile(r"[ \t]*<parameter(?=$|[ \t\r\n/>])")
_CLOSE = re.compile(r"""</interact["']?[ \t]*>""")
_BLOCK_TAG = re.compile(
    r"""</?(?:parameter|interact)(?=[ \t\r\n/>"'])"""
    r"|</\uff5c\uff5cDSML\uff5c\uff5c[ \t]+parameter(?=[ \t>])"
)
# Longer than any block tag name, including the DSML parameter closer.
_TAG_PREFIX_LIMIT = 32
_FENCE = re.compile(r"[ ]{0,3}(`{3,}|~{3,})(.*)$")
INTERACTION_MARKUP_RETRY = (
    "You wrote an <interact ...> tag as text instead of calling a tool. "
    "No question was created and no learner answer was received. "
    "Call the actual `interact` tool for that unanswered question now. "
    "Do not repeat the tag, assume an answer, advance or call `finish`."
)


def _tag_end(text: str, start: int) -> int | None:
    """Find an unquoted tag terminator, tolerating the observed stray name quote."""
    quote = ""
    if text[start : start + 1] in ('"', "'") and text[start + 1 : start + 2] == ">":
        start += 1
    for at in range(start, len(text)):
        character = text[at]
        if quote:
            if character == quote:
                quote = ""
        elif character in ('"', "'"):
            quote = character
        elif character == ">":
            return at + 1
    return None


def authored_interaction_markup(script: str) -> frozenset[str]:
    """Preserve exact literal tag examples present in the author's documents.

    A multiline example keeps its following lines up to a blank line, so the
    complete authored example is exempt but a different generated body is not.
    """
    literals: set[str] = set()
    in_example = False
    for line in script.splitlines():
        if contains_interaction_markup(line, frozenset()):
            in_example = True
        elif not line.strip():
            in_example = False
        if in_example:
            literals.add(line.strip())
    return frozenset(literals)


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
        self._parameter_block = False
        self._in_parameter = False
        self._pending_tag = ""
        self._after_literal = False

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

    def settle(self) -> str:
        """Settle the last line at a part boundary; a rejected block stays open."""
        return self._settle()

    def flush(self) -> str:
        """End a response's protocol fragment without losing literal-code fences."""
        result = self._settle()
        self._parameter_block = False
        self._in_parameter = False
        self._pending_tag = ""
        self._after_literal = False
        return result

    def _could_be_control_line(self) -> bool:
        stripped = self._line.lstrip(" ")
        if self._parameter_block:
            return True
        if len(self._line) - len(stripped) > 3:
            return False
        if self._after_literal and (
            "<parameter".startswith(stripped) or stripped.startswith("<parameter")
        ):
            return True
        if not stripped:
            return True
        if "<interact".startswith(stripped):
            return True
        if stripped.startswith("<interact"):
            return _OPEN.match(self._line) is not None
        return stripped[0] in "`~" and all(c == stripped[0] for c in stripped)

    def _discard_block(self, text: str) -> str | None:
        """Return only text after a structural close, ignoring closes in parameters."""
        text = self._pending_tag + text
        self._pending_tag = ""
        at = 0
        while tag := _BLOCK_TAG.search(text, at):
            end = _tag_end(text, tag.end())
            if end is None:
                self._pending_tag = text[tag.start() :]
                return None
            token = tag.group()
            if "parameter" in token:
                if token.startswith("</"):
                    self._in_parameter = False
                elif not self._in_parameter:
                    self._in_parameter = not text[:end].endswith("/>")
            elif token.startswith("</") and not self._in_parameter:
                self._parameter_block = False
                return text[end:]
            at = end
        # A tag can be cut at a text-part boundary before its name is complete.
        # Keep only a tail short enough to be such a prefix, so a body is never held.
        start = text.rfind("<", at)
        if (
            start >= 0
            and len(text) - start <= _TAG_PREFIX_LIMIT
            and ">" not in text[start:]
        ):
            self._pending_tag = text[start:]
        return None

    def _settle(self) -> str:
        text, sent = self._line, self._sent
        self._line = ""
        self._sent = 0
        after_close = False
        while self._fence is None:
            if self._parameter_block:
                remainder = self._discard_block(text)
                if remainder is None or not remainder.strip():
                    return ""
                text, sent = remainder, 0
                after_close = True
            if text.strip() in self.literals:
                self._after_literal = True
                break
            if self._after_literal:
                self._after_literal = not text.strip()
                if _PARAMETER.match(text):
                    # The authored lines were shown; a generated body after them is not.
                    self.invalid = True
                    self._parameter_block = True
                    continue
            # Whitespace after a removed tag is not Markdown code indentation.
            start = len(text) - len(text.lstrip(" \t")) if after_close else 0
            opening = _OPEN.match(text, start)
            if opening is None:
                break
            end = _tag_end(text, opening.end())
            if end is None:
                self.invalid = True
                self._parameter_block = True
                self._pending_tag = text
                return ""
            suffix = text[end:].strip()
            self_closing = text[:end].endswith("/>")
            if not (
                self_closing
                or not suffix
                or _CLOSE.match(suffix)
                or _PARAMETER.match(suffix)
            ):
                break  # Nonempty inline examples are ordinary content.
            self.invalid = True
            if self_closing:
                return ""  # Do not advance on prose attached to an unexecuted call.
            self._parameter_block = True
            text, sent = text[end:], 0
        match = _FENCE.fullmatch(text.rstrip("\r\n"))
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
        return text[sent:]


def contains_interaction_markup(text: str, literals: frozenset[str]) -> bool:
    """Check the complete response with the same recognition as the stream filter."""
    filter_ = InteractionMarkupFilter(literals)
    filter_.feed(text)
    filter_.flush()
    return filter_.invalid
