"""
Sandbox-aware text splitting helpers for listen/audiovisual mode.

We split a generated markdown block into multiple speakable parts based on
"sandbox" boundaries (visual elements rendered as sandbox on the frontend).

Unit rule:
    A sandbox element and the speech AFTER it are treated as one unit.
    Therefore, we split speakable text by sandbox blocks and synthesize the
    speakable sections between sandbox blocks.
"""

from __future__ import annotations

import html
import re
from typing import List


_DELIM = "\n\n[[[SANDBOX_BOUNDARY]]]\n\n"


# NOTE: This list should stay aligned with frontend sandbox rendering as much as
# possible. It is intentionally conservative and focuses on common visual blocks.
_SANDBOX_BLOCK_PATTERNS: list[re.Pattern[str]] = [
    # Mermaid diagrams.
    re.compile(r"```mermaid[\s\S]*?```", re.IGNORECASE),
    # SVG blocks.
    re.compile(r"<svg[\s\S]*?</svg>", re.IGNORECASE),
    # Common HTML/XML block elements that typically render as sandbox.
    re.compile(
        r"<(math|script|style|iframe|canvas|video|audio|table)[^>]*>[\s\S]*?</\1>",
        re.IGNORECASE,
    ),
    # HTML images.
    re.compile(r"<img\b[^>]*?>", re.IGNORECASE),
    # Markdown images.
    re.compile(r"!\[[^\]]*\]\([^)]+\)"),
]


def _normalize_for_boundary_detection(text: str) -> str:
    """
    Normalize HTML entity escaping so sandbox tags like '<svg>' can be detected.

    This mirrors the best-effort unescape behavior in `preprocess_for_tts`.
    """
    if not text:
        return ""

    try:
        for _ in range(2):  # handle double-escaped content (e.g. '&amp;lt;')
            unescaped = html.unescape(text)
            if unescaped == text:
                break
            text = unescaped
    except Exception:
        pass

    if "\xa0" in text:
        text = text.replace("\xa0", " ")

    return text


def split_text_by_sandbox_boundaries(text: str) -> List[str]:
    """
    Split raw markdown content into speakable parts by sandbox boundaries.

    Returns:
        A list of raw markdown parts in order. Parts may be empty if the text
        starts/ends with sandbox blocks or contains consecutive sandbox blocks.
    """
    normalized = _normalize_for_boundary_detection(text or "")
    if not normalized:
        return []

    replaced = normalized
    for pattern in _SANDBOX_BLOCK_PATTERNS:
        replaced = pattern.sub(_DELIM, replaced)

    return replaced.split(_DELIM)
