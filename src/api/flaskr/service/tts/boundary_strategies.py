"""
Boundary detection strategies for TTS visual element skipping.

Provides a strategy pattern for finding the end positions of different
visual element types (fence, svg, iframe, video, table, sandbox, image).

Cross-Platform Compatibility Note:
These patterns mirror the frontend visual boundary detection in
src/cook-web/src/c-utils/listen-mode/visual-boundary-detector.ts
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from flaskr.service.tts.patterns import (
    AV_IFRAME_CLOSE,
    AV_SVG_CLOSE,
    AV_TABLE_CLOSE,
    AV_VIDEO_CLOSE,
)
from flaskr.service.tts.pipeline import (
    _extend_fixed_marker_end,
    _find_html_block_end_with_complete,
    _find_markdown_table_block,
    _get_fence_ranges,
)


class BoundaryStrategy(ABC):
    """Abstract base class for boundary detection strategies."""

    @abstractmethod
    def find_end(self, raw: str) -> Optional[int]:
        """
        Find the end position of the visual element in raw text.

        Args:
            raw: The raw text starting with the visual element

        Returns:
            End position (exclusive) if found and complete, None otherwise
        """
        pass


class FenceBoundaryStrategy(BoundaryStrategy):
    """Strategy for fenced code blocks (```)."""

    def find_end(self, raw: str) -> Optional[int]:
        if not raw:
            return None
        # Find closing ``` after the opening (skip first 3 chars)
        close = raw.find("```", 3)
        if close == -1:
            return None
        return close + 3


class SvgBoundaryStrategy(BoundaryStrategy):
    """Strategy for SVG elements (<svg>...</svg>)."""

    def find_end(self, raw: str) -> Optional[int]:
        if not raw:
            return None
        close = AV_SVG_CLOSE.search(raw)
        if not close:
            return None
        return close.end()


class IframeBoundaryStrategy(BoundaryStrategy):
    """Strategy for iframe elements (<iframe>...</iframe>)."""

    def find_end(self, raw: str) -> Optional[int]:
        if not raw:
            return None
        close = AV_IFRAME_CLOSE.search(raw)
        if not close:
            return None
        return _extend_fixed_marker_end(raw, close.end())


class VideoBoundaryStrategy(BoundaryStrategy):
    """Strategy for video elements (<video>...</video>)."""

    def find_end(self, raw: str) -> Optional[int]:
        if not raw:
            return None
        close = AV_VIDEO_CLOSE.search(raw)
        if not close:
            return None
        return close.end()


class HtmlTableBoundaryStrategy(BoundaryStrategy):
    """Strategy for HTML table elements (<table>...</table>)."""

    def find_end(self, raw: str) -> Optional[int]:
        if not raw:
            return None
        close = AV_TABLE_CLOSE.search(raw)
        if not close:
            return None
        return close.end()


class MarkdownTableBoundaryStrategy(BoundaryStrategy):
    """Strategy for markdown tables (| A | B |\n| --- | --- |)."""

    def find_end(self, raw: str) -> Optional[int]:
        if not raw:
            return None
        fence_ranges = _get_fence_ranges(raw)
        block = _find_markdown_table_block(raw, fence_ranges)
        if block is None:
            return None
        _start, end, complete = block
        if not complete:
            return None
        return end


class SandboxBoundaryStrategy(BoundaryStrategy):
    """Strategy for HTML sandbox blocks (div, section, article, etc.)."""

    def find_end(self, raw: str) -> Optional[int]:
        if not raw:
            return None
        end, complete = _find_html_block_end_with_complete(raw, 0)
        return end if complete else None


class MarkdownImageBoundaryStrategy(BoundaryStrategy):
    """Strategy for markdown images (![alt](url))."""

    def find_end(self, raw: str) -> Optional[int]:
        if not raw:
            return None
        start = raw.find("![")
        if start == -1:
            return None
        image_open = raw.find("](", start + 2)
        if image_open == -1:
            return None
        image_close = raw.find(")", image_open + 2)
        if image_close == -1:
            return None
        return image_close + 1


# Registry of boundary strategies
BOUNDARY_STRATEGIES: dict[str, BoundaryStrategy] = {
    "fence": FenceBoundaryStrategy(),
    "svg": SvgBoundaryStrategy(),
    "iframe": IframeBoundaryStrategy(),
    "video": VideoBoundaryStrategy(),
    "html_table": HtmlTableBoundaryStrategy(),
    "md_table": MarkdownTableBoundaryStrategy(),
    "sandbox": SandboxBoundaryStrategy(),
    "md_img": MarkdownImageBoundaryStrategy(),
}


def find_boundary_end(kind: str, raw: str) -> Optional[int]:
    """
    Find the end position of a visual element boundary.

    Args:
        kind: The type of visual element (fence, svg, iframe, video, html_table,
              md_table, sandbox, md_img)
        raw: The raw text starting with the visual element

    Returns:
        End position (exclusive) if found and complete, None otherwise

    Example:
        >>> find_boundary_end("fence", "```python\\ncode\\n```")
        18
        >>> find_boundary_end("video", "<video src='test.mp4'></video>")
        30
    """
    strategy = BOUNDARY_STRATEGIES.get(kind)
    if strategy is None:
        return None
    return strategy.find_end(raw)
