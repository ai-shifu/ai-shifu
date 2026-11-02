"""Cut what a 2.0 turn says into the pieces a 1.0 lesson is delivered in.

A 1.0 lesson never reaches the browser as one stretch of text. The MarkdownFlow formatter divides
the model's output into typed pieces as it streams -- a run of prose, an HTML card, a code fence,
an image -- and each piece becomes its own element. That shape is what the rest of the product is
built on: in listening mode a text element is spoken and not shown, a visual element is shown and
not spoken, and the audio for a passage is bound to the element the passage is in.

A 2.0 turn is one continuous stretch of text for a whole lesson. Sent as it is, the whole lesson
lands in a single text element: the cover card inside it is never shown, because a text element is
not renderable, and the audio for every page but one is lost, because an element keeps one page's
audio. So the turn is run through the same formatter a 1.0 lesson goes through, and comes out in
the same pieces, with the same types and the same numbering. Nothing here decides what a piece is;
the formatter does, exactly as it does for 1.0.

All learning modes use these pieces. Classification is independent of whether audio is requested:
classroom needs the visual types to select what to show, and reading needs the same elements for
history and later mode changes. Content and numbering belong to the formatter, including
script/style pieces appended to earlier HTML.
The agent opts into prose-only MDF marker cleanup after that classification; visuals stay opaque.
Question prompts start a fresh formatter after visuals so they cannot inherit unfinished syntax.
Consecutive prose keeps its existing element identity, as it does in the 1.0 stream.
"""

from __future__ import annotations

from .preserve_markers import PreserveMarkerFormatter
from .syntax.formatter.stream import StreamFormatter


class LessonPager:
    """The formatter a 1.0 lesson streams through, applied to a 2.0 turn.

    `add` returns `(content, type, number)` pieces for every complete line in the text so far, in
    order; `flush` returns whatever is still buffered when the turn ends. The legacy default
    passes content through exactly. With `clean_markers=True`, prose markers are removed;
    ambiguous Markdown waits for a boundary or flush, and visual source stays unchanged.
    """

    def __init__(self, *, clean_markers: bool = False) -> None:
        """Start a fresh formatter for one turn."""
        self._clean_markers = clean_markers
        self._formatter = self._new_formatter()
        self._block_offset = 0
        self._next_number = 0
        self._last_type = ""

    def add(self, text: str) -> list[tuple[str, str, int]]:
        """Format the next stretch of the turn's text."""
        return self._pieces(self._formatter.process(text))

    def flush(self) -> list[tuple[str, str, int]]:
        """Format what is still buffered, because the turn is over."""
        return self._pieces(self._formatter.flush())

    def start_block(self) -> list[tuple[str, str, int]]:
        """Flush preceding content and keep the question outside unfinished visual syntax.

        A question is outside any unfinished HTML or code in the narration. Its formatter starts
        fresh, as a new 1.0 block does, while the offset keeps its identity separate from the
        visual. Consecutive prose stays in the same element to preserve history and audio
        grouping. Use the maximum emitted number: script/style may have returned to an earlier
        HTML number immediately before this boundary.
        """
        pieces = self.flush()
        if self._last_type in {"text", "title"}:
            # These types already leave the classifier in its ordinary text state.
            return pieces
        self._formatter = self._new_formatter()
        self._block_offset = self._next_number
        return pieces

    def _new_formatter(self) -> StreamFormatter | PreserveMarkerFormatter:
        return PreserveMarkerFormatter() if self._clean_markers else StreamFormatter()

    def _pieces(self, elements: list) -> list[tuple[str, str, int]]:
        pieces = [
            (element.content, element.type, element.number + self._block_offset)
            for element in elements
        ]
        for _, stream_type, number in pieces:
            self._next_number = max(self._next_number, number + 1)
            self._last_type = stream_type
        return pieces
