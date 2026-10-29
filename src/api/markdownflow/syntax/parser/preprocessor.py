"""Code Block Preprocessor.

Extracts code block content before parsing, implementing CommonMark-compliant fenced code blocks.
Also extracts HTML comments to prevent them from being sent to LLM.
"""

from markdownflow.syntax.constants import (
    COMPILED_PHYSICAL_LINE_END_REGEX,
    COMPILED_VARIABLE_NAME_PLACEHOLDER_REGEX,
)
from markdownflow.syntax.variable_names import (
    find_interaction_end,
    read_variable_marker,
)

from .code_fence_utils import is_code_fence_end, parse_code_fence_start
from .document_blocks import physical_lines
from .document_context import DocumentLiteralReader, literal_variable_markers
from .html_comment_utils import (
    is_html_comment_end,
    is_html_comment_start,
    remove_inline_comment,
)


class CodeBlockPreprocessor:
    """Code block and HTML comment preprocessor.

    Extracts code blocks and HTML comments from document and replaces them with placeholders,
    so that MarkdownFlow syntax inside code blocks/comments is ignored during subsequent parsing.

    Attributes:
        code_blocks: Mapping of placeholder → original code block content (including fence markers)
        html_comments: Mapping of placeholder → HTML comment content (multi-line only)
        counter: Unified placeholder counter (code blocks and comments share same counter)

    """

    # State machine states
    STATE_NORMAL = "NORMAL"
    STATE_IN_CODE_BLOCK = "IN_CODE_BLOCK"
    STATE_IN_HTML_COMMENT = "IN_HTML_COMMENT"

    def __init__(self) -> None:
        """Initialize preprocessor."""
        self.code_blocks: dict[str, str] = {}
        self.html_comments: dict[str, str] = {}
        self.counter: int = 0

    def extract_code_blocks(self, document: str) -> str:
        r"""Extract code blocks and HTML comments from document and replace with placeholders.

        How it works:
          1. Scan document line by line using a state machine
          2. Detect CommonMark-compliant fenced code blocks
          3. Detect HTML multi-line comments
          4. Replace code blocks and comments with unique placeholders
          5. Store content in internal mappings

        Priority rules:
          - Code blocks have priority: HTML comments inside code blocks are not extracted
          - Single-line comments are removed inline: <!-- ... --> on same line
          - Multi-line comments are extracted with placeholders

        Args:
            document: Original markdown document

        Returns:
            Processed document (code blocks and comments replaced with placeholders)

        Examples:
            >>> preprocessor = CodeBlockPreprocessor()
            >>> doc = "```python\\nprint('hello')\\n```"
            >>> processed = preprocessor.extract_code_blocks(doc)
            >>> "__MDFLOW_CODE_BLOCK_1__" in processed
            True

        """
        # Opaque names may contain comment or fence punctuation. Protect marker text
        # before Markdown preprocessing, then restore its exact source afterward.
        marker_prefix = "\x00mdf-name:"
        while marker_prefix in document:
            marker_prefix += ":"
        markers: dict[str, str] = {}
        pieces: list[str] = []
        at = 0
        scan = 0
        mask_fence = None
        interaction_until = -1
        literal_reader = DocumentLiteralReader(document)

        def protect_marker(start: int, end: int) -> None:
            nonlocal at
            placeholder = f"{marker_prefix}{len(markers)}\x00"
            markers[placeholder] = document[start:end]
            pieces.extend((document[at:start], placeholder))
            at = end

        while scan < len(document):
            if scan == 0 or (
                document[scan - 1] in "\r\n"
                and not (document[scan - 1] == "\r" and document[scan] == "\n")
            ):
                line_break = COMPILED_PHYSICAL_LINE_END_REGEX.search(document, scan)
                line_end = line_break.start() if line_break else len(document)
                next_line = line_break.end() if line_break else len(document)
                line = document[scan:line_end]
                if mask_fence is not None:
                    if is_code_fence_end(line, mask_fence):
                        mask_fence = None
                    scan = next_line
                    continue
                opening = parse_code_fence_start(line)
                if opening is not None:
                    mask_fence = opening
                    scan = next_line
                    continue
            if document.startswith("<!--", scan):
                block = literal_reader.blocks.terminated_html(scan)
                if block is not None:
                    scan = block.end
                    continue
                comment_end = document.find("-->", scan + 4)
                scan = comment_end + 3 if comment_end >= 0 else len(document)
                continue
            if scan > interaction_until:
                literal_end = literal_reader.read(scan)
                if literal_end is not None:
                    for example in literal_variable_markers(
                        document, scan, literal_end
                    ):
                        protect_marker(example.start, example.end)
                    scan = literal_end
                    continue
                if document.startswith("?[", scan):
                    interaction_end = find_interaction_end(document, scan + 2)
                    interaction_until = (
                        interaction_end if interaction_end >= 0 else len(document)
                    )
            if document.startswith("{{", scan):
                marker = read_variable_marker(document, scan)
                end = marker.end if marker is not None else len(document)
                protect_marker(scan, end)
                scan = end
            else:
                scan += 1
        pieces.append(document[at:])
        masked_document = "".join(pieces)
        lines = physical_lines(masked_document)
        result = []

        # State machine variables
        state = self.STATE_NORMAL
        current_fence = None
        code_buffer = []
        comment_buffer = []

        for physical_line in lines:
            line = masked_document[physical_line.start : physical_line.content_end]
            ending = masked_document[physical_line.content_end : physical_line.end]
            if state == self.STATE_NORMAL:
                # Priority: Check code blocks first (code block priority principle)
                fence_info = parse_code_fence_start(line)
                if fence_info is not None:
                    # Enter code block state
                    state = self.STATE_IN_CODE_BLOCK
                    current_fence = fence_info
                    code_buffer = [line + ending]
                else:
                    # Check HTML comments (both single-line and multi-line need processing)
                    comment_info, is_single_line = is_html_comment_start(line)
                    if comment_info is not None:
                        if is_single_line:
                            # Single-line comment: remove comment part, preserve rest of line
                            cleaned_line = remove_inline_comment(line)
                            # Only add if cleaned content is non-empty
                            if cleaned_line.strip():
                                result.append(cleaned_line + ending)
                            # Don't store single-line comments, already processed
                        else:
                            # Multi-line comment: enter comment state
                            state = self.STATE_IN_HTML_COMMENT
                            comment_buffer = [line + ending]
                    else:
                        # Normal line, keep as-is
                        result.append(line + ending)

            elif state == self.STATE_IN_CODE_BLOCK:
                # Don't check HTML comments inside code blocks
                # Detect fence closing
                if is_code_fence_end(line, current_fence):
                    # Generate code block placeholder
                    placeholder = self._generate_code_block_placeholder()

                    # Store code block
                    code_content = "".join(code_buffer) + line
                    self.code_blocks[placeholder] = code_content

                    # Output placeholder (as a separate line)
                    result.append(placeholder + ending)

                    # Reset state
                    state = self.STATE_NORMAL
                    current_fence = None
                    code_buffer = []
                else:
                    code_buffer.append(line + ending)

            elif state == self.STATE_IN_HTML_COMMENT:
                # Accumulate comment lines
                # Detect comment end
                if is_html_comment_end(line):
                    # Generate HTML comment placeholder
                    placeholder = self._generate_html_comment_placeholder()

                    # Store comment
                    comment_content = "".join(comment_buffer) + line
                    self.html_comments[placeholder] = comment_content

                    # Output placeholder
                    result.append(placeholder + ending)

                    # Reset state
                    state = self.STATE_NORMAL
                    comment_buffer = []
                else:
                    comment_buffer.append(line + ending)

        # Handle unclosed code blocks (keep as-is)
        if state == self.STATE_IN_CODE_BLOCK and code_buffer:
            # Restore unclosed code block content to result
            result.extend(code_buffer)

        # Handle unclosed comments (keep as-is)
        if state == self.STATE_IN_HTML_COMMENT and comment_buffer:
            result.extend(comment_buffer)

        processed = "".join(result)
        if markers:

            def restore_markers(text: str) -> str:
                return COMPILED_VARIABLE_NAME_PLACEHOLDER_REGEX.sub(
                    lambda match: markers.get(match.group(0), match.group(0)), text
                )

            processed = restore_markers(processed)
            self.code_blocks = {
                key: restore_markers(value) for key, value in self.code_blocks.items()
            }
            self.html_comments = {
                key: restore_markers(value) for key, value in self.html_comments.items()
            }
        return processed

    def restore_code_blocks(self, processed: str) -> str:
        r"""Restore all placeholders back to original content (code blocks + HTML comments).

        Used for preserved content blocks, needs complete restoration of all content.

        Args:
            processed: Processed document containing placeholders

        Returns:
            Restored document

        Examples:
            >>> preprocessor = CodeBlockPreprocessor()
            >>> doc = "```python\\nprint('hello')\\n```"
            >>> processed = preprocessor.extract_code_blocks(doc)
            >>> restored = preprocessor.restore_code_blocks(processed)
            >>> restored == doc
            True

        """
        result = processed

        # Restore code block placeholders
        for placeholder, original in self.code_blocks.items():
            result = result.replace(placeholder, original)

        # Restore HTML comment placeholders
        for placeholder, original in self.html_comments.items():
            result = result.replace(placeholder, original)

        return result

    def restore_code_blocks_only(self, processed: str) -> str:
        """Restore only code block placeholders, not HTML comments.

        Used for content blocks sent to LLM, preserves code blocks but removes comments.

        Args:
            processed: Processed document containing placeholders

        Returns:
            Document with only code blocks restored (comment placeholders remain)

        """
        result = processed

        # Only restore code block placeholders
        for placeholder, original in self.code_blocks.items():
            result = result.replace(placeholder, original)

        return result

    def remove_html_comment_placeholders(self, processed: str) -> str:
        """Remove HTML comment placeholders and their lines.

        Used to clean comment content before sending to LLM.

        Args:
            processed: Processed document containing placeholders

        Returns:
            Document with comment placeholders removed

        """
        lines = physical_lines(processed)
        filtered_lines = []

        for physical_line in lines:
            line = processed[physical_line.start : physical_line.content_end]
            ending = processed[physical_line.content_end : physical_line.end]
            # Skip lines that only contain comment placeholders
            trimmed = line.strip()
            if not (
                trimmed.startswith("__MDFLOW_HTML_COMMENT_") and trimmed.endswith("__")
            ):
                # Keep non-placeholder lines, or lines where placeholder has other content
                filtered_lines.append(line + ending)

        return "".join(filtered_lines)

    def _generate_code_block_placeholder(self) -> str:
        """Generate code block placeholder.

        Returns:
            Placeholder in format __MDFLOW_CODE_BLOCK_N__

        """
        self.counter += 1
        return f"__MDFLOW_CODE_BLOCK_{self.counter}__"

    def _generate_html_comment_placeholder(self) -> str:
        """Generate HTML comment placeholder.

        Returns:
            Placeholder in format __MDFLOW_HTML_COMMENT_N__

        """
        self.counter += 1
        return f"__MDFLOW_HTML_COMMENT_{self.counter}__"

    def reset(self) -> None:
        """Reset preprocessor state (for processing new documents)."""
        self.code_blocks = {}
        self.html_comments = {}
        self.counter = 0

    def get_code_blocks(self) -> dict[str, str]:
        """Return all extracted code blocks (for debugging).

        Returns:
            Mapping of placeholder → original code block content

        """
        return self.code_blocks

    def get_html_comments(self) -> dict[str, str]:
        """Return all extracted HTML comments (for debugging).

        Returns:
            Mapping of placeholder → HTML comment content

        """
        return self.html_comments
