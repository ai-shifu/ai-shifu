"""Formatter Type Definitions.

Defines ElementType constants, FormattedElement dataclass, and ClassifyResult.
Mirrors Go formatter/types.go.
"""

from dataclasses import dataclass, field
from typing import Any


class ElementType:
    """SSE stream content element types."""

    HTML = "html"
    SVG = "svg"
    DIFF = "diff"
    IMG = "img"
    TABLES = "tables"
    CODE = "code"
    LATEX = "latex"
    MERMAID = "mermaid"
    TITLE = "title"
    TEXT = "text"
    INTERACTION = "interaction"


@dataclass
class FormattedElement:
    """A structured element in the SSE stream."""

    content: str = ""
    type: str = ElementType.TEXT
    number: int = 0
    is_show: bool = False
    is_read: bool = False
    operation: str = ""
    is_checkpoint: bool = False
    audio_url: str = ""
    audio_segments: list[Any] = field(default_factory=list)


@dataclass
class ClassifyResult:
    """Classification result for a single line."""

    type: str = ElementType.TEXT
    is_append: bool = False  # script/style attaches to previous html block
    is_continuation: bool = False  # inside an existing block (not the first line)


def is_text_family(t: str) -> bool:
    """Check if type belongs to the text family (title <-> text transitions don't increment number)."""
    return t in (ElementType.TEXT, ElementType.TITLE)
