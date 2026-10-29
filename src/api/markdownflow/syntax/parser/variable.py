"""Variable Parser Module.

Provides variable extraction and replacement functionality for MarkdownFlow documents.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from markdownflow.syntax.constants import (
    OUTPUT_INSTRUCTION_PREFIX,
    OUTPUT_INSTRUCTION_SUFFIX,
    VARIABLE_DEFAULT_VALUE,
)

from .document_context import find_document_variable_markers


class _PreserveTagState:
    """Track real output tags without interpreting the contents of opaque markers."""

    def __init__(self) -> None:
        self.inside = False
        self._tail = ""

    def feed(self, text: str) -> None:
        combined = self._tail + text
        opening = combined.rfind(OUTPUT_INSTRUCTION_PREFIX)
        closing = combined.rfind(OUTPUT_INSTRUCTION_SUFFIX)
        if opening >= 0 or closing >= 0:
            self.inside = opening > closing
        # Retain incomplete tags that may continue across replacement boundaries.
        self._tail = combined[
            -(max(len(OUTPUT_INSTRUCTION_PREFIX), len(OUTPUT_INSTRUCTION_SUFFIX)) - 1) :
        ]

    def skip_marker(self) -> None:
        self._tail = ""


@dataclass
class _ReplacementSegment:
    """Keep original markers distinct from literal text and already rendered values."""

    text: str
    variable_name: str | None = None
    opaque: bool = False


def extract_variables_from_text(text: str) -> list[str]:
    """Extract all variable names from text.

    Recognizes two variable formats:
    - %{{variable_name}} format (preserved variables)
    - {{variable_name}} format (replaceable variables)

    Args:
        text: Text content to analyze

    Returns:
        Sorted list of unique variable names

    """
    return sorted(
        {
            marker.name
            for marker in find_document_variable_markers(text)
            if marker.name is not None
        }
    )


def replace_variables_in_text(
    text: str,
    variables: Mapping[str, str | list[str]] | None = None,
    add_quotes: bool = True,
) -> str:
    """Replace variables in text, undefined or empty variables are auto-assigned "UNKNOWN".

    Args:
        text: Text containing variables
        variables: Variable name to value mapping (accepts dict or any Mapping type)
        add_quotes: Whether to add triple quotes around replaced values (default: True).
                   Set to False for preserved content blocks where quotes should not be added.

    Returns:
        Text with variables replaced

    """
    if not text or not isinstance(text, str):
        return text or ""

    values = dict(variables or {})
    segments: list[_ReplacementSegment] = []
    at = 0
    for marker in find_document_variable_markers(text):
        segments.append(_ReplacementSegment(text[at : marker.start]))
        name = (
            marker.name
            if not (marker.start and text[marker.start - 1] == "%")
            else None
        )
        segments.append(
            _ReplacementSegment(text[marker.start : marker.end], name, opaque=True)
        )
        if name is not None:
            values.setdefault(name, VARIABLE_DEFAULT_VALUE)
        at = marker.end
    segments.append(_ReplacementSegment(text[at:]))

    # As in the historical per-variable replacement, every occurrence of one
    # key sees the same pre-batch state. Only the next key sees emitted values.
    for name, var_value in values.items():
        if isinstance(var_value, list):
            value_str = ", ".join(
                str(v) for v in var_value if v is not None and str(v).strip()
            )
            if not value_str:
                value_str = VARIABLE_DEFAULT_VALUE
        else:
            value_str = (
                str(var_value)
                if var_value not in (None, "")
                else VARIABLE_DEFAULT_VALUE
            )
        preserve = _PreserveTagState()
        for segment in segments:
            if not segment.opaque:
                preserve.feed(segment.text)
                continue
            if segment.variable_name == name:
                segment.text = (
                    f'"""{value_str}"""'
                    if add_quotes and not preserve.inside
                    else value_str
                )
                segment.variable_name = None
                segment.opaque = False
            # Read the original marker in this batch, never its new value.
            preserve.skip_marker()
    return "".join(segment.text for segment in segments)
