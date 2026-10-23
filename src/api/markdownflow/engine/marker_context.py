"""Document-stage marker boundaries without changing the raw name grammar."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from markdown_it.common.html_re import HTML_TAG_RE

from .variable_names import normalize_variable_name

_BACKTICK_RUN = re.compile(r"`+")
# Inline code belongs to one paragraph and cannot absorb a later fenced block.
_INLINE_CODE_BREAK = re.compile(
    r"^[ \t]*\r?$|^[ ]{0,3}(?:`{3,}[^`\r\n]*|~{3,}[^\r\n]*)\r?$", re.MULTILINE
)
# markdown-it anchors its public pattern for a substring. Drop only that anchor
# so matching at an existing source offset does not copy the remaining document.
_INLINE_HTML = re.compile(HTML_TAG_RE.pattern.removeprefix("^"))
_HTML_PREFIX = re.compile(r"<(?:/?[A-Za-z]|[!?])")
_LINE_END = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")
_LINE_END_CHARS = "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"


@dataclass(frozen=True)
class ContextMarker:
    """A complete marker or an opaque, genuinely unfinished document tail."""

    start: int
    end: int
    raw_name: str
    name: str | None
    complete: bool = True


@dataclass
class MarkerContext:
    """Source offsets shared by collection, substitution and interaction scanning."""

    markers: list[ContextMarker] = field(default_factory=list)
    literals: list[tuple[int, int]] = field(default_factory=list)
    escaped_openers: list[int] = field(default_factory=list)
    fences: list[tuple[int, int]] = field(default_factory=list)
    unmatched_backticks: list[tuple[int, str]] = field(default_factory=list)
    pending_html_start: int | None = None


def _escaped(text: str, at: int) -> bool:
    before = at
    while before and text[before - 1] == "\\":
        before -= 1
    return (at - before) % 2 == 1


def _literal_markers(text: str, start: int, end: int) -> list[ContextMarker]:
    """Keep old complete literal references, but never read beyond their region."""
    markers: list[ContextMarker] = []
    while (start := text.find("{{", start, end)) >= 0:
        close = text.find("}}", start + 2, end)
        if close < 0:
            break
        raw = text[start + 2 : close]
        markers.append(
            ContextMarker(start, close + 2, raw, normalize_variable_name(raw))
        )
        start = close + 2
    return markers


def analyze_marker_context(
    text: str, *, final: bool = True, fence_indent: int | None = None
) -> MarkerContext:
    """Recognize outer literals before markers; a real marker's body stays opaque.

    Complete markers in inline code and HTML retain their historical collection
    and substitution behavior. An incomplete example cannot consume text after
    that literal's closing delimiter. Fences are optional because the streaming
    filter already owns their state, while document callers need whole blocks.
    """
    context = MarkerContext()
    runs = list(_BACKTICK_RUN.finditer(text))
    breaks = list(_INLINE_CODE_BREAK.finditer(text))
    break_starts = {boundary.start() for boundary in breaks}
    boundary_index = len(breaks) - 1
    next_run: dict[int, tuple[int, int]] = {}
    closing: dict[int, tuple[int, int]] = {}
    for run in reversed(runs):
        while boundary_index >= 0 and breaks[boundary_index].start() >= run.end():
            next_run.clear()
            boundary_index -= 1
        if boundary_index >= 0 and breaks[boundary_index].end() > run.start():
            # A fence delimiter is a block boundary, never an inline-code closer.
            next_run.clear()
            boundary_index -= 1
            continue
        width = run.end() - run.start()
        if width in next_run:
            closing[run.start()] = next_run[width]
        if final or run.end() < len(text):
            next_run[width] = (run.start(), run.end())
    fence_pattern = (
        re.compile(r"^[ ]{0," + str(fence_indent) + r"}(`{3,}|~{3,}).*$")
        if fence_indent is not None
        else None
    )
    at = 0
    while at < len(text):
        if at in break_starts:
            context.unmatched_backticks.clear()
        if fence_pattern is not None and (not at or text[at - 1] in _LINE_END_CHARS):
            line_break = _LINE_END.search(text, at)
            line_end = line_break.start() if line_break else len(text)
            fence = fence_pattern.match(text[at:line_end])
            if fence:
                opening = fence.group(1)
                end = line_break.end() if line_break else len(text)
                while end < len(text):
                    line_break = _LINE_END.search(text, end)
                    line_end = line_break.start() if line_break else len(text)
                    line = text[end:line_end]
                    candidate = fence_pattern.match(line)
                    end = line_break.end() if line_break else len(text)
                    stripped = line.rstrip().lstrip(" ")
                    if (
                        candidate
                        and len(stripped) >= len(opening)
                        and stripped == opening[0] * len(stripped)
                    ):
                        break
                context.fences.append((at, end))
                at = end
                continue
        if text.startswith("{{", at):
            if _escaped(text, at):
                context.escaped_openers.append(at)
                at += 1
                continue
            close = text.find("}}", at + 2)
            if close < 0:
                context.markers.append(
                    ContextMarker(at, len(text), text[at + 2 :], None, complete=False)
                )
                break
            raw = text[at + 2 : close]
            context.markers.append(
                ContextMarker(at, close + 2, raw, normalize_variable_name(raw))
            )
            at = close + 2
        elif run := _BACKTICK_RUN.match(text, at):
            if not _escaped(text, at):
                if at in closing:
                    content_end, end = closing[at]
                    context.literals.append((at, end))
                    context.markers.extend(
                        _literal_markers(text, run.end(), content_end)
                    )
                    at = end
                    continue
                context.unmatched_backticks.append((at, run.group()))
            at = run.end()
        elif text[at] == "<" and not _escaped(text, at):
            if html := _INLINE_HTML.match(text, at):
                context.literals.append((at, html.end()))
                context.markers.extend(_literal_markers(text, at, html.end()))
                at = html.end()
            else:
                if context.pending_html_start is None and (
                    at + 1 == len(text) or _HTML_PREFIX.match(text, at)
                ):
                    context.pending_html_start = at
                at += 1
        else:
            at += 1
    return context


def marker_syntax_source(text: str, context: MarkerContext) -> str:
    """Hide only literal/escaped openers and fenced controls, preserving offsets."""
    scanned = list(text)
    for start, end in context.literals:
        for at in range(start, end):
            if scanned[at] == "{":
                scanned[at] = "\x00"
    for at in context.escaped_openers:
        scanned[at] = "\x00"
    for start, end in context.fences:
        scanned[start:end] = "\x00" * (end - start)
    return "".join(scanned)
