"""
Visual boundary detection patterns for audio-visual sync.

This module defines regex patterns to detect visual content elements
(SVG, tables, images, iframes, code blocks, etc.) in streaming text.
These boundaries are used by VisualAwareTTSOrchestrator to split audio
at visual element positions so the frontend can synchronize playback.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class VisualMatch:
    """A matched visual element in the text buffer."""

    start: int
    end: int
    visual_type: str
    content: str


# ---------------------------------------------------------------------------
# Paired-tag patterns: <tag ...>...</tag>
# ---------------------------------------------------------------------------

_SVG_PATTERN = re.compile(r"<svg[\s\S]*?</svg>", re.IGNORECASE)

_IFRAME_PATTERN = re.compile(r"<iframe[\s\S]*?</iframe>", re.IGNORECASE)

_MATH_TAG_PATTERN = re.compile(r"<math[\s\S]*?</math>", re.IGNORECASE)

_HTML_BLOCK_PATTERN = re.compile(
    r"<(div|section|article|figure|details|blockquote)[^>]*>[\s\S]*?</\1>",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Fenced block patterns: ```...```
# ---------------------------------------------------------------------------

_MERMAID_PATTERN = re.compile(r"```mermaid[\s\S]*?```")

# Fenced code block with language tag (```python, ```js, etc.) or bare ```\n
_CODE_BLOCK_PATTERN = re.compile(r"```[a-zA-Z]*\n[\s\S]*?```")

# ---------------------------------------------------------------------------
# Inline / self-closing patterns
# ---------------------------------------------------------------------------

# Markdown image: ![alt text](url) — possibly with title
_MD_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\([^)]+\)")

# HTML img tag: <img ... /> or <img ...> (self-closing or void)
_HTML_IMG_PATTERN = re.compile(r"<img\s[^>]*?/?>", re.IGNORECASE)

# Markdown table: header row + separator row + optional data rows.
# The separator row must contain at least one cell with dashes (---|).
_MD_TABLE_PATTERN = re.compile(
    r"(?:^|\n)(\|[^\n]+\|\s*\n\|[\s:|-]+\|\s*\n(?:\|[^\n]+\|\s*\n?)*)",
    re.MULTILINE,
)

# LaTeX display math: $$...$$  (multiline)
_LATEX_DISPLAY_MATH_PATTERN = re.compile(r"\$\$[\s\S]+?\$\$")


# ---------------------------------------------------------------------------
# Ordered list of (pattern, visual_type) tuples.
# Order matters: paired tags first (they are larger / more important),
# then fenced blocks, then inline elements.
# ---------------------------------------------------------------------------

_VISUAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Paired tags
    (_SVG_PATTERN, "svg"),
    (_IFRAME_PATTERN, "iframe"),
    (_MATH_TAG_PATTERN, "math"),
    (_HTML_BLOCK_PATTERN, "html"),
    # Fenced blocks — mermaid before generic code to get a more specific type
    (_MERMAID_PATTERN, "mermaid"),
    (_CODE_BLOCK_PATTERN, "code"),
    # Inline / self-closing
    (_MD_IMAGE_PATTERN, "image"),
    (_HTML_IMG_PATTERN, "image"),
    (_MD_TABLE_PATTERN, "table"),
    (_LATEX_DISPLAY_MATH_PATTERN, "math"),
]


def find_earliest_complete_visual(text: str) -> Optional[VisualMatch]:
    """
    Find the earliest complete visual element in *text*.

    Scans all known visual patterns and returns the match that starts at
    the lowest position.  Returns ``None`` when no complete visual element
    is found (e.g. only incomplete / partial elements remain).

    Args:
        text: Raw text buffer (may contain markdown, HTML, SVG, etc.)

    Returns:
        A VisualMatch with start/end offsets, type, and raw content,
        or None if nothing matched.
    """
    if not text:
        return None

    earliest: Optional[VisualMatch] = None

    for pattern, visual_type in _VISUAL_PATTERNS:
        m = pattern.search(text)
        if m is None:
            continue

        # For table pattern the actual table content is in group(1)
        if visual_type == "table" and m.lastindex and m.lastindex >= 1:
            content = m.group(1)
            # Adjust start to the beginning of the table content within the
            # overall match (skip the optional leading newline).
            offset = m.start() + m.group(0).index(content)
            candidate = VisualMatch(
                start=offset,
                end=offset + len(content),
                visual_type=visual_type,
                content=content,
            )
        else:
            candidate = VisualMatch(
                start=m.start(),
                end=m.end(),
                visual_type=visual_type,
                content=m.group(0),
            )

        if earliest is None or candidate.start < earliest.start:
            earliest = candidate

    return earliest


# ---------------------------------------------------------------------------
# Incomplete element detection — used during streaming to decide whether
# to wait for more chunks before splitting.
# ---------------------------------------------------------------------------


def has_incomplete_visual(text: str) -> bool:
    """
    Check if *text* ends with an incomplete visual element that may become
    complete once more streaming chunks arrive.

    This extends the checks already present in ``tts/__init__.py`` with
    additional patterns for iframe, table, and LaTeX math.
    """
    if not text:
        return False

    # Incomplete fenced code block (odd number of ```)
    if text.count("```") % 2 == 1:
        return True

    lower = text.lower()

    # Incomplete paired tags
    for tag in (
        "svg",
        "iframe",
        "math",
        "div",
        "section",
        "article",
        "figure",
        "details",
        "blockquote",
    ):
        last_open = lower.rfind(f"<{tag}")
        if last_open != -1 and lower.find(f"</{tag}>", last_open) == -1:
            return True

    # Incomplete LaTeX display math (single $$ without closing $$)
    first_dd = text.find("$$")
    if first_dd != -1:
        second_dd = text.find("$$", first_dd + 2)
        if second_dd == -1:
            return True

    # Incomplete markdown table: header row present but separator row not yet
    # (a line starting with | but no |---| line following it at the very end)
    lines = text.rstrip().split("\n")
    if lines:
        last_line = lines[-1].strip()
        if last_line.startswith("|") and last_line.endswith("|"):
            # Could be a table header waiting for separator — check if the
            # second-to-last line also looks like a table row.
            # Only flag as incomplete if there is no separator row yet.
            has_separator = any(re.match(r"^\|[\s:|-]+\|$", ln.strip()) for ln in lines)
            if not has_separator:
                return True

    return False
