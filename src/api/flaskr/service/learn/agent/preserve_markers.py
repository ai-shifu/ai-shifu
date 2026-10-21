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
from dataclasses import dataclass
from string import punctuation

from markdown_flow.formatter.patterns import block_html_open_re

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
_MAY_BE_FENCE = re.compile(r"^[ ]{0,3}[`~]|^[ \t]*!?=*[ \t]*$")
# The tail of an unfinished line that may still become a marker once more text arrives.
_PARTIAL_TAIL = re.compile(r"!?=*$")
_HTML_TAG_HEAD = re.compile(r"</?([a-zA-Z][a-zA-Z0-9:-]*)(?=[\s/>])")
_HTML_TAG_PREFIX = re.compile(r"</?[a-zA-Z][a-zA-Z0-9:-]*$")
_HTML_DOCTYPE_HEAD = re.compile(r"<!DOCTYPE(?=[\s>])", re.IGNORECASE)
_HTML_ROOT_HEAD = re.compile(r"<(?:html|body|svg)(?=[\s>/])", re.IGNORECASE)
# Raw-text and RCDATA bodies cannot open nested HTML elements. Only script/style
# contain code; other text-only elements still have prose markers removed.
_RAW_TEXT_END = {
    tag: re.compile(rf"</{tag}(?=[\s/>])", re.IGNORECASE)
    for tag in (
        "script",
        "style",
        "textarea",
        "title",
        "iframe",
        "xmp",
        "noembed",
        "noframes",
    )
}
_PROSE_SPECIAL = re.compile(r"[<`\\\[\]]")
_BACKTICKS = re.compile(r"`+")


def _run_end(text: str, start: int) -> int:
    """Find the end of a repeated Markdown delimiter or escape character."""
    end = start + 1
    while end < len(text) and text[end] == text[start]:
        end += 1
    return end


def _inline_boundary(text: str, start: int, scanned: int = 0) -> int:
    """Locate a paragraph or block boundary that ends an inline candidate."""
    # Inline syntax cannot cross a paragraph break or consume a code/HTML block. Revisit the previous
    # chunk's last line too: its opening tag may only now have become complete.
    newline = text.rfind("\n", start, start + scanned)
    if newline < 0:
        newline = text.find("\n", start)
    while newline >= 0:
        line_start = newline + 1
        newline = text.find("\n", line_start)
        raw_line = text[line_start : newline if newline >= 0 else None]
        line = _MARKERS.sub("", raw_line)
        candidate = line.lstrip(" \t")
        if (
            (newline >= 0 and not raw_line.strip(" \t"))
            or _CODE_FENCE_OPEN.match(raw_line)
            or _FENCE_LINE.match(raw_line)
            or block_html_open_re.match(line)
            or _HTML_ROOT_HEAD.match(candidate)
            or _HTML_DOCTYPE_HEAD.match(candidate)
            or candidate.startswith("<!--")
        ):
            return line_start
    return len(text)


def _code_span_end(
    text: str, start: int, scanned: int | None, *, final: bool
) -> tuple[int | None, int | None]:
    """Pair backticks; a None scan offset means a block forced an unmatched opener."""
    if scanned is None:
        return None, None
    opening_end = _run_end(text, start)
    width = opening_end - start
    boundary = _inline_boundary(text, start, scanned)
    for closing in _BACKTICKS.finditer(
        text, max(opening_end, start + scanned), boundary
    ):
        # The next chunk may extend this run; do not close it prematurely.
        if closing.end() == len(text) and not final:
            return None, closing.start() - start
        if closing.end() - closing.start() == width:
            return closing.end(), 0
    if boundary < len(text):
        # The caller replays unmatched source through the line/fence parser too.
        return None, None
    return None, len(text) - start


@dataclass
class _LinkSuffix:
    """Incremental progress through a link destination and optional title."""

    position: int = 1
    stage: str = "open"
    depth: int = 0
    closer: str = ""
    separated: bool = False
    reference: bool = False
    reference_end: int = 0


@dataclass
class _LinkLabel:
    """Images may contain links; a link cannot contain another active link."""

    image: bool
    active: bool = True
    contains_link: bool = False
    reference: bool = False
    content: bool = False


def _link_suffix_end(
    text: str, start: int, state: _LinkSuffix, *, final: bool
) -> tuple[int | None, int | None]:
    """Recognize link metadata without rescanning a long destination or title."""
    maximum = _inline_boundary(text, start, state.position)
    while start + state.position < maximum:
        pos = start + state.position
        char = text[pos]
        if state.stage in ("angle", "bare", "title") and char == "\\":
            if pos + 1 >= maximum:
                break
            following = text[pos + 1]
            if state.stage == "bare" and following in " \t\n":
                return None, None
            state.position += 2 if following in punctuation else 1
            continue
        if state.stage == "open":
            if char != (":" if state.reference else "("):
                return None, None
            state.position += 1
            state.stage = "leading"
        elif state.stage == "leading":
            if char in " \t\n":
                state.position += 1
            elif char == ")" and not state.reference:
                return pos + 1, 0
            elif char == "<":
                state.position += 1
                state.stage = "angle"
            else:
                state.stage = "bare"
        elif state.stage == "angle":
            if char in "<\n":
                return None, None
            state.position += 1
            if char == ">":
                state.stage = "destination-end"
        elif state.stage == "bare":
            if char in " \t\n":
                if state.depth:
                    return None, None
                state.stage = "destination-end"
            elif char == ")" and state.depth == 0:
                return (None, None) if state.reference else (pos + 1, 0)
            else:
                if char == "(":
                    state.depth += 1
                    if state.depth > 32:
                        return None, None
                elif char == ")":
                    state.depth -= 1
                elif ord(char) < 32 or ord(char) == 127:
                    return None, None
                state.position += 1
        elif state.stage == "destination-end":
            if state.reference and char == "\n":
                state.position += 1
                state.reference_end = state.position
                state.stage = "reference-title"
            elif char in " \t\n":
                state.separated = True
                state.position += 1
            elif char == ")" and not state.reference:
                return pos + 1, 0
            elif state.separated and char in "\"'(":
                state.closer = ")" if char == "(" else char
                state.position += 1
                state.stage = "title"
            else:
                return None, None
        elif state.stage == "reference-title":
            if char in " \t":
                state.position += 1
            elif char in "\"'(":
                state.closer = ")" if char == "(" else char
                state.position += 1
                state.stage = "title"
            else:
                return start + state.reference_end, 0
        elif state.stage == "title":
            if state.closer == ")" and char == "(":
                if state.reference_end:
                    return start + state.reference_end, 0
                return None, None
            state.position += 1
            if char == state.closer:
                state.stage = "title-end"
        elif state.reference and char == "\n":
            return pos + 1, 0
        elif char in " \t\n":
            state.position += 1
        else:
            if state.reference_end:
                return start + state.reference_end, 0
            return (pos + 1, 0) if char == ")" and not state.reference else (None, None)
    if state.reference and (final or maximum < len(text)):
        if state.stage == "title-end":
            return maximum, 0
        if state.reference_end:
            return start + state.reference_end, 0
        if state.stage in ("destination-end", "title-end") or (
            state.stage == "bare" and state.depth == 0
        ):
            return maximum, 0
    unfinished = state.position if not final and maximum == len(text) else None
    return None, unfinished


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
        self._inline_tail = ""
        self._inline_scanned: int | None = 0
        self._labels: list[_LinkLabel] = []
        self._image_pending = False
        self._link_suffix: _LinkSuffix | None = None
        self._replay_source: str | None = None
        self._backslashes = 0
        self._at_line_start = True
        self._line_indent = 0
        self._html_block_tag: str | None = None
        self._html_block_depth = 0

    def _emit(self, out: list[str], source: str, *, prose: bool = False) -> None:
        """Track the output line position, including HTML wrapped in removed markers."""
        emitted = _MARKERS.sub("", source) if prose else source
        out.append(emitted)
        if emitted.strip(" \t\n"):
            for label in self._labels:
                label.content = True
        if "\n" in emitted:
            last = emitted.rsplit("\n", 1)[1]
            self._at_line_start = not last.strip(" \t")
            self._line_indent = len(last.expandtabs(4)) if self._at_line_start else 0
        elif emitted.strip(" \t"):
            self._at_line_start = False
        elif self._at_line_start:
            self._line_indent += len(emitted.expandtabs(4))

    def feed(self, text: str) -> str:
        """Return `text` with markers removed, less any tail that might still become one."""
        if not text:
            return ""
        out: list[str] = []
        while True:
            self._line += text
            while "\n" in self._line:
                line, self._line = self._line.split("\n", 1)
                out.append(self._complete_line(line))
                self._released_some_of_line = False
                if self._inline_scanned is None or self._replay_source is not None:
                    break
            if self._inline_scanned is not None and self._replay_source is None:
                head, held = self._split_partial(self._line)
                self._line = held
                if head:
                    self._released_some_of_line = True
                    if self._fence:
                        self._emit(out, head)
                    else:
                        out.append(self._filter_html(head))
            if self._replay_source is not None:
                text = self._replay_source + self._line
                self._replay_source = None
                self._line = ""
                self._released_some_of_line = False
                continue
            if self._inline_scanned is not None or not self._inline_tail:
                break
            # A block boundary proves the opener is unmatched. Replay now so
            # streaming resumes, keeping any held marker/fence suffix last.
            pending, self._inline_tail = self._inline_tail, ""
            self._inline_scanned = 0
            opening_end = self._pending_opener_end(pending)
            self._emit(out, pending[:opening_end])
            text = pending[opening_end:] + self._line
            self._line = ""
            self._released_some_of_line = True
        return "".join(out)

    def flush(self) -> str:
        """Release what was held back, because no more text is coming."""
        out = [self._flush_buffer()]
        while self._inline_tail or self._replay_source is not None:
            if self._replay_source is not None:
                replay, self._replay_source = self._replay_source, None
                out.append(self.feed(replay))
                out.append(self._flush_buffer())
                continue
            # An unmatched opener is ordinary Markdown text. Replay its remainder
            # so real HTML, later code spans, and whole-line fences still work.
            pending, self._inline_tail = self._inline_tail, ""
            self._inline_scanned = 0
            opening_end = self._pending_opener_end(pending)
            self._emit(out, pending[:opening_end])
            self._released_some_of_line = True
            out.append(self.feed(pending[opening_end:]))
            out.append(self._flush_buffer())
        return "".join(out)

    def _pending_opener_end(self, pending: str) -> int:
        """Release one failed link bracket or an unmatched backtick run."""
        if pending.startswith("]"):
            label = self._labels.pop()
            if label.image and label.contains_link:
                self._disable_outer_links()
            self._link_suffix = None
            return 1
        return _run_end(pending, 0)

    def _disable_outer_links(self) -> None:
        """Stop nested links at the nearest image alt label."""
        for label in reversed(self._labels):
            if label.image:
                label.contains_link = True
                break
            label.active = False

    def _flush_buffer(self) -> str:
        """Finish buffered source, allowing a code span to close at end of stream."""
        tail, self._line = self._line, ""
        self._released_some_of_line = False
        # A fragment that never became a marker is text, and is shown as it is.
        out = tail if self._fence else self._filter_html(tail, final=True)
        # An unfinished tag is still source text, not a MarkdownFlow marker.
        html_tail, self._html_tail = self._html_tail, ""
        return out + html_tail

    def _complete_line(self, line: str) -> str:
        whole_line = not self._released_some_of_line
        if self._fence is not None:
            if whole_line and self._closes_fence(line):
                self._fence = None
            self._at_line_start = True
            self._line_indent = 0
            return line + "\n"
        in_literal = (
            self._raw_tag is not None
            or self._html_block_tag is not None
            or bool(self._html_tail or self._inline_tail)
        )
        if whole_line and not in_literal and not line.strip(" \t"):
            self._labels.clear()
        if whole_line and not in_literal:
            opening = _CODE_FENCE_OPEN.match(line)
            if opening:
                self._labels.clear()
                run = opening.group(1)
                self._fence = (run[0], len(run))
                return line + "\n"
        if whole_line and not in_literal and _FENCE_LINE.match(line):
            # The fence line itself: not content. Its newline goes too, or every fenced block
            # would gain a blank line.
            self._labels.clear()
            return ""
        return self._filter_html(line + "\n")

    def _filter_html(self, text: str, *, final: bool = False) -> str:
        """Strip prose markers while preserving actual HTML and Markdown code spans."""
        text = self._inline_tail + self._html_tail + text
        self._html_tail = ""
        self._inline_tail = ""
        out: list[str] = []
        index = 0
        while index < len(text):
            if self._raw_tag is not None:
                prose = self._raw_tag not in ("script", "style")
                match = _RAW_TEXT_END[self._raw_tag].search(text, index)
                if match is None:
                    # Keep only a possible closing-tag prefix; stream all other code.
                    last_lt = text.rfind("<", index)
                    closer = f"</{self._raw_tag}"
                    if last_lt >= index and closer.startswith(text[last_lt:].lower()):
                        self._emit(out, text[index:last_lt], prose=prose)
                        self._html_tail = text[last_lt:]
                    else:
                        self._emit(out, text[index:], prose=prose)
                    break
                end = _tag_end(text, match.end())
                if end is None:
                    self._emit(out, text[index : match.start()], prose=prose)
                    self._html_tail = text[match.start() :]
                    break
                self._emit(out, text[index : match.start()], prose=prose)
                self._emit(out, text[match.start() : end])
                self._raw_tag = None
                index = end
                continue

            special = _PROSE_SPECIAL.search(text, index)
            if special is None:
                tail = text[index:]
                self._image_pending = tail.endswith("!") and (
                    len(tail) > 1 or self._backslashes % 2 == 0
                )
                self._emit(out, text[index:], prose=True)
                self._backslashes = 0
                break
            start = special.start()
            prefix = text[index:start]
            if prefix:
                self._image_pending = prefix.endswith("!") and (
                    len(prefix) > 1 or self._backslashes % 2 == 0
                )
            self._emit(out, text[index:start], prose=True)
            if start > index:
                self._backslashes = 0
            char = text[start]
            if self._html_block_tag is not None and char in ("\\", "`", "[", "]", "!"):
                # Markdown escapes/code spans do not apply inside an HTML visual.
                end = _run_end(text, start)
                self._emit(out, text[start:end])
                index = end
                continue
            if char == "\\":
                self._image_pending = False
                end = _run_end(text, start)
                self._emit(out, text[start:end])
                self._backslashes += end - start
                index = end
                continue
            escaped = self._backslashes % 2 == 1
            self._backslashes = 0
            if escaped:
                self._image_pending = False
                self._emit(out, char)
                index = start + 1
                continue
            if char == "[":
                label = _LinkLabel(
                    image=self._image_pending,
                    reference=(
                        not self._labels
                        and not self._image_pending
                        and self._at_line_start
                        and self._line_indent <= 3
                    ),
                )
                self._image_pending = False
                self._emit(out, char)
                self._labels.append(label)
                index = start + 1
                continue
            self._image_pending = False
            if char == "]":
                if not self._labels or not self._labels[-1].active:
                    if self._labels:
                        self._labels.pop()
                    self._emit(out, char)
                    index = start + 1
                    continue
                if self._link_suffix is None:
                    self._link_suffix = _LinkSuffix()
                if (
                    self._link_suffix.stage == "open"
                    and self._labels[-1].reference
                    and self._labels[-1].content
                    and text[start + 1 : start + 2] == ":"
                ):
                    self._link_suffix.reference = True
                end, self._inline_scanned = _link_suffix_end(
                    text, start, self._link_suffix, final=final
                )
                if end is None:
                    self._inline_tail = text[start:]
                    break
                label = self._labels.pop()
                if not label.image:
                    self._disable_outer_links()
                reference = self._link_suffix.reference
                self._link_suffix = None
                self._emit(out, text[start:end])
                if reference and end < len(text):
                    self._replay_source = text[end:]
                    break
                index = end
                continue
            if char == "`":
                end, self._inline_scanned = _code_span_end(
                    text, start, self._inline_scanned, final=final
                )
                if end is None:
                    self._inline_tail = text[start:]
                    break
                self._emit(out, text[start:end])
                index = end
                continue
            fragment = text[start:]
            if fragment.startswith("<!--"):
                end = text.find("-->", start + 4)
                end = end + 3 if end >= 0 else None
                match = None
                tag = None
            elif "<!DOCTYPE".startswith(fragment.upper()) or _HTML_DOCTYPE_HEAD.match(
                fragment
            ):
                end = _tag_end(text, start + 2)
                match = None
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
                    self._emit(out, "<")
                    index = start + 1
                    continue
                end = _tag_end(text, match.end())
                tag = match.group(1).lower() if not fragment.startswith("</") else None
            if end is None:
                self._html_tail = fragment
                break
            if match is not None:
                name = match.group(1).lower()
                self_closing_svg = tag == "svg" and text[start:end].endswith("/>")
                if self._html_block_tag == name and not self_closing_svg:
                    self._html_block_depth += -1 if tag is None else 1
                    if self._html_block_depth == 0:
                        self._html_block_tag = None
                elif (
                    self._html_block_tag is None
                    and not self_closing_svg
                    and self._at_line_start
                    and tag not in _RAW_TEXT_END
                    and tag is not None
                    and (
                        block_html_open_re.match(fragment)
                        or tag in ("html", "body", "svg")
                    )
                ):
                    # Use the same block tags as the downstream StreamFormatter.
                    self._html_block_tag = tag
                    self._html_block_depth = 1
                    self._labels.clear()
            leading_metadata = match is None and self._at_line_start
            self._emit(out, text[start:end])
            if leading_metadata:
                # Leading HTML metadata may precede the visual's root on this line.
                self._at_line_start = True
            if tag in _RAW_TEXT_END:
                # Self-closing syntax does not close these non-void HTML text elements.
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
