"""Keep persisted MarkdownFlow positions while excluding authored comments."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

from markdown_flow.constants import BLOCK_SEPARATOR, INTERACTION_PATTERN_SPLIT
from markdown_flow.models import Block
from markdown_flow.parser.code_fence_utils import (
    is_code_fence_end,
    parse_code_fence_start,
)
from markdown_flow.parser.html_comment_utils import (
    is_html_comment_end,
    is_html_comment_start,
    remove_inline_comment,
)

from .agent.engine.script_code_blocks import build_code_block_index
from .agent.engine.script_comments import comment_ranges

if TYPE_CHECKING:
    from collections.abc import Iterator

    from markdown_flow import MarkdownFlow

_LINEBREAKS = re.compile(r"\r\n|\r|\n")


def _part_spans(text: str) -> Iterator[tuple[int, int]]:
    """Reproduce native block splitting while retaining each original offset."""
    segment_start = 0
    segments = [match.span() for match in re.finditer(BLOCK_SEPARATOR, text)]
    for separator_start, separator_end in [*segments, (len(text), len(text))]:
        cursor = segment_start
        for interaction in re.finditer(
            INTERACTION_PATTERN_SPLIT, text[segment_start:separator_start]
        ):
            start = segment_start + interaction.start()
            end = segment_start + interaction.end()
            yield cursor, start
            yield start, end
            cursor = end
        yield cursor, separator_start
        segment_start = separator_end


def _raw_source_spans(
    document: str, restored: str, spans: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Trace native inline deletions back to the original lexical context.

    Restoring placeholders reverses native preprocessing except its removal of
    the first inline comment and empty comment-only lines. Verify those exact
    native operations line by line; do not rescan their lossy result for notes.
    In particular, a removed backtick must not protect a later private comment.
    """
    if not spans:
        return []
    lines = restored.split("\n")
    line_index = 0
    raw_offset = 0
    restored_offset = 0
    pieces: list[tuple[int, int, int]] = []
    raw_lines = document.split("\n")
    code_fence = None
    in_comment = False
    for raw_index, line in enumerate(raw_lines):
        target = lines[line_index] if line_index < len(lines) else None
        single_line = False
        cleaned = line
        if code_fence is not None:
            if is_code_fence_end(line, code_fence):
                code_fence = None
        elif in_comment:
            in_comment = not is_html_comment_end(line)
        else:
            code_fence = parse_code_fence_start(line)
            if code_fence is None:
                comment, single_line = is_html_comment_start(line)
                if single_line:
                    cleaned = remove_inline_comment(line)
                elif comment is not None:
                    in_comment = True
        if single_line and not cleaned.strip():
            raw_offset += len(line) + (raw_index < len(raw_lines) - 1)
            continue
        if cleaned != target:
            message = "MarkdownFlow preprocessing does not match the original source"
            raise ValueError(message)
        if not single_line:
            pieces.append((restored_offset, restored_offset + len(line), raw_offset))
        else:
            comment_start = line.find("<!--")
            comment_end = line.find("-->", comment_start) + 3
            pieces.extend(
                [
                    (restored_offset, restored_offset + comment_start, raw_offset),
                    (
                        restored_offset + comment_start,
                        restored_offset + len(cleaned),
                        raw_offset + comment_end,
                    ),
                ]
            )
        restored_offset += len(cleaned)
        line_index += 1
        if line_index < len(lines):
            pieces.append(
                (restored_offset, restored_offset + 1, raw_offset + len(line))
            )
            restored_offset += 1
        raw_offset += len(line) + (raw_index < len(raw_lines) - 1)
    if line_index != len(lines):
        message = "MarkdownFlow preprocessing left unmatched source lines"
        raise ValueError(message)
    result: list[tuple[int, int]] = []
    piece_index = 0
    for start, end in spans:
        while piece_index < len(pieces) and pieces[piece_index][1] <= start:
            piece_index += 1
        source_start = None
        source_end = None
        for current in range(piece_index, len(pieces)):
            left, right, raw_start = pieces[current]
            if left >= end:
                break
            if right <= left:
                continue
            source_start = (
                raw_start + max(start - left, 0)
                if source_start is None
                else source_start
            )
            source_end = raw_start + min(end - left, right - left)
        if source_start is None or source_end is None:
            message = "MarkdownFlow block has no original source position"
            raise ValueError(message)
        result.append((source_start, source_end))
    return result


def project_legacy_block_positions(
    original: MarkdownFlow,
) -> tuple[list[Block], list[Block], dict[str, str]]:
    """Project one global source into the native slots without matching bodies.

    Native preprocessing can hide a comment behind a placeholder or split an
    unclosed note into several blocks. Restore the whole processed source with
    each slot's provenance, then remove notes across those boundaries. Empty
    slots remain addressable so existing progress and generated rows keep their
    original positions. Private execution blocks protect literal code from the
    library's variable renderer; public blocks retain stable authored source.
    """
    processed = original.get_processed_document()
    blocks = original.get_all_blocks()
    spans = []
    for part_start, part_end in _part_spans(processed):
        start, end = part_start, part_end
        while start < end and processed[start].isspace():
            start += 1
        while end > start and processed[end - 1].isspace():
            end -= 1
        if start < end:
            spans.append((start, end))
    if len(spans) != len(blocks) or any(
        processed[start:end] != block.content
        for (start, end), block in zip(spans, blocks, strict=True)
    ):
        message = "MarkdownFlow block positions do not match its source parser"
        raise ValueError(message)

    mappings = {
        **original._preprocessor.code_blocks,
        **original._preprocessor.html_comments,
    }
    placeholders = (
        re.compile("|".join(re.escape(key) for key in mappings)) if mappings else None
    )

    def restore(part: str) -> str:
        return (
            placeholders.sub(lambda match: mappings[match[0]], part)
            if placeholders
            else part
        )

    parts: list[str] = []
    restored_spans: list[tuple[int, int]] = []
    cursor = 0
    length = 0
    for start, end in spans:
        prefix, body = restore(processed[cursor:start]), restore(processed[start:end])
        parts.extend((prefix, body))
        length += len(prefix)
        restored_spans.append((length, length + len(body)))
        length += len(body)
        cursor = end
    parts.append(restore(processed[cursor:]))
    restored = "".join(parts)
    source = original.document
    restored_spans = _raw_source_spans(source, restored, restored_spans)
    comments = comment_ranges(source)
    literals = []
    comment_index = 0
    for start, end in sorted(build_code_block_index(source).items()):
        while comment_index < len(comments) and comments[comment_index][1] <= start:
            comment_index += 1
        if comment_index == len(comments) or start < comments[comment_index][0]:
            literals.append((start, end))
    ranges = sorted(
        [(start, end, False) for start, end in comments]
        + [(start, end, True) for start, end in literals]
    )
    public: list[Block] = []
    execution: list[Block] = []
    code: dict[str, str] = {}
    namespace = f"MDFLOW_POSITION_LITERAL_{uuid4().hex}_"
    while namespace in source:
        namespace = f"MDFLOW_POSITION_LITERAL_{uuid4().hex}_"
    range_index = 0
    for block, (start, end) in zip(blocks, restored_spans, strict=True):
        while range_index < len(ranges) and ranges[range_index][1] <= start:
            range_index += 1
        visible: list[str] = []
        protected: list[str] = []
        last_marker = None
        cursor = start
        for current_range in range(range_index, len(ranges)):
            left, right, literal = ranges[current_range]
            if left >= end:
                break
            left, right = max(left, start), min(right, end)
            visible.append(source[cursor:left])
            protected.append(source[cursor:left])
            text = source[left:right]
            if literal:
                marker = f"{namespace}{len(code)}__"
                last_marker = marker
                visible.append(text)
                protected.append(marker)
                code[marker] = text
            else:
                lines = "".join(_LINEBREAKS.findall(text))
                visible.append(lines)
                protected.append(lines)
            cursor = right
        visible.append(source[cursor:end])
        protected.append(source[cursor:end])
        public_content = "".join(visible).strip()
        private_content = "".join(protected).strip()
        if last_marker is not None and private_content.endswith(last_marker):
            # Native block splitting trims the source's outer whitespace before
            # execution. Keep that boundary rule when its last bytes are code.
            code[last_marker] = code[last_marker].rstrip()
        private_block = Block(private_content, block.block_type, block.index)
        public_block = Block(public_content, block.block_type, block.index)
        # Restored examples are display source, not variable declarations.
        # Native placeholders kept these names out of Block.variables as well.
        public_block.variables = list(private_block.variables)
        public.append(public_block)
        execution.append(private_block)
    return public, execution, code
