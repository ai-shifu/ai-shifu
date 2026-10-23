"""Document-stage marker boundaries without changing the raw name grammar."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from string import punctuation

from markdown_it.common.html_re import HTML_TAG_RE

from .document_blocks import (
    DocumentBlocks,
    container_content_info,
    container_content_start,
    fence_opening,
    indentation,
    read_angle_autolink,
)
from .variable_names import normalize_variable_name, read_variable_marker

_BACKTICK_RUN = re.compile(r"`+")
_DOLLAR_RUN = re.compile(r"\$+")
_BLANK_LINE = re.compile(
    r"(?:\r\n|\r(?!\n)|(?<!\r)\n)[ \t]*(?:\r\n|\r(?!\n)|(?<!\r)\n)"
)
_ATX_START = re.compile(r"^ {0,3}#{1,6}(?=[ \t\r\n]|$)", re.MULTILINE)
# Inline code belongs to one paragraph and cannot absorb a later fenced block.
_INLINE_CODE_BREAK = re.compile(
    r"^[ \t]*\r?$|^[ ]{0,3}(?:`{3,}[^`\r\n]*|~{3,}[^\r\n]*)\r?$", re.MULTILINE
)
# markdown-it anchors its public pattern for a substring. Drop only that anchor
# so matching at an existing source offset does not copy the remaining document.
_INLINE_HTML = re.compile(HTML_TAG_RE.pattern.removeprefix("^"))
_HTML_PREFIX = re.compile(r"<(?:/?[A-Za-z]|[!?])")
_HTML_TERMINATORS = (("<!--", "-->"), ("<?", "?>"), ("<![CDATA[", "]]>"))
_LINE_END = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")
_LINE_END_CHARS = "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"
_INDENTED_CODE = re.compile(r"(?: {4}| {0,3}\t)")
_RAW_HTML_START = re.compile(
    r"[ ]{0,3}<(script|style|pre|textarea)(?=[ \t\r\n\f>])",
    re.IGNORECASE | re.MULTILINE,
)
_RAW_HTML_END = {
    name: re.compile(r"</" + name + r"[ \t\r\n]*>", re.IGNORECASE)
    for name in ("script", "style", "pre", "textarea")
}


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
    inactive_document_controls: list[int] = field(default_factory=list)
    fences: list[tuple[int, int]] = field(default_factory=list)
    container_fences: list[tuple[int, int]] = field(default_factory=list)
    unmatched_backticks: list[tuple[int, str]] = field(default_factory=list)
    unmatched_math: list[tuple[int, str]] = field(default_factory=list)
    pending_html_start: int | None = None
    pending_autolink_start: int | None = None
    pending_raw_html_tag: str | None = None
    pending_raw_html_closed: bool = False
    pending_resource_start: int | None = None
    pending_labels: list[tuple[bool, bool]] = field(default_factory=list)
    pending_label_starts: list[int] = field(default_factory=list)
    pending_label_counts: list[int] = field(default_factory=list)
    pending_resource_image: bool = False
    pending_resource_label_start: int | None = None
    pending_resource_opener: bool = False
    pending_block_start: int | None = None
    pending_html_block: bool = False
    pending_indented_block: bool = False
    pending_block_steps: tuple[int, ...] = ()
    pending_html_closing_line: bool = False
    pending_container_fence: tuple[str, int, tuple[int, ...]] | None = None
    pending_container_closed: bool = False
    pending_reference_start: int | None = None
    pending_reference_body_start: int | None = None
    pending_reference_steps: tuple[int, ...] = ()
    indent_restart_after: list[int] = field(default_factory=list)


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


def _html_can_close(text: str, at: int, last_ends: dict[str, int]) -> bool:
    """Reject impossible tails before the native regex rescans them at each opener."""
    if last_ends[">"] < at:
        return False
    for opening, closing in _HTML_TERMINATORS:
        if text.startswith(opening, at):
            # CommonMark also accepts these two empty-comment spellings.
            if opening == "<!--" and text.startswith(("<!-->", "<!--->"), at):
                return True
            return last_ends[closing] >= at + len(opening)
    return True


def _indented_code_end(text: str, start: int, blocks: DocumentBlocks) -> int | None:
    index = blocks.by_start.get(start)
    if index is None or not (
        blocks.indented_may_start(index)
        or (blocks.container_steps[index] and blocks.paragraph_interrupts(index))
    ):
        return None
    first = blocks.lines[index]
    first_value = text[first.start : first.content_end]
    if (
        indentation(
            first_value,
            blocks.content_starts[index] - first.start,
            blocks.virtual_padding[index],
        )[1]
        < 4
    ):
        return None
    last_content_end = start
    steps = blocks.container_steps[index]
    for following in range(index, len(blocks.lines)):
        line = blocks.lines[following]
        value = text[line.start : line.content_end]
        info = (
            (
                blocks.content_starts[following] - line.start,
                blocks.virtual_padding[following],
            )
            if following == index
            else container_content_info(value, steps)
        )
        if info is None:
            if not value.strip(" \t") or container_content_start(
                value, steps, partial=True
            ) == len(value):
                continue
            break
        content, virtual = info
        body = value[content:]
        if body.strip(" \t"):
            if indentation(value, content, virtual)[1] < 4:
                break
            last_content_end = line.content_end
    return last_content_end if last_content_end > start else None


def _raw_html_opening(
    text: str,
    start: int,
    _last_ends: dict[str, int],
    blocks: DocumentBlocks,
    *,
    final: bool = True,
) -> tuple[str, int] | None:
    if start not in blocks.by_start:
        return None
    content = blocks.block_content_start(blocks.by_start[start])
    if content is None:
        return None
    opening = _RAW_HTML_START.match(text, content)
    if opening is None:
        return None
    tag_start = text.find("<", start, opening.end())
    token_end = blocks.html_token_end(blocks.by_start[start], tag_start, final=final)
    return opening.group(
        1
    ).lower(), token_end if token_end is not None else opening.end()


def _raw_html_bounds(
    text: str,
    start: int,
    last_ends: dict[str, int],
    blocks: DocumentBlocks,
    *,
    final: bool = True,
) -> tuple[int, int, bool] | None:
    """Recognize only native raw-text blocks, preserving generic HTML rules."""
    opening = _raw_html_opening(text, start, last_ends, blocks, final=final)
    if opening is None:
        return None
    name, opening_end = opening
    limit = blocks.container_end(blocks.by_start[start], final=final)
    closing = _RAW_HTML_END[name].search(text, opening_end, limit)
    if closing is not None:
        blocks.closed_html_lines.add(blocks.line_at(closing.end()).start)
    if closing is None:
        return opening_end, limit, False
    return opening_end, blocks.line_at(closing.end()).content_end, True


def _link_resource_end(text: str, start: int) -> int | None:
    """Read a complete inline-link resource, without claiming an unfinished one."""
    at = start + 1

    def skip_space(cursor: int) -> int | None:
        beginning = cursor
        while cursor < len(text) and text[cursor] in " \t\r\n":
            cursor += 1
        return None if _BLANK_LINE.search(text, beginning, cursor) else cursor

    at = skip_space(at)
    if at is None or at >= len(text):
        return None
    if text[at] == "<":
        at += 1
        while at < len(text):
            if text[at] == "\\" and at + 1 < len(text) and text[at + 1] in punctuation:
                at += 2
            elif text[at] == ">":
                at += 1
                break
            elif text[at] in "<\r\n":
                return None
            else:
                at += 1
        else:
            return None
    else:
        depth = 0
        while at < len(text):
            character = text[at]
            if character == "\\" and at + 1 < len(text) and text[at + 1] in punctuation:
                at += 2
                continue
            if character in " \t\r\n" or (character == ")" and depth == 0):
                break
            if character == "(":
                depth += 1
                if depth > 32:
                    return None
            elif character == ")":
                depth -= 1
            elif ord(character) < 32 or character == "\x7f":
                return None
            at += 1
        if depth:
            return None
    destination_end = at
    at = skip_space(at)
    if at is None or at >= len(text):
        return None
    if text[at] == ")":
        return at + 1
    if at == destination_end or text[at] not in "\"'(":
        return None
    closing = ")" if text[at] == "(" else text[at]
    at += 1
    title_start = at
    while at < len(text):
        if text[at] == "\\" and at + 1 < len(text) and text[at + 1] in punctuation:
            at += 2
        elif text[at] == closing:
            if _BLANK_LINE.search(text, title_start, at):
                return None
            at = skip_space(at + 1)
            return (
                at + 1
                if at is not None and at < len(text) and text[at] == ")"
                else None
            )
        else:
            at += 1
    return None


def _legacy_plain_fence(
    text: str, start: int, pattern: re.Pattern[str]
) -> tuple[int, int | None] | None:
    """Retain the host's established splitlines fence scope for script projection."""
    if start and text[start - 1] not in _LINE_END_CHARS:
        return None
    ending = _LINE_END.search(text, start)
    end = ending.start() if ending else len(text)
    match = pattern.match(text[start:end])
    if match is None:
        return None
    opening = match.group(1)
    at = ending.end() if ending else len(text)
    while at < len(text):
        line_start = at
        ending = _LINE_END.search(text, at)
        end = ending.start() if ending else len(text)
        value = text[at:end]
        at = ending.end() if ending else len(text)
        stripped = value.rstrip().lstrip(" ")
        if (
            pattern.match(value)
            and len(stripped) >= len(opening)
            and stripped == opening[0] * len(stripped)
        ):
            return at, line_start
    return len(text), None


def _reference_end(text: str, start: int, blocks: DocumentBlocks) -> int | None:
    """Read a complete definition resource without claiming an unfinished title."""
    at = blocks.reference_space(start, start)
    if at is None or at >= len(text):
        return None
    destination_start = at
    if text[at] == "<":
        at += 1
        while at < len(text):
            if text[at] == "\\" and at + 1 < len(text) and text[at + 1] in punctuation:
                at += 2
            elif text[at] == ">":
                at += 1
                break
            elif text[at] in "<\r\n":
                return None
            else:
                at += 1
        else:
            return None
    else:
        depth = 0
        while at < len(text) and text[at] not in " \t\r\n":
            character = text[at]
            if character == "\\" and at + 1 < len(text) and text[at + 1] in punctuation:
                at += 2
                continue
            if character == "(":
                depth += 1
                if depth > 32:
                    return None
            elif character == ")":
                depth -= 1
                if depth < 0:
                    return None
            elif ord(character) < 32 or character == "\x7f":
                return None
            at += 1
        if depth:
            return None
    if at == destination_start:
        return None
    destination_end = at
    destination_line = blocks.line_at(destination_end)
    fallback = (
        destination_line.content_end
        if not text[destination_end : destination_line.content_end].strip(" \t")
        else None
    )
    at = blocks.reference_space(at, start)
    if at is None or at >= len(text) or text[at] not in "\"'(":
        return fallback
    title_next_line = at > destination_line.content_end
    if at == destination_end:
        return None
    closing = ")" if text[at] == "(" else text[at]
    at += 1
    title_start = at
    while at < len(text):
        if text[at] == "\\" and at + 1 < len(text) and text[at + 1] in punctuation:
            at += 2
        elif text[at] == closing:
            line_end = blocks.line_at(at).content_end
            if blocks.reference_has_blank(title_start, at) or text[
                at + 1 : line_end
            ].strip(" \t"):
                return fallback if title_next_line else None
            return line_end
        else:
            at += 1
    return fallback if title_next_line else None


def _inline_closers(
    text: str, pattern: re.Pattern[str], breaks: list[tuple[int, int]], *, final: bool
) -> dict[int, tuple[int, int]]:
    runs = list(pattern.finditer(text))
    boundary_index = len(breaks) - 1
    next_run: dict[int, tuple[int, int]] = {}
    closing: dict[int, tuple[int, int]] = {}
    for run in reversed(runs):
        while boundary_index >= 0 and breaks[boundary_index][0] >= run.end():
            next_run.clear()
            boundary_index -= 1
        if boundary_index >= 0 and breaks[boundary_index][1] > run.start():
            # A fence delimiter is a block boundary, never an inline-code closer.
            next_run.clear()
            boundary_index -= 1
            continue
        # An odd slash escapes only the first tick; its suffix can open a span.
        start = run.start() + int(_escaped(text, run.start()))
        width = run.end() - start
        if width and width in next_run:
            closing[start] = next_run[width]
        if final or run.end() < len(text):
            next_run[run.end() - run.start()] = (run.start(), run.end())
    return closing


def analyze_marker_context(
    text: str,
    *,
    final: bool = True,
    fence_indent: int | None = None,
    label_counts: dict[int, int] | None = None,
) -> MarkerContext:
    """Recognize outer literals before markers; a real marker's body stays opaque.

    Complete markers in inline code and HTML retain their historical collection
    and substitution behavior. An incomplete example cannot consume text after
    that literal's closing delimiter. Fences are optional because the streaming
    filter already owns their state, while document callers need whole blocks.
    """
    context = MarkerContext()
    last_html_ends = {
        ending: text.rfind(ending)
        for ending in (">", *(closing for _, closing in _HTML_TERMINATORS))
    }
    blocks = DocumentBlocks(text, _INLINE_HTML)
    breaks: list[tuple[int, int]] = []
    for index, line in enumerate(blocks.lines):
        value = blocks.projected_line(index)
        opening = _raw_html_opening(text, line.start, last_html_ends, blocks)
        if (
            not value.strip(" \t")
            or fence_opening(value) is not None
            or opening is not None
            or blocks.inline_block_interrupts(index)
        ):
            breaks.append(
                (line.start, opening[1] if opening is not None else line.content_end)
            )
        if blocks.paragraph_interrupts(index):
            breaks.append((line.start, line.start))
        if _ATX_START.match(value) is not None:
            breaks.extend(
                ((line.start, line.start), (line.content_end, line.content_end))
            )
    breaks.sort()
    break_starts = {start for start, _ in breaks}
    closing = _inline_closers(text, _BACKTICK_RUN, breaks, final=final)
    math_closing = _inline_closers(text, _DOLLAR_RUN, breaks, final=final)
    legacy_fence = (
        re.compile(r"^[ ]{0," + str(fence_indent) + r"}(`{3,}|~{3,}).*$")
        if fence_indent is not None
        else None
    )
    at = 0
    labels: list[tuple[bool, bool, int, int]] = []
    active_links: set[int] = set()
    resource_start = -1
    resource_image = False
    resource_label_start = -1
    interaction_until = -1
    while at < len(text):
        if at <= interaction_until and not text.startswith("{{", at):
            at += 1
            continue
        if at <= interaction_until:
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
            continue
        if at in break_starts:
            labels.clear()
            active_links.clear()
            context.unmatched_backticks.clear()
            context.unmatched_math.clear()
        reference_start = blocks.reference_prefix(at)
        if reference_start is not None:
            reference_end = _reference_end(text, reference_start, blocks)
            if not final and not blocks.reference_has_blank(reference_start, len(text)):
                context.pending_reference_start = at
                context.pending_reference_body_start = reference_start
                context.pending_reference_steps = blocks.container_steps[
                    blocks.by_start[blocks.line_at(at).start]
                ]
            if reference_end is not None:
                context.literals.append((at, reference_end))
                context.markers.extend(_literal_markers(text, at, reference_start))
                context.markers.extend(
                    _literal_markers(text, reference_start, reference_end)
                )
                at = reference_end
                continue
        if legacy_fence is not None:
            legacy = _legacy_plain_fence(text, at, legacy_fence)
            if legacy is not None:
                end, closing_start = legacy
                context.fences.append((at, end))
                if closing_start is not None and closing_start in blocks.by_start:
                    blocks.closed_fence_lines.add(closing_start)
                at = end
                continue
        fenced = blocks.fence(at, final=final)
        if fenced is not None:
            if fenced.steps:
                context.container_fences.append((at, fenced.end))
            line = blocks.line_at(at)
            indent = len(text[at : line.content_end]) - len(
                text[at : line.content_end].lstrip(" ")
            )
            if not fenced.steps and fence_indent is not None and indent <= fence_indent:
                context.fences.append((at, fenced.end))
            else:
                context.literals.append((at, fenced.end))
                context.markers.extend(_literal_markers(text, at, fenced.end))
            if not final and fenced.steps and fenced.end == len(text):
                context.pending_block_start = at
                context.pending_container_fence = (
                    fenced.marker,
                    fenced.size,
                    fenced.steps,
                )
                context.pending_container_closed = fenced.closed
            at = fenced.end
            continue
        indented_end = _indented_code_end(text, at, blocks)
        if indented_end is not None:
            context.literals.append((at, indented_end))
            context.markers.extend(_literal_markers(text, at, indented_end))
            steps = blocks.container_steps[blocks.by_start[at]]
            trailing = blocks.lines[
                blocks.by_start[blocks.line_at(indented_end).start] + 1 :
            ]
            pending = not final
            for line in trailing:
                value = text[line.start : line.content_end]
                info = container_content_info(value, steps, partial=True)
                if value.strip(" \t") and (
                    info is None or value[info[0] :].strip(" \t")
                ):
                    pending = False
                    break
            if pending:
                context.pending_block_start = at
                context.pending_indented_block = True
                context.pending_block_steps = blocks.container_steps[
                    blocks.by_start[at]
                ]
            at = indented_end
            continue
        raw_html = _raw_html_bounds(text, at, last_html_ends, blocks, final=final)
        if raw_html is not None:
            opening_end, end, complete = raw_html
            context.literals.append((at, end))
            context.markers.extend(_literal_markers(text, at, opening_end))
            context.markers.extend(_literal_markers(text, opening_end, end))
            if not final and end == len(text):
                context.pending_html_start = at
                context.pending_raw_html_closed = complete
                context.pending_block_steps = blocks.container_steps[
                    blocks.by_start[at]
                ]
                opening = _raw_html_opening(
                    text, at, last_html_ends, blocks, final=final
                )
                if opening is not None:
                    context.pending_raw_html_tag = opening[0]
            at = end
            continue
        special_html = blocks.terminated_html(at, final=final)
        if special_html is not None:
            context.literals.append((at, special_html.end))
            context.markers.extend(_literal_markers(text, at, special_html.opening_end))
            context.markers.extend(
                _literal_markers(text, special_html.opening_end, special_html.end)
            )
            if not final and special_html.end == len(text):
                context.pending_block_start = at
                context.pending_html_closing_line = True
                context.pending_block_steps = blocks.container_steps[
                    blocks.by_start[at]
                ]
            at = special_html.end
            continue
        ordinary = blocks.ordinary_html(at, final=final)
        if ordinary is not None:
            context.literals.append((at, ordinary.end))
            context.markers.extend(_literal_markers(text, at, ordinary.opening_end))
            context.markers.extend(
                _literal_markers(text, ordinary.opening_end, ordinary.end)
            )
            if not final and (ordinary.end == len(text) or not ordinary.closed):
                context.pending_block_start = at
                context.pending_html_block = True
                context.pending_block_steps = blocks.container_steps[
                    blocks.by_start[blocks.line_at(at).start]
                ]
            at = ordinary.end
            continue
        if text[at] == "$" and not _escaped(text, at) and at in math_closing:
            _, end = math_closing[at]
            context.literals.append((at, end))
            context.markers.extend(_literal_markers(text, at, end))
            at = end
            continue
        if text[at] == "(" and at == resource_start:
            resource_end = _link_resource_end(text, at)
            if resource_end is not None:
                if not resource_image:
                    for index in active_links:
                        image, _, start, count = labels[index]
                        labels[index] = (image, False, start, count)
                    active_links.clear()
                context.literals.append((at, resource_end))
                context.markers.extend(_literal_markers(text, at, resource_end))
                at = resource_end
                continue
            if not final:
                context.pending_resource_start = at
        if (
            text[at] == "$"
            and not _escaped(text, at)
            and (math_run := _DOLLAR_RUN.match(text, at))
        ):
            context.unmatched_math.append((at, math_run.group()))
            at = math_run.end()
            continue
        if text[at] == "[" and not _escaped(text, at):
            labels.append(
                (
                    at > 0 and text[at - 1] == "!" and not _escaped(text, at - 1),
                    True,
                    at,
                    max(1, label_counts.get(at, 1)) if label_counts is not None else 1,
                )
            )
            if not labels[-1][0]:
                active_links.add(len(labels) - 1)
        elif text[at] == "]" and not _escaped(text, at) and labels:
            resource_image, active, resource_label_start, count = labels[-1]
            if count == 1:
                active_links.discard(len(labels) - 1)
                labels.pop()
            else:
                labels[-1] = (resource_image, active, resource_label_start, count - 1)
            resource_start = at + 1 if active else -1
        if text.startswith("?[", at) and not _escaped(text, at):
            limit, closed = blocks.interaction_limit(
                at + 2,
                lambda position: (
                    marker.end
                    if (marker := read_variable_marker(text, position)) is not None
                    else None
                ),
                final=final,
            )
            if not closed and limit < len(text):
                context.inactive_document_controls.append(at)
            interaction_until = limit if closed else limit - 1
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
            if _escaped(text, at):
                at += 1
                continue
            if at in closing:
                content_end, end = closing[at]
                context.literals.append((at, end))
                context.markers.extend(_literal_markers(text, run.end(), content_end))
                at = end
                continue
            context.unmatched_backticks.append((at, run.group()))
            at = run.end()
        elif text[at] == "<" and not _escaped(text, at):
            autolink_end = read_angle_autolink(text, at)
            if autolink_end is not None:
                context.literals.append((at, autolink_end))
                context.markers.extend(_literal_markers(text, at, autolink_end))
                at = autolink_end
                continue
            if (
                not final
                and context.pending_autolink_start is None
                and read_angle_autolink(text, at, partial=True) is not None
            ):
                context.pending_autolink_start = at
            index = blocks.by_start[blocks.line_at(at).start]
            html_end = (
                blocks.html_token_end(index, at, final=final)
                if _html_can_close(text, at, last_html_ends)
                else None
            )
            if html_end is not None:
                context.literals.append((at, html_end))
                context.markers.extend(_literal_markers(text, at, html_end))
                at = html_end
            else:
                if context.pending_html_start is None and (
                    at + 1 == len(text) or _HTML_PREFIX.match(text, at)
                ):
                    context.pending_html_start = at
                    context.pending_block_steps = blocks.container_steps[index]
                at += 1
        else:
            at += 1
    context.indent_restart_after = [
        line.content_end
        for index, line in enumerate(blocks.lines)
        if blocks.indented_may_start(index + 1)
    ]
    context.pending_labels = [(image, active) for image, active, _, _ in labels]
    context.pending_label_starts = [start for _, _, start, _ in labels]
    context.pending_label_counts = [count for _, _, _, count in labels]
    context.pending_resource_image = resource_image
    context.pending_resource_label_start = (
        resource_label_start if resource_label_start >= 0 else None
    )
    context.pending_resource_opener = resource_start == len(text)
    return context


def marker_syntax_source(text: str, context: MarkerContext) -> str:
    """Hide only literal/escaped openers and fenced controls, preserving offsets."""
    scanned = list(text)
    for start, end in context.literals:
        for at in range(start, end):
            if scanned[at] == "{":
                scanned[at] = "\x00"
    for at in (*context.escaped_openers, *context.inactive_document_controls):
        scanned[at] = "\x00"
    for start, end in context.fences:
        scanned[start:end] = "\x00" * (end - start)
    return "".join(scanned)
