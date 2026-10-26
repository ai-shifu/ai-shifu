"""Compatibility imports for the shared native historical prompt matcher."""

from flaskr.common.markdownflow_prompt import (
    _render_legacy_text,
    historical_collected_questions,
    historical_reference_names,
    matched_section_length,
)

__all__ = [
    "_render_legacy_text",
    "historical_collected_questions",
    "historical_reference_names",
    "matched_section_length",
]
