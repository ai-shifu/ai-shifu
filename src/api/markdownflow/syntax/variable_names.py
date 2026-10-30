"""Opaque variable names and the first-closing-brace marker contract."""

import re
from collections.abc import Iterator
from dataclasses import dataclass

VARIABLE_BODY_SOURCE = r"(?:(?!\}\})[\s\S])*"
VARIABLE_REFERENCE_SOURCE = r"\{\{(" + VARIABLE_BODY_SOURCE + r")\}\}"
VARIABLE_ASSIGNMENT_SOURCE = "%" + VARIABLE_REFERENCE_SOURCE
VARIABLE_ASSIGNMENT_UNIT_SOURCE = r"%\{\{" + VARIABLE_BODY_SOURCE + r"\}\}"
VARIABLE_REFERENCE_UNIT_SOURCE = r"\{\{" + VARIABLE_BODY_SOURCE + r"\}\}"
_INVALID_NAME = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def normalize_variable_name(raw: str) -> str | None:
    """Trim Python whitespace while preserving every character inside a valid name."""
    name = raw.strip()
    if not name or "}}" in name or _INVALID_NAME.search(name):
        return None
    return name


@dataclass(frozen=True)
class VariableMarker:
    """One whole marker, including an invalid name that must not be reparsed inside."""

    start: int
    end: int
    raw_name: str
    name: str | None


def read_variable_marker(text: str, start: int = 0) -> VariableMarker | None:
    """Read exactly at start; the first literal closing pair always ends the marker."""
    if not text.startswith("{{", start):
        return None
    close = text.find("}}", start + 2)
    if close < 0:
        return None
    raw = text[start + 2 : close]
    return VariableMarker(start, close + 2, raw, normalize_variable_name(raw))


def read_interaction_variable(text: str, start: int = 0) -> VariableMarker | None:
    """Read only a leading binding, accepting the legacy percent prefix."""
    while start < len(text) and text[start].isspace():
        start += 1
    if text.startswith("%", start):
        start += 1
    return read_variable_marker(text, start)


def find_variable_markers(text: str) -> Iterator[VariableMarker]:
    """Yield non-overlapping markers without recursively reading their names."""
    at = 0
    while (start := text.find("{{", at)) >= 0:
        marker = read_variable_marker(text, start)
        if marker is None:
            return
        yield marker
        at = marker.end


def format_variable_reference(raw: str) -> str | None:
    """Pad a normalized name so even a final single brace remains part of the name."""
    name = normalize_variable_name(raw)
    return "{{ " + name + " }}" if name is not None else None


def format_variable_assignment(raw: str) -> str | None:
    """Render an assignment without introducing an escape or quote decoding rule."""
    reference = format_variable_reference(raw)
    return "%" + reference if reference is not None else None


def find_interaction_end(text: str, start: int = 0) -> int:
    """Find a closing bracket after skipping whole assignment markers and option escapes."""
    at = start
    while at < len(text):
        if text.startswith("{{", at):
            marker = read_variable_marker(text, at)
            if marker is None:
                return -1
            at = marker.end
        elif text[at] == "\\" and at + 1 < len(text) and text[at + 1] in "|/.]":
            at += 2
        elif text[at] == "]":
            return at
        else:
            at += 1
    return -1


def find_interaction_spans(
    text: str, *, syntax_source: str | None = None
) -> Iterator[tuple[int, int]]:
    """Scan without restarting inside complete or unterminated marker text."""
    source = syntax_source if syntax_source is not None else text
    at = 0
    while at < len(text):
        if source.startswith("{{", at):
            marker = read_variable_marker(text, at)
            if marker is None:
                return
            at = marker.end
        elif source.startswith("?[", at) and (not at or text[at - 1] != "\\"):
            end = find_interaction_end(text, at + 2)
            if end < 0:
                return
            if text[end + 1 : end + 2] != "(":
                yield at, end + 1
            at = end + 1
        else:
            at += 1
