from __future__ import annotations

from typing import Any


def normalize_source_span(raw: Any) -> list[int]:
    if not isinstance(raw, list) or len(raw) < 2:
        return []
    try:
        start = int(raw[0])
        end = int(raw[1])
    except (TypeError, ValueError):
        return []
    if start < 0 or end < 0:
        return []
    if end <= start:
        return []
    return [start, end]


def slice_source_by_span(raw_content: str, source_span: list[int]) -> str:
    if not raw_content:
        return ""
    if len(source_span) != 2:
        return ""
    start, end = source_span
    if start >= len(raw_content):
        return ""
    return raw_content[start : min(end, len(raw_content))]
