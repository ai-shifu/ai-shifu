"""Output Parser Module.

Handles output instructions and preserved content processing for MarkdownFlow documents.
"""

import re

from markdownflow.syntax.constants import (
    COMPILED_INLINE_PRESERVE_REGEX,
    COMPILED_PRESERVE_FENCE_REGEX,
)
from markdownflow.syntax.variable_names import read_variable_marker

from .document_context import (
    find_document_protected_spans,
    find_document_variable_markers,
)


def is_preserved_content_block(content: str) -> bool:
    """Check if content is completely preserved content block.

    Preserved blocks are entirely wrapped by markers with no external content.
    Supports inline (===content===), multiline (!=== ... !===) formats, and mixed formats.

    Args:
        content: Content to check

    Returns:
        True if content is fully wrapped by preserved markers

    """
    content, _, _ = _protect_variable_names(content)
    content = content.strip()
    if not content:
        return False

    lines = content.split("\n")

    # Use state machine to validate that all non-empty content is preserved
    state = "OUTSIDE"  # States: OUTSIDE, INSIDE
    has_preserve_content = False

    for line in lines:
        stripped_line = line.strip()

        # Check if this line is a fence marker (!===)
        if COMPILED_PRESERVE_FENCE_REGEX.match(stripped_line):
            if state == "OUTSIDE":
                # Enter preserve block
                state = "INSIDE"
                has_preserve_content = True
            elif state == "INSIDE":
                # Exit preserve block
                state = "OUTSIDE"
            # Fence markers themselves are valid preserved content
        # Non-fence lines
        elif state == "INSIDE" and stripped_line:  # type: ignore[unreachable]
            # Inside fence block, this is valid preserved content
            has_preserve_content = True
        elif stripped_line:  # Non-empty line outside fence
            # Outside fence block, check if it's inline format
            match = COMPILED_INLINE_PRESERVE_REGEX.match(stripped_line)
            if match:
                # Ensure inner content exists and contains no ===
                inner_content = match.group(1).strip()
                if inner_content and "===" not in inner_content:
                    # Valid inline format
                    has_preserve_content = True
                else:
                    # Invalid inline format
                    return False
            else:
                # Not fence, not inline format -> external content
                return False

    # Judgment conditions:
    # 1. Must have preserved content
    # 2. Final state must be OUTSIDE (all fence blocks closed)
    return has_preserve_content and state == "OUTSIDE"


def _protect_variable_names(content: str) -> tuple[str, dict[str, str], str]:
    """Keep opaque marker text outside the output-instruction operator grammar."""
    prefix = "\x00mdf-output-name:"
    if "{{" not in content:
        return content, {}, prefix
    spans = [
        (marker.start, marker.end) for marker in find_document_variable_markers(content)
    ]
    spans.extend(
        (start, end)
        for start, end in find_document_protected_spans(content)
        if content.startswith("{{", start)
        and read_variable_marker(content, start) is None
    )
    used_nonces = {
        match.group(1)
        for match in re.finditer(re.escape(prefix) + r"([0-9]+):", content)
    }
    nonce = 0
    while str(nonce) in used_nonces:
        nonce += 1
    prefix = f"{prefix}{nonce}:"
    markers: dict[str, str] = {}
    pieces: list[str] = []
    at = 0
    for start, end in spans:
        token = f"{prefix}{len(markers)}\x00"
        markers[token] = content[start:end]
        pieces.extend((content[at:start], token))
        at = end
    pieces.append(content[at:])
    return "".join(pieces), markers, prefix
