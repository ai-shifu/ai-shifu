"""
TTS Service Layer.

This module provides text preprocessing for TTS synthesis.
"""

import re
import logging
import html

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

_FENCE = "```"


def _strip_incomplete_fenced_code(text: str) -> tuple[str, bool]:
    """
    Strip an incomplete fenced code block from the end of the buffer.

    For streaming text, it is common to receive the opening fence in one chunk
    and the closing fence in a later chunk. In that case we should avoid letting
    any of the (potentially non-speakable) code content reach TTS.

    Returns:
        (text_without_incomplete_block, had_incomplete_block)
    """
    fence_count = text.count(_FENCE)
    if fence_count % 2 == 0:
        return text, False

    last_fence_pos = text.rfind(_FENCE)
    if last_fence_pos == -1:
        return text, False

    return text[:last_fence_pos], True


def _strip_incomplete_xml_block(text: str, tag_name: str) -> tuple[str, bool]:
    """
    Strip an incomplete XML/HTML block from the end of the buffer.

    This is primarily used for <svg> blocks which are not meant to be spoken.
    The implementation is intentionally tolerant of partial opening tags (e.g.
    '<svg width=\"800\"' without a closing '>') which can happen in streaming.
    """
    if not text:
        return text, False

    tag = (tag_name or "").strip().lower()
    if not tag:
        return text, False

    lower = text.lower()
    start = lower.rfind(f"<{tag}")
    if start == -1:
        return text, False

    end = lower.find(f"</{tag}>", start)
    if end == -1:
        return text[:start], True

    return text, False


def _strip_incomplete_angle_bracket_tag(text: str) -> tuple[str, bool]:
    """
    Strip an incomplete angle-bracket tag from the end of the buffer.

    This is a best-effort safeguard for streaming content where we might receive
    a partial HTML/XML tag split across chunks (e.g. '<p' or '<span class=\"').

    We only strip when the tail looks like a tag start (e.g. '<' followed by a
    letter, '/', '!' or '?'). This avoids removing common non-tag uses like
    '< 3' or 'a < b' where '<' is followed by whitespace or digits.
    """
    if not text:
        return text, False

    last_lt = text.rfind("<")
    if last_lt == -1:
        return text, False

    tail = text[last_lt:]
    if ">" in tail:
        return text, False

    if len(tail) == 1:
        return text[:last_lt], True

    next_char = tail[1]
    if next_char.isspace():
        return text, False

    if not (next_char.isalpha() or next_char in {"/", "!", "?"}):
        return text, False

    return text[:last_lt], True


def _strip_incomplete_blocks(text: str) -> tuple[str, bool]:
    """
    Strip known incomplete blocks from the end of the buffer.

    Returns:
        (text_without_incomplete_blocks, had_any_incomplete_block)
    """
    had_incomplete = False

    text, removed = _strip_incomplete_fenced_code(text)
    had_incomplete = had_incomplete or removed

    # Strip incomplete non-speakable XML blocks (most important: SVG).
    for tag in ("svg", "math", "script", "style"):
        text, removed = _strip_incomplete_xml_block(text, tag)
        had_incomplete = had_incomplete or removed

    # Strip incomplete generic HTML/XML tags (e.g. '<p' at buffer tail).
    text, removed = _strip_incomplete_angle_bracket_tag(text)
    had_incomplete = had_incomplete or removed

    return text, had_incomplete


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

    # Check for incomplete SVG (tolerant of partial opening tags in streaming)
    lower = text.lower()
    last_svg_open = lower.rfind("<svg")
    if last_svg_open != -1 and lower.find("</svg>", last_svg_open) == -1:
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

    # Normalize common HTML entity escaping (e.g. '&lt;p&gt;') so tag stripping
    # works consistently for content coming from HTML renderers.
    try:
        for _ in range(2):  # handle double-escaped content (e.g. '&amp;lt;')
            unescaped = html.unescape(text)
            if unescaped == text:
                break
            text = unescaped
    except Exception:
        # Best-effort only; keep original text on unescape errors.
        pass

    # Replace non-breaking spaces from HTML with regular spaces.
    if "\xa0" in text:
        text = text.replace("\xa0", " ")

    # Strip incomplete blocks at the tail of the stream buffer. This prevents
    # partial SVG/code blocks leaking into TTS between chunks.
    text, _ = _strip_incomplete_blocks(text)

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
