"""Split what a 2.0 turn says into the pages a listening lesson is read in.

A 1.0 lesson arrives already divided: the script's own blocks become separate elements, and the
audio for each one is bound to the element it belongs to. A 2.0 turn is one continuous stretch of
text for a whole lesson, so without this every page of it lands in a single element -- and audio
binding keeps only one page per element (`matched_positions[-1]`), which drops the audio for every
page but the last. The learner is then shown pages marked speakable that have no audio, which the
browser reads as buffering and waits on forever.

Pages are taken from the same contract the speech pipeline segments by, rather than from a rule of
our own, so a page boundary here is a page boundary there and the audio lands where its text is.
"""

from __future__ import annotations

from flaskr.service.tts.api import build_av_segmentation_contract


class LessonPager:
    """Tracks which page of a lesson the text arriving now belongs to.

    Fed the turn's text as it streams; returns the same text cut at page boundaries, each piece
    carrying the page it belongs to. A piece is never held back: a learner watching the lesson
    write itself has to see it as it is written.
    """

    def __init__(self) -> None:
        """Start on the first page with nothing said yet."""
        self._full = ""

    def add(self, text: str) -> list[tuple[str, int]]:
        """Return the new text split into `(text, page)` pieces, in order and complete.

        The contract is rebuilt over the whole turn each time rather than extended, because a
        boundary is only recognisable once enough of it has arrived -- the same reason the speech
        pipeline rebuilds it per chunk. Text is never withheld or reordered: a learner watching the
        lesson write itself has to see exactly what was written, in the order it was written.
        """
        if not text:
            return []
        start = len(self._full)
        self._full += text

        # Which page each newly arrived character belongs to. Positions the contract does not
        # cover -- whitespace between segments, the markup of a boundary itself -- carry the page
        # of the text before them, so nothing is dropped and nothing jumps a page early.
        spans = self._page_spans()
        page_of: dict[int, int] = {}
        for page, (span_start, span_end) in spans:
            for index in range(max(span_start, start), min(span_end, len(self._full))):
                page_of[index] = page

        pieces: list[tuple[str, int]] = []
        current = self._page_before(start, spans)
        buffer: list[str] = []
        for index in range(start, len(self._full)):
            page = page_of.get(index, current)
            if buffer and page != current:
                pieces.append(("".join(buffer), current))
                buffer = []
            current = page
            buffer.append(self._full[index])
        if buffer:
            pieces.append(("".join(buffer), current))
        return pieces

    def _page_spans(self) -> list[tuple[int, tuple[int, int]]]:
        contract = build_av_segmentation_contract(self._full)
        spans: list[tuple[int, tuple[int, int]]] = []
        for segment in contract.get("speakable_segments") or []:
            span = segment.get("source_span") or []
            if not isinstance(span, (list, tuple)) or len(span) != 2:
                continue
            try:
                start, end = int(span[0]), int(span[1])
                page = int(segment.get("position") or 0)
            except (TypeError, ValueError):
                continue
            spans.append((page, (start, end)))
        return spans

    @staticmethod
    def _page_before(offset: int, spans: list[tuple[int, tuple[int, int]]]) -> int:
        """Return the page in force just before this offset."""
        page = 0
        for candidate, (span_start, span_end) in spans:
            if span_start <= offset < span_end:
                return candidate
            if span_start < offset:
                page = candidate
        return page
