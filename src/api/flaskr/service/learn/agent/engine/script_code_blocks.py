"""Locate Markdown code examples without losing their authored source bytes."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from markdown_it import MarkdownIt
from markdown_it.rules_block.html_block import HTML_SEQUENCES, html_block

from .script_html_tags import html_tag_end

if TYPE_CHECKING:
    from markdown_it.rules_block.state_block import StateBlock
    from markdown_it.token import Token

_LINEBREAKS = re.compile(r"\r\n|\r|\n")
_SAFE_HTML_STARTS = tuple(sequence[0] for sequence in HTML_SEQUENCES[:6])


def _safe_html_block(
    state: StateBlock, start_line: int, end_line: int, silent: bool
) -> bool:
    """Keep CommonMark HTML blocks without evaluating its generic-tag regex."""
    if state.is_code_block(start_line) or not state.md.options.get("html"):
        return False
    start = state.bMarks[start_line] + state.tShift[start_line]
    line = state.src[start : state.eMarks[start_line]]
    if not line.startswith("<"):
        return False
    if any(pattern.search(line) for pattern in _SAFE_HTML_STARTS):
        # The official rule stops at the same matching type 1-6 sequence.
        return html_block(state, start_line, end_line, silent)

    tag_end = html_tag_end(line, 0)
    if tag_end is None or line[tag_end:].strip() or silent:
        return False
    # Type 7 ends on a blank line or container exit. This state transition
    # follows markdown-it-py's MIT-licensed html_block rule (ExecutableBookProject).
    next_line = start_line + 1
    while next_line < end_line and state.sCount[next_line] >= state.blkIndent:
        start = state.bMarks[next_line] + state.tShift[next_line]
        if start == state.eMarks[next_line]:
            break
        next_line += 1
    state.line = next_line
    token = state.push("html_block", "", 0)
    token.map = [start_line, next_line]
    token.content = state.getLines(
        start_line, next_line, state.blkIndent, keepLastLF=True
    )
    return True


def build_code_block_index(text: str) -> dict[int, int]:
    """Map physical block starts to ends, including Markdown containers.

    Only the block parser runs: inline delimiter handling belongs to the caller.
    A caller must enter a range at its start, rather than protect every contained
    line. That keeps a fence inside a skipped HTML comment from exposing later
    author notes as literal code.
    """
    offsets = [0, *(match.end() for match in _LINEBREAKS.finditer(text))]
    if offsets[-1] != len(text):
        offsets.append(len(text))
    normalized = _LINEBREAKS.sub("\n", text).replace("\x00", "\ufffd")
    parser = MarkdownIt("commonmark")
    parser.block.ruler.at(
        "html_block",
        _safe_html_block,
        {"alt": ["paragraph", "reference", "blockquote"]},
    )
    tokens: list[Token] = []
    parser.block.parse(normalized, parser, {}, tokens)
    return {
        offsets[token.map[0]]: offsets[token.map[1]]
        for token in tokens
        if token.type in {"fence", "code_block"} and token.map is not None
    }
