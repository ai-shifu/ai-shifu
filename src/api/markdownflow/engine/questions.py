"""Literal question text and the first-closing-brace marker contract."""

import re
from collections.abc import Iterator
from dataclasses import dataclass

MAX_QUESTION_LENGTH = 255
# A previous native host accepted this width for already-issued bindings.
MAX_LEGACY_QUESTION_LENGTH = 256

QUESTION_BODY_SOURCE = r"(?:(?!\}\})[\s\S])*"
QUESTION_MARKER_SOURCE = r"\{\{(" + QUESTION_BODY_SOURCE + r")\}\}"
QUESTION_SOURCE = "%" + QUESTION_MARKER_SOURCE
QUESTION_UNIT_SOURCE = r"%\{\{" + QUESTION_BODY_SOURCE + r"\}\}"
QUESTION_MARKER_UNIT_SOURCE = r"\{\{" + QUESTION_BODY_SOURCE + r"\}\}"
_INVALID_NAME = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def normalize_question(raw: str) -> str | None:
    """Trim Python whitespace while preserving every character inside a valid name."""
    name = raw.strip()
    if not name or "}}" in name or _INVALID_NAME.search(name):
        return None
    return name


@dataclass(frozen=True)
class QuestionMarker:
    """One whole marker, including an invalid name that must not be reparsed inside."""

    start: int
    end: int
    raw_name: str
    name: str | None


def read_question_marker(text: str, start: int = 0) -> QuestionMarker | None:
    """Read exactly at start; the first literal closing pair always ends the marker."""
    if not text.startswith("{{", start):
        return None
    close = text.find("}}", start + 2)
    if close < 0:
        return None
    raw = text[start + 2 : close]
    return QuestionMarker(start, close + 2, raw, normalize_question(raw))


def find_question_markers(text: str) -> Iterator[QuestionMarker]:
    """Yield non-overlapping markers without recursively reading their questions."""
    at = 0
    while (start := text.find("{{", at)) >= 0:
        marker = read_question_marker(text, start)
        if marker is None:
            return
        yield marker
        at = marker.end


def format_question_marker(raw: str) -> str | None:
    """Pad a normalized name so even a final single brace remains part of the name."""
    name = normalize_question(raw)
    return "{{ " + name + " }}" if name is not None else None


def format_question(raw: str) -> str | None:
    """Render a question marker without introducing an escape or quote decoding rule."""
    question = normalize_question(raw)
    if question is None or len(question) > MAX_QUESTION_LENGTH:
        return None
    reference = format_question_marker(question)
    return "%" + reference if reference is not None else None


def find_interaction_end(text: str, start: int = 0) -> int:
    """Find a closing bracket without splitting its question or literal option groups."""
    at = start
    while at < len(text):
        if text.startswith("{{", at):
            marker = read_question_marker(text, at)
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
    """Find authored controls while treating standalone braces as ordinary text."""
    source = syntax_source if syntax_source is not None else text
    at = 0
    while at < len(text):
        if source.startswith("?[", at) and (not at or text[at - 1] != "\\"):
            end = find_interaction_end(text, at + 2)
            if end < 0:
                return
            if text[end + 1 : end + 2] != "(":
                yield at, end + 1
            at = end + 1
        else:
            at += 1
