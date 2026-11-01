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

from markdownflow.engine.stream_marker_context import (
    compact_marker_context,
    pending_autolink_is_primary,
    pending_literal_context,
)
from markdownflow.syntax.constants import COMPILED_INLINE_HTML_REGEX
from markdownflow.syntax.parser.document_blocks import DocumentBlocks
from markdownflow.syntax.parser.marker_context import (
    analyze_marker_context,
    marker_syntax_source,
)
from markdownflow.syntax.variable_names import (
    find_interaction_end,
    read_variable_marker,
)

_OPEN = "?["
_FENCE_OPEN = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})", re.MULTILINE)
# A block closes only on a line of its own fence character, at least as long, with nothing after
# it but whitespace. `` ```not-a-close `` opens nothing and closes nothing; it is code.
_FENCE_CLOSE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})[ \t]*$")
# A line still arriving that may yet become one.
_MAY_BE_FENCE = re.compile(r"^[ ]{0,3}[`~]", re.MULTILINE)
_LINE_BREAK = re.compile(r"\r\n|\r(?=.)|\n")
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
        # A backslash when the text already sent out ends in an odd run of backslashes, else
        # empty. An opener is escaped by an odd run before it, and that run may have left in an
        # earlier chunk, so its parity has to be remembered.
        self._previous = ""
        # Classify the emitted line prefix, so an indent from an earlier chunk
        # still counts without retaining the narration on that line.
        self._line_so_far = ""
        # Keep unfinished syntax as small continuation witnesses. Emitted prose
        # and attribute/title values never need to be retained or rescanned.
        self._context_prefix = ""
        self._context_label_counts: dict[int, int] = {}
        self._opaque_prefix_until = 0
        # A question inside a raw marker cannot be classified until a viable
        # enclosing literal closes or fails. Buffer its possible output in chunks,
        # keeping only bounded lexical state for each new arrival.
        self._pending_literal: str | None = None
        self._pending_literal_chunks: list[str] = []
        self._raw_marker_active = False
        self._raw_marker_tail = ""
        self._raw_marker_boundary: tuple[str, str] | None = None
        self.spans: list[str] = []

    def feed(self, text: str) -> str:
        """Return `text` with any complete span removed, holding back an unfinished one."""
        if not text:
            return ""
        if self._raw_marker_active:
            out: list[str] = []
            closing = (self._raw_marker_tail + text).find("}}")
            cut = len(text) if closing < 0 else closing + 2 - len(self._raw_marker_tail)
            self._emit(out, text[:cut])
            if closing < 0:
                self._raw_marker_tail = "}" if text.endswith("}") else ""
                return "".join(out)
            self._raw_marker_active = False
            self._raw_marker_tail = ""
            self._raw_marker_boundary = None
            self._held += text[cut:]
            return "".join(out) + self._drain()
        if self._pending_literal is not None:
            self._pending_literal_chunks.append(text)
            pending = pending_literal_context(self._pending_literal + text)
            witness = pending[1] if pending is not None else None
            if witness is not None:
                self._pending_literal = witness
                return ""
            self._pending_literal = None
            text = "".join(self._pending_literal_chunks)
            self._pending_literal_chunks.clear()
        self._held += text
        return self._drain()

    def _drain(self, *, final: bool = False) -> str:
        """Classify held source, replaying an unresolved literal candidate at EOF."""
        out: list[str] = []
        while self._held:
            if self._inside:

                def marker_end(at: int) -> int | None:
                    marker = read_variable_marker(self._held, at)
                    return marker.end if marker is not None else None

                limit, closed = DocumentBlocks(
                    self._held, COMPILED_INLINE_HTML_REGEX
                ).interaction_limit(2, marker_end, final=False)
                if (
                    not closed
                    and limit < len(self._held)
                    and _LINE_BREAK.search(self._held, limit) is not None
                ):
                    self._emit(out, self._held[:limit])
                    self._held = self._held[limit:]
                    self._inside = False
                    continue
                end = find_interaction_end(self._held, 2)
                if end < 0:
                    return "".join(out)
                if len(self._held) == end + 1:
                    # The character after the bracket decides whether this is a question or a
                    # link, and it has not arrived yet.
                    return "".join(out)
                if self._held[end + 1] == "(":
                    self._emit(out, self._held[: end + 2])
                    self._held = self._held[end + 2 :]
                    self._inside = False
                    continue
                self.spans.append(self._held[: end + 1])
                self._held = self._held[end + 1 :]
                self._inside = False
                continue
            fence = self._next_fence_line(self._held, final=final)
            start, pending_literal = (
                (-1, None)
                if self._fence is not None
                else self._find_open(self._held, self._previous, final=final)
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
                self._context_prefix = ""
                self._context_label_counts.clear()
                self._held = self._held[line_end:]
                continue
            if start >= 0 and self._in_indented_code(self._held, start):
                # Four spaces of indent is a code block of its own in Markdown, and the browser
                # renders its contents as code rather than as controls. Left as text.
                line_break = _LINE_BREAK.search(self._held, start)
                if line_break is None:
                    return "".join(out)
                self._emit(out, self._held[: line_break.end()])
                self._held = self._held[line_break.end() :]
                continue
            if start < 0 and self._fence is not None:
                # Inside a code block with no fence in sight: all text, but a line that may yet
                # close the block waits for its end.
                cut = max(
                    (match.end() for match in _LINE_BREAK.finditer(self._held)),
                    default=0,
                )
                self._emit(out, self._held[:cut])
                self._held = self._held[cut:]
                return "".join(out)
            if start < 0:
                unclosed = self._unclosed_marker_start(self._held, final=final)
                if unclosed >= 0:
                    if final or self._raw_marker_owns_tail(self._held, unclosed):
                        # Settled raw ownership cannot be changed by later name
                        # characters. Emit them and retain only its closing-pair
                        # boundary, rather than rescanning or copying the name.
                        self._emit(out, self._held[:unclosed])
                        self._held = self._held[unclosed:]
                        self._raw_marker_boundary = (
                            self._previous,
                            self._line_so_far,
                        )
                        self._raw_marker_active = True
                        self._raw_marker_tail = "}" if self._held.endswith("}") else ""
                        self._emit(out, self._held)
                        self._held = ""
                        return "".join(out)
                    self._emit(out, self._held[:unclosed])
                    self._held = self._held[unclosed:]
                    return "".join(out)
                if self._held.endswith(("`", "$", "~")):
                    # Do not commit the width of a delimiter run until its next
                    # character arrives; a network cut may split that run.
                    cut = len(self._held.rstrip(self._held[-1]))
                    self._emit(out, self._held[:cut])
                    self._held = self._held[cut:]
                    return "".join(out)
                # A trailing `?` waits for the next chunk, which may turn it into an opener.
                # Without this the same output is handled differently depending on where the
                # network split it, which is the one thing a filter like this must not do. It
                # costs nothing a learner can see: consecutive pieces of a turn's text are
                # written as one element, so a passage released in two parts still arrives whole.
                if self._held.endswith(("?", "{", "\r")):
                    self._emit(out, self._held[:-1])
                    self._held = self._held[-1:]
                else:
                    self._emit(out, self._held)
                    self._held = ""
                return "".join(out)
            if pending_literal is not None:
                self._emit(out, self._held[:start])
                self._held = self._held[start:]
                self._pending_literal = pending_literal
                return "".join(out)
            close = find_interaction_end(self._held, start + 2)
            if close >= 0 and self._held[close + 1 : close + 2] == "(":
                # `?[text](link)` is a link, not a question: the grammar's own pattern ends in a
                # negative lookahead for the bracket, and a lesson may well write one.
                self._emit(out, self._held[: close + 2])
                self._held = self._held[close + 2 :]
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
        if self._fence is None:
            counts: dict[int, int] = {}
            self._context_prefix = compact_marker_context(
                self._context_prefix + text,
                label_counts=self._context_label_counts,
                counts_out=counts,
                lookahead=self._held[len(text) : len(text) + 1],
            )
            self._context_label_counts = counts
        else:
            self._context_prefix = ""
            self._context_label_counts.clear()
        out.append(text)
        run = len(text) - len(text.rstrip("\\"))
        odd = run % 2 == 1
        if run == len(text) and self._previous == "\\":
            # Only backslashes: they extend the run carried from earlier chunks.
            odd = not odd
        self._previous = "\\" if odd else ""
        cut = max(text.rfind("\n"), text.rfind("\r"))
        line = text[cut + 1 :] if cut >= 0 else self._line_so_far + text
        self._line_so_far = line[:4] if not line.strip(" \t\r") else "x"

    def flush(self) -> str:
        """Release what is still held, because no more text is coming.

        A span waiting only to find out whether a bracket follows it is settled here: nothing
        follows it, so it is a question and not a link. An opener that never closed was never a
        span at all -- it is text, and it goes out as text.
        """
        released = ""
        if self._pending_literal is not None:
            self._held += "".join(self._pending_literal_chunks)
            self._pending_literal_chunks.clear()
            self._pending_literal = None
            released = self._drain(final=True)
        if self._inside and find_interaction_end(self._held, 2) == len(self._held) - 1:
            self.spans.append(self._held)
            self._held = ""
        tail, self._held = self._held, ""
        self._inside = False
        self._fence = None
        self._context_prefix = ""
        self._context_label_counts.clear()
        if self._raw_marker_active and self._raw_marker_boundary is not None:
            # Before incremental emission, an unfinished raw name left these
            # boundary witnesses at the prose preceding its opener on flush.
            self._previous, self._line_so_far = self._raw_marker_boundary
        self._raw_marker_active = False
        self._raw_marker_tail = ""
        self._raw_marker_boundary = None
        return released + tail

    def _marker_scan_text(
        self,
        text: str,
        *,
        container_fences: bool = False,
        final: bool = False,
        provisional_markers: list[tuple[int, int, str]] | None = None,
    ) -> str:
        """Hide code/escaped marker openers without changing opaque name contents."""
        prefix = self._context_prefix
        source = prefix + text
        context = analyze_marker_context(
            source, final=final, label_counts=self._context_label_counts
        )
        provisional = context.pending_autolink_start
        if provisional is not None and not pending_autolink_is_primary(
            source, provisional
        ):
            provisional = None
        reference_markers: list[tuple[int, int]] = []
        pending = (
            pending_literal_context(source, reference_markers=reference_markers)
            if not final and provisional_markers is not None
            else None
        )
        owned = [
            marker
            for marker in context.markers
            if marker.start < len(prefix) < marker.end
            and not any(start <= marker.start < end for start, end in context.literals)
            and (provisional is None or marker.start < provisional)
            and (pending is None or marker.start < pending[0])
        ]
        self._opaque_prefix_until = max(
            (marker.end - len(prefix) for marker in owned), default=0
        )
        scanned = marker_syntax_source(source, context)
        if owned:
            end = len(prefix) + self._opaque_prefix_until
            scanned = (
                scanned[: len(prefix)]
                + "\x00" * self._opaque_prefix_until
                + scanned[end:]
            )
        if provisional is not None:
            # A viable angle link may still become ordinary text in a later
            # chunk. Its witness retains any raw opener for that fallback.
            scanned = scanned[:provisional] + scanned[provisional:].replace("{", "\x00")
        if pending is not None and provisional_markers is not None:
            start, witness = pending
            provisional_markers.extend(
                (marker.start - len(prefix), marker.end - len(prefix), witness)
                for marker in context.markers
                if marker.start >= start
                and not any(
                    opening <= marker.start < end for opening, end in context.literals
                )
            )
            # A reference definition accepted at EOF can still fail when its
            # physical line continues. Its raw markers retain that ambiguity
            # even when the native prefix currently classifies them as literal.
            provisional_markers.extend(
                (opening - len(prefix), end - len(prefix), witness)
                for opening, end in reference_markers
            )
            # Find the potentially real question without committing the marker's
            # ownership before its enclosing native literal has been decided.
            characters = list(scanned)
            for opening, _, _ in provisional_markers:
                at = max(0, len(prefix) + opening)
                characters[at : at + 2] = "\x00" * 2
            scanned = "".join(characters)
        if container_fences:
            characters = list(scanned)
            for start, end in context.container_fences:
                for at in range(start, end):
                    if characters[at] in "`~":
                        characters[at] = "\x00"
            scanned = "".join(characters)
        return scanned[len(prefix) :]

    def _next_fence_line(
        self, text: str, *, final: bool = False
    ) -> tuple[int, int | None] | None:
        """Where the next fence line starts in `text`, and where it ends.

        The end is None when the line has not finished arriving, which is the caller's cue to
        wait for it rather than let it out as ordinary text. Fences are line-based, so this
        looks at every line start in what is held, not only at the first.
        """
        scan_text = text
        reference_wait: int | None = None
        if self._fence is None:
            source = self._context_prefix + text
            context = analyze_marker_context(
                source, final=final, label_counts=self._context_label_counts
            )
            if any(
                not marker.complete
                and marker.start < len(self._context_prefix)
                and not any(
                    start <= marker.start < end for start, end in context.literals
                )
                and (
                    context.pending_autolink_start is None
                    or marker.start < context.pending_autolink_start
                )
                for marker in context.markers
            ):
                return None
            if context.pending_reference_body_start is not None:
                opening = source.find("{{", context.pending_reference_body_start)
                while opening >= 0:
                    marker = read_variable_marker(source, opening)
                    if marker is None:
                        if _LINE_BREAK.search(source, opening) is None:
                            # A title's closing quote is provisional until its line ends.
                            # An earlier native fence still takes precedence.
                            reference_wait = max(0, opening - len(self._context_prefix))
                        break
                    opening = source.find("{{", marker.end)
            if (
                context.pending_block_start is not None
                and context.pending_container_fence is not None
                and _LINE_BREAK.search(source, context.pending_block_start) is None
            ):
                # A later info-string backtick can still invalidate this opening.
                return (0, None)
            # A raw marker is one opaque token, even when its name is invalid or
            # its closing pair has not arrived. Padding may contain newlines, so
            # searching the original text would mistake its contents for fences.
            # Keep offsets intact for the original line/stream state below.
            parts: list[str] = []
            at = 0
            marker_scan = self._marker_scan_text(
                text, container_fences=True, final=final
            )
            while (start := marker_scan.find("{{", at)) >= 0:
                marker = read_variable_marker(text, start)
                end = marker.end if marker is not None else len(text)
                parts.extend((marker_scan[at:start], "\x00" * (end - start)))
                at = end
                if marker is None:
                    break
            parts.append(marker_scan[at:])
            scan_text = "".join(parts)
        # Keep offsets while making all physical endings visible to multiline anchors.
        line_source = scan_text.replace("\r\n", "\x00\n").replace("\r", "\n")
        for match in _FENCE_OPEN.finditer(line_source):
            if not self._at_line_start(text, match.start()):
                continue
            if reference_wait is not None and reference_wait <= match.start():
                return (reference_wait, None)
            line_break = _LINE_BREAK.search(text, match.start())
            if line_break is None:
                return (match.start(), None)
            if self._fence is not None and not self._closes_here(
                text[match.start() : line_break.start()]
            ):
                # Inside a block, a line that is not a valid closer is part of the code.
                continue
            return (match.start(), line_break.end())
        for partial in _MAY_BE_FENCE.finditer(line_source):
            if (
                self._at_line_start(text, partial.start())
                and _LINE_BREAK.search(text, partial.start()) is None
            ):
                if reference_wait is not None and reference_wait <= partial.start():
                    return (reference_wait, None)
                return (partial.start(), None)
        return (reference_wait, None) if reference_wait is not None else None

    def _in_indented_code(self, text: str, at: int) -> bool:
        """Whether the line `at` sits on is indented far enough to be a code block."""
        before = text[:at]
        cut = max(before.rfind("\n"), before.rfind("\r"))
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
            line = before[max(before.rfind("\n"), before.rfind("\r")) + 1 :]
        else:
            line = self._line_so_far
        # A fence may be indented by up to three spaces, so what stands before it on its line
        # counts as nothing only when it is that indent. The indent may have left in an earlier
        # chunk, which is why this is tracked rather than read off the character before.
        return line == "" or (len(line) <= 3 and line.isspace() and "\n" not in line)

    @staticmethod
    def _closes_here(line: str) -> bool:
        """Whether this line is a valid closing fence, rather than code that starts like one."""
        return _FENCE_CLOSE.match(line.rstrip("\r\n")) is not None

    def _toggle_fence(self, line: str) -> None:
        """Open a code block on this fence line, or close the one it ends."""
        match = _FENCE_OPEN.match(line)
        if match is None:
            return
        run = match.group(1)
        if self._fence is None:
            self._fence = (run[0], len(run))
        elif (
            _FENCE_CLOSE.match(line.rstrip("\r\n")) is not None
            and run[0] == self._fence[0]
            and len(run) >= self._fence[1]
        ):
            self._fence = None

    def _find_open(
        self, text: str, previous: str, *, final: bool = False
    ) -> tuple[int, str | None]:
        """Locate the next `?[` and any literal state delaying its classification.

        `previous` is a backslash when the text before `text` ends in an odd run of backslashes,
        which decides an opener preceded only by backslashes in what is left to scan.
        """
        provisional_markers: list[tuple[int, int, str]] = []
        marker_scan = self._marker_scan_text(
            text, final=final, provisional_markers=provisional_markers
        )
        at = min(len(text), self._opaque_prefix_until)
        while at < len(text):
            if marker_scan.startswith("{{", at):
                marker = read_variable_marker(text, at)
                if marker is None:
                    return -1, None
                at = marker.end
            elif text.startswith(_OPEN, at):
                before = at
                while before and text[before - 1] == "\\":
                    before -= 1
                run = at - before + int(not before and previous == "\\")
                if run % 2 == 0:
                    witness = next(
                        (
                            value
                            for start, end, value in provisional_markers
                            if start <= at < end
                        ),
                        None,
                    )
                    return at, witness
                at += len(_OPEN)
            else:
                at += 1
        return -1, None

    def _unclosed_marker_start(self, text: str, *, final: bool = False) -> int:
        marker_scan = self._marker_scan_text(text, final=final)
        at = 0
        while (start := marker_scan.find("{{", at)) >= 0:
            marker = read_variable_marker(text, start)
            if marker is None:
                return start
            at = marker.end
        return -1

    def _raw_marker_owns_tail(self, text: str, start: int) -> bool:
        """Whether no earlier unfinished literal can still claim this marker."""
        source = self._context_prefix + text
        opening = len(self._context_prefix) + start
        context = analyze_marker_context(
            source, final=False, label_counts=self._context_label_counts
        )
        if any(
            at < opening
            for at, _ in (*context.unmatched_backticks, *context.unmatched_math)
        ):
            return False
        pending_blocks = [context.pending_block_start]
        if context.pending_block_steps or context.pending_raw_html_tag is not None:
            # A container marker such as '>' is source padding, rather than an
            # HTML terminator. Keep the document parser's projected block state.
            pending_blocks.append(context.pending_html_start)
        if any(at is not None and at < opening for at in pending_blocks):
            return False
        pending = pending_literal_context(source)
        return pending is None or pending[0] >= opening
