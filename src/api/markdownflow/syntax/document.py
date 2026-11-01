"""Split a MarkdownFlow document into blocks and collect its variables."""

from collections.abc import Iterator

from .enums import BlockType
from .models import Block
from .parser.document_context import (
    find_document_interaction_spans,
    find_document_protected_spans,
)
from .parser.output import is_preserved_content_block
from .parser.preprocessor import CodeBlockPreprocessor
from .parser.variable import extract_variables_from_text


def _find_block_separator_spans(source: str) -> Iterator[tuple[int, int]]:
    """Match newline/whitespace separators without retrying every blank line."""
    position = 0
    while (start := source.find("\n", position)) != -1:
        marker = start + 1
        while marker < len(source) and source[marker].isspace():
            marker += 1
        if not source.startswith("---", marker):
            position = marker + 1
            continue

        end = marker + 3
        last_newline = -1
        while end < len(source) and source[end].isspace():
            if source[end] == "\n":
                last_newline = end
            end += 1
        if last_newline == -1:
            position = end
            continue

        # The former greedy whitespace expression ends at the last newline,
        # leaving any following indentation for the next content block.
        position = last_newline + 1
        yield start, position


class MarkdownFlowDocument:
    """Parse-only view of a MarkdownFlow document used by authoring and publishing."""

    def __init__(self, document: str) -> None:
        """Replace code blocks with placeholders once, before any parsing."""
        self._document = document
        self._blocks: list[Block] | None = None
        self._preprocessor = CodeBlockPreprocessor()
        self._processed_document = self._preprocessor.extract_code_blocks(document)

    def document(self) -> str:
        """Return the original document text."""
        return self._document

    @property
    def block_count(self) -> int:
        """Return the number of blocks."""
        return len(self.get_all_blocks())

    def get_all_blocks(self) -> list[Block]:
        """Split the document into content, preserved and interaction blocks."""
        if self._blocks is not None:
            return self._blocks

        # Parse the preprocessed document (code blocks already replaced with placeholders)
        source = self._processed_document
        protected = list(find_document_protected_spans(source))
        segments = []
        at = 0
        protected_at = 0
        for start, end in _find_block_separator_spans(source):
            while protected_at < len(protected) and protected[protected_at][1] <= start:
                protected_at += 1
            if protected_at < len(protected) and protected[protected_at][0] < end:
                continue
            segments.append(source[at:start])
            at = end
        segments.append(source[at:])
        final_blocks: list[Block] = []

        for segment in segments:
            at = 0
            parts: list[tuple[str, bool]] = []
            for start, end in find_document_interaction_spans(segment):
                parts.extend(((segment[at:start], False), (segment[start:end], True)))
                at = end
            parts.append((segment[at:], False))
            for part, interaction in parts:
                text = part.strip()
                if not text:
                    continue
                if interaction:
                    block_type = BlockType.INTERACTION
                elif is_preserved_content_block(text):
                    block_type = BlockType.PRESERVED_CONTENT
                else:
                    block_type = BlockType.CONTENT
                final_blocks.append(
                    Block(content=text, block_type=block_type, index=len(final_blocks))
                )

        self._blocks = final_blocks
        return self._blocks

    def extract_variables(self) -> list[str]:
        """Return unique variable names, ignoring code blocks and HTML comments."""
        return extract_variables_from_text(self._processed_document)
