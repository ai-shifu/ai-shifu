"""Document-stage boundaries without changing the raw variable-marker grammar."""

import itertools
from collections.abc import Iterator
from string import punctuation

from markdownflow.syntax.constants import (
    COMPILED_ATX_START_REGEX,
    COMPILED_BLANK_LINE_REGEX,
    COMPILED_DOLLAR_RUN_REGEX,
    COMPILED_INLINE_HTML_REGEX,
    COMPILED_PHYSICAL_LINE_END_REGEX,
    COMPILED_RAW_HTML_END_REGEX,
    COMPILED_RAW_HTML_START_REGEX,
)
from markdownflow.syntax.variable_names import (
    VariableMarker,
    find_variable_markers,
    read_variable_marker,
)

from .document_blocks import (
    DocumentBlocks,
    container_content_info,
    container_content_start,
    container_opening,
    fence_opening,
    indentation,
    read_angle_autolink,
)

_HTML_TERMINATORS = (("<!--", "-->"), ("<?", "?>"), ("<![CDATA[", "]]>"))


def document_html_ends(text: str) -> dict[str, int]:
    """Index possible native HTML closers once for a document scan."""
    return {
        ending: text.rfind(ending)
        for ending in (">", *(closing for _, closing in _HTML_TERMINATORS))
    }


def _html_can_close(text: str, start: int, last_ends: dict[str, int]) -> bool:
    if last_ends[">"] < start:
        return False
    for opening, closing in _HTML_TERMINATORS:
        if text.startswith(opening, start):
            return last_ends[closing] >= start + len(opening)
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
    last_html_ends: dict[str, int],  # noqa: ARG001
    blocks: DocumentBlocks,
) -> tuple[str, int] | None:
    if start not in blocks.by_start:
        return None
    content = blocks.block_content_start(blocks.by_start[start])
    if content is None:
        return None
    opening = COMPILED_RAW_HTML_START_REGEX.match(text, content)
    if opening is None:
        return None
    tag_start = text.find("<", start, opening.end())
    token_end = blocks.html_token_end(blocks.by_start[start], tag_start)
    return opening.group(
        1
    ).lower(), token_end if token_end is not None else opening.end()


def _raw_html_bounds(
    text: str, start: int, last_html_ends: dict[str, int], blocks: DocumentBlocks
) -> tuple[int, int] | None:
    opening = _raw_html_opening(text, start, last_html_ends, blocks)
    if opening is None:
        return None
    name, opening_end = opening
    limit = blocks.container_end(blocks.by_start[start])
    closing = COMPILED_RAW_HTML_END_REGEX[name].search(text, opening_end, limit)
    if closing is not None:
        blocks.closed_html_lines.add(blocks.line_at(closing.end()).start)
    return opening_end, blocks.line_at(
        closing.end()
    ).content_end if closing is not None else limit


def literal_variable_markers(
    text: str, start: int, end: int
) -> Iterator[VariableMarker]:
    """Keep opening attributes and raw HTML bodies as separate local examples."""
    ending = COMPILED_PHYSICAL_LINE_END_REGEX.search(text, start, end)
    opening_line = text[start : ending.start() if ending is not None else end]
    content, _ = container_opening(opening_line)
    tag_start = start + content
    while tag_start < end and text[tag_start] == " ":
        tag_start += 1
    token_end = None
    if tag_start < end and text[tag_start] == "<":
        local = DocumentBlocks(text[start:end], COMPILED_INLINE_HTML_REGEX)
        token_end = local.html_token_end(0, tag_start - start)
    boundaries = (
        (start, start + token_end, end)
        if token_end is not None and start + token_end <= end
        else (start, end)
    )
    for left, right in itertools.pairwise(boundaries):
        for marker in find_variable_markers(text[left:right]):
            yield VariableMarker(
                left + marker.start, left + marker.end, marker.raw_name, marker.name
            )


def read_link_resource_end(text: str, start: int) -> int | None:
    """Read a complete inline-link resource, without claiming an unfinished one."""
    at = start + 1

    def skip_space(cursor: int) -> int | None:
        beginning = cursor
        while cursor < len(text) and text[cursor] in " \t\r\n":
            cursor += 1
        return (
            None
            if COMPILED_BLANK_LINE_REGEX.search(text, beginning, cursor)
            else cursor
        )

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
            if COMPILED_BLANK_LINE_REGEX.search(text, title_start, at) is not None:
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


def read_reference_end(text: str, start: int, blocks: DocumentBlocks) -> int | None:
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


def _math_spans(
    text: str, last_html_ends: dict[str, int], blocks: DocumentBlocks
) -> dict[int, int]:
    """Index equal-width math delimiters once, bounded by paragraphs and blocks."""
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
        if COMPILED_ATX_START_REGEX.match(value) is not None:
            breaks.extend(
                ((line.start, line.start), (line.content_end, line.content_end))
            )
    breaks.sort()
    spans: dict[int, int] = {}
    next_run: dict[int, tuple[int, int]] = {}
    boundary_index = len(breaks) - 1
    for run in reversed(list(COMPILED_DOLLAR_RUN_REGEX.finditer(text))):
        while boundary_index >= 0 and breaks[boundary_index][0] >= run.end():
            next_run.clear()
            boundary_index -= 1
        if boundary_index >= 0 and breaks[boundary_index][1] > run.start():
            next_run.clear()
            boundary_index -= 1
            continue
        start = run.start()
        before = start
        while before and text[before - 1] == "\\":
            before -= 1
        opening_start = start + (start - before) % 2
        width = run.end() - opening_start
        if width and width in next_run:
            spans[opening_start] = next_run[width][1]
        next_run[run.end() - start] = (start, run.end())
    return spans


class DocumentLiteralReader:
    """Carry only document-stage link-label state and reusable delimiter indexes."""

    def __init__(self, text: str) -> None:
        """Precompute HTML, block and math boundaries for the whole text."""
        self.text = text
        self.last_html_ends = document_html_ends(text)
        self.blocks = DocumentBlocks(text, COMPILED_INLINE_HTML_REGEX)
        self.math_spans = _math_spans(text, self.last_html_ends, self.blocks)
        self.labels: list[tuple[bool, bool]] = []
        self.active_links: set[int] = set()
        self.resource_start = -1
        self.resource_image = False

    def read(self, start: int) -> int | None:
        """Return the end of the literal starting at ``start``, if there is one."""
        index = self.blocks.by_start.get(start)
        if index is not None and (index == 0 or self.blocks.blank(index - 1)):
            self.labels.clear()
            self.active_links.clear()
        reference_start = self.blocks.reference_prefix(start)
        if reference_start is not None:
            reference_end = read_reference_end(self.text, reference_start, self.blocks)
            if reference_end is not None:
                return reference_end
        end = read_document_literal_end(
            self.text, start, last_html_ends=self.last_html_ends, blocks=self.blocks
        )
        if end is not None:
            return end
        if self.text[start] == "$" and start in self.math_spans:
            return self.math_spans[start]
        if self.text[start] == "(" and start == self.resource_start:
            resource_end = read_link_resource_end(self.text, start)
            if resource_end is not None and not self.resource_image:
                for index in self.active_links:
                    self.labels[index] = (False, False)
                self.active_links.clear()
            return resource_end
        if self.text[start] == "[":
            image = start > 0 and self.text[start - 1] == "!"
            before = start - 1
            while before > 0 and self.text[before - 1] == "\\":
                before -= 1
            image = image and (start - 1 - before) % 2 == 0
            self.labels.append((image, True))
            if not image:
                self.active_links.add(len(self.labels) - 1)
        elif self.text[start] == "]" and self.labels:
            self.active_links.discard(len(self.labels) - 1)
            self.resource_image, active = self.labels.pop()
            self.resource_start = start + 1 if active else -1
        return None


def read_document_literal_end(
    text: str,
    start: int,
    *,
    last_html_ends: dict[str, int] | None = None,
    blocks: DocumentBlocks | None = None,
) -> int | None:
    """Read a literal region using physical line offsets without rewriting names."""
    blocks = (
        blocks
        if blocks is not None
        else DocumentBlocks(text, COMPILED_INLINE_HTML_REGEX)
    )
    last_html_ends = (
        last_html_ends if last_html_ends is not None else document_html_ends(text)
    )
    fenced = blocks.fence(start)
    if fenced is not None:
        return fenced.end
    indented_end = _indented_code_end(text, start, blocks)
    if indented_end is not None:
        return indented_end
    raw_html = _raw_html_bounds(text, start, last_html_ends, blocks)
    if raw_html is not None:
        return raw_html[1]
    special_html = blocks.terminated_html(start)
    if special_html is not None:
        return special_html.end
    ordinary = blocks.ordinary_html(start)
    if ordinary is not None:
        return ordinary.end
    if text[start] == "\\":
        return (
            start + 2
            if start + 1 < len(text) and text[start + 1] in punctuation
            else None
        )
    if text[start] == "<":
        if (autolink_end := read_angle_autolink(text, start)) is not None:
            return autolink_end
        if not _html_can_close(text, start, last_html_ends):
            return None
        return blocks.html_token_end(
            blocks.by_start[blocks.line_at(start).start], start
        )
    if text[start] != "`":
        return None
    opening_end = start + 1
    while opening_end < len(text) and text[opening_end] == "`":
        opening_end += 1
    size = opening_end - start
    opening_line = blocks.line_at(start)
    opening_heading = (
        COMPILED_ATX_START_REGEX.match(
            blocks.projected_line(blocks.by_start[opening_line.start])
        )
        is not None
    )
    at = opening_end
    while at < len(text):
        if text[at] in "\r\n":
            line = blocks.line_at(at)
            following = blocks.by_start.get(line.end)
            if following is not None:
                next_line = blocks.lines[following]
                value = blocks.projected_line(following)
                if (
                    opening_heading
                    or COMPILED_ATX_START_REGEX.match(value) is not None
                    or not value.strip(" \t")
                    or fence_opening(value) is not None
                    or blocks.paragraph_interrupts(following)
                    or blocks.inline_block_interrupts(following)
                    or _raw_html_opening(text, next_line.start, last_html_ends, blocks)
                    is not None
                ):
                    break
            at = line.end
            continue
        if text[at] == "`":
            end = at + 1
            while end < len(text) and text[end] == "`":
                end += 1
            if end - at == size:
                return end
            at = end
        else:
            at += 1
    return opening_end


def _document_units(text: str) -> Iterator[tuple[int, int, bool]]:
    """Yield literal markup and raw-marker regions, keeping interaction bodies raw."""
    at = 0
    interaction_until = -1
    reader = DocumentLiteralReader(text)
    while at < len(text):
        if at > interaction_until:
            literal_end = reader.read(at)
            if literal_end is not None:
                yield at, literal_end, True
                at = literal_end
                continue
            if text.startswith("?[", at):
                limit, closed = reader.blocks.interaction_limit(
                    at + 2,
                    lambda position: (
                        marker.end
                        if (marker := read_variable_marker(text, position)) is not None
                        else None
                    ),
                )
                if not (closed and text[limit + 1 : limit + 2] == "("):
                    interaction_until = limit if closed else limit - 1
        if text.startswith("{{", at):
            marker = read_variable_marker(text, at)
            end = marker.end if marker is not None else len(text)
            yield at, end, False
            at = end
        else:
            at += 1


def find_document_variable_markers(text: str) -> Iterator[VariableMarker]:
    """Collect complete examples inside markup, without letting them cross its edge."""
    if "{{" not in text:
        return
    for start, end, literal in _document_units(text):
        if literal:
            if text[start] == "\\":
                continue
            yield from literal_variable_markers(text, start, end)
        else:
            marker = read_variable_marker(text, start)
            if marker is not None:
                yield marker


def find_document_protected_spans(text: str) -> Iterator[tuple[int, int]]:
    """Keep document separators outside marker names and already-owned markup."""
    for start, end, _ in _document_units(text):
        yield start, end


def find_document_interaction_spans(text: str) -> Iterator[tuple[int, int]]:
    """Find controls outside markup while retaining raw ownership inside controls."""
    at = 0
    reader = DocumentLiteralReader(text)
    while at < len(text):
        literal_end = reader.read(at)
        if literal_end is not None:
            at = literal_end
        elif text.startswith("{{", at):
            marker = read_variable_marker(text, at)
            if marker is None:
                return
            at = marker.end
        elif text.startswith("?[", at):
            end, closed = reader.blocks.interaction_limit(
                at + 2,
                lambda position: (
                    marker.end
                    if (marker := read_variable_marker(text, position)) is not None
                    else None
                ),
            )
            if not closed:
                at = end
                continue
            if text[end + 1 : end + 2] == "(":
                # Replay the native label instead of losing its resource state.
                at += 1
                continue
            yield at, end + 1
            at = end + 1
        else:
            at += 1
