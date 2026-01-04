"""
TTS Service Layer.

This module provides text preprocessing for TTS synthesis.
"""

import re
import logging

# Import models to ensure they are registered with SQLAlchemy
from .models import LearnGeneratedAudio  # noqa: F401


logger = logging.getLogger(__name__)

# Pattern to match code blocks (both fenced and inline)
CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```|`[^`]+`")

# Pattern to match markdown headers
HEADER_PATTERN = re.compile(r"^#+\s+", re.MULTILINE)

# Pattern to match markdown links [text](url)
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]+\)")

# Pattern to match markdown images ![alt](url)
IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\([^)]+\)")

# Pattern to match markdown bold/italic
BOLD_ITALIC_PATTERN = re.compile(r"\*{1,3}([^*]+)\*{1,3}|_{1,3}([^_]+)_{1,3}")

# Pattern to match markdown lists
LIST_PATTERN = re.compile(r"^[\s]*[-*+]\s+|^[\s]*\d+\.\s+", re.MULTILINE)

# Pattern to match mermaid blocks
MERMAID_PATTERN = re.compile(r"```mermaid[\s\S]*?```")

# Pattern to match SVG blocks
SVG_PATTERN = re.compile(r"<svg[\s\S]*?</svg>", re.IGNORECASE)

# Pattern to match any XML/HTML block elements with content
XML_BLOCK_PATTERN = re.compile(
    r"<(svg|math|script|style)[^>]*>[\s\S]*?</\1>", re.IGNORECASE
)


def has_incomplete_block(text: str) -> bool:
    """
    Check if text contains an incomplete block that should not be processed yet.

    This is important for streaming TTS where content arrives in chunks.
    We should wait for complete blocks before processing.

    Args:
        text: Text buffer to check

    Returns:
        True if there's an incomplete block that needs more content
    """
    if not text:
        return False

    # Check for incomplete code blocks (``` without closing ```)
    # Count occurrences - if odd number, block is incomplete
    code_block_count = text.count("```")
    if code_block_count % 2 == 1:
        return True

    # Check for incomplete SVG
    svg_opens = len(re.findall(r"<svg[^>]*>", text, re.IGNORECASE))
    svg_closes = len(re.findall(r"</svg>", text, re.IGNORECASE))
    if svg_opens > svg_closes:
        return True

    # Check for incomplete mermaid (inside code blocks, but might be streaming)
    # If we see ```mermaid but buffer has odd ``` count, it's incomplete
    if "```mermaid" in text.lower() and code_block_count % 2 == 1:
        return True

    return False


def preprocess_for_tts(text: str) -> str:
    """
    Remove code blocks and markdown formatting not suitable for TTS.

    Args:
        text: Raw markdown text

    Returns:
        Cleaned text suitable for TTS synthesis
    """
    if not text:
        return ""

    # IMPORTANT: Remove code blocks FIRST (they may contain SVG, mermaid, etc.)
    text = CODE_BLOCK_PATTERN.sub("", text)

    # Remove mermaid diagrams (in case they're not in code blocks)
    text = MERMAID_PATTERN.sub("", text)

    # Remove SVG blocks - handle multiline and nested content
    text = SVG_PATTERN.sub("", text)

    # Remove other XML block elements (math, script, style)
    text = XML_BLOCK_PATTERN.sub("", text)

    # Remove any remaining angle bracket content that looks like tags
    # This catches malformed or partial SVG/HTML
    text = re.sub(r"<[^>]*>", "", text)

    # Remove markdown headers (keep the text)
    text = HEADER_PATTERN.sub("", text)

    # Remove images completely
    text = IMAGE_PATTERN.sub("", text)

    # Keep link text but remove URL
    text = LINK_PATTERN.sub(r"\1", text)

    # Remove bold/italic markers but keep text
    text = BOLD_ITALIC_PATTERN.sub(r"\1\2", text)

    # Remove list markers
    text = LIST_PATTERN.sub("", text)

    # Remove data URIs (base64 encoded content)
    text = re.sub(r"data:[a-zA-Z0-9/+;=,]+", "", text)

    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    # Remove leading/trailing whitespace from each line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()
