"""Document-stage views of the single marker scanner for syntax-layer callers.

Every function here reads one ``scan_marker_document`` pass, so variable
extraction, separator protection, block splitting and preprocessing classify
markers exactly as the engine and the learner runtime do.
"""

from bisect import bisect_right
from collections.abc import Iterator

from markdownflow.syntax.variable_names import VariableMarker

from .marker_context import MarkerContext, scan_marker_document


def _literal_units(context: MarkerContext) -> list[tuple[int, int]]:
    """Literal markup regions, backslash escape pairs and unmatched code runs."""
    return [*context.literals, *context.escapes, *context.code_runs]


def _document_units(context: MarkerContext) -> list[tuple[int, int]]:
    """Literal regions plus live marker regions, in source order."""
    starts = [start for start, _ in context.literals]
    units = _literal_units(context)
    for marker in context.markers:
        at = bisect_right(starts, marker.start) - 1
        if at < 0 or marker.start >= context.literals[at][1]:
            units.append((marker.start, marker.end))
    return sorted(units)


def _variable_marker(marker) -> VariableMarker:  # noqa: ANN001
    return VariableMarker(marker.start, marker.end, marker.raw_name, marker.name)


def find_document_variable_markers(text: str) -> Iterator[VariableMarker]:
    """Collect complete examples inside markup, without letting them cross its edge."""
    if "{{" not in text:
        return
    context, _ = scan_marker_document(text)
    for marker in context.markers:
        if marker.complete:
            yield _variable_marker(marker)


def find_document_protected_spans(text: str) -> Iterator[tuple[int, int]]:
    """Keep document separators outside marker names and already-owned markup."""
    context, _ = scan_marker_document(text)
    yield from _document_units(context)


def find_document_interaction_spans(text: str) -> Iterator[tuple[int, int]]:
    """Find controls outside markup while retaining raw ownership inside controls."""
    if "?[" not in text:
        return
    context, _ = scan_marker_document(text)
    yield from context.controls


class DocumentLiteralReader:
    """Answer literal-region lookups at source offsets from one document scan."""

    def __init__(self, text: str) -> None:
        """Scan the whole text once."""
        self.text = text
        self.context, self.blocks = scan_marker_document(text)
        self._ends = dict(_literal_units(self.context))
        self._markers = [
            _variable_marker(marker)
            for marker in self.context.markers
            if marker.complete
        ]
        self._marker_starts = [marker.start for marker in self._markers]

    def read(self, start: int) -> int | None:
        """Return the end of the literal starting at ``start``, if there is one."""
        return self._ends.get(start)

    def literal_markers(self, start: int, end: int) -> list[VariableMarker]:
        """Return the complete examples the scan found inside ``[start, end)``."""
        low = bisect_right(self._marker_starts, start - 1)
        high = bisect_right(self._marker_starts, end - 1)
        return self._markers[low:high]
