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
history and later mode changes. Content and numbering belong to the formatter, including literal
separator lines and script/style pieces appended to earlier HTML.
"""

from __future__ import annotations

from markdown_flow.formatter.stream import StreamFormatter


class LessonPager:
    """The formatter a 1.0 lesson streams through, applied to a 2.0 turn.

    `add` returns `(content, type, number)` pieces for every complete line in the text so far, in
    order; `flush` returns whatever is still buffered when the turn ends. Text is never withheld
    beyond the line it is on. The formatter's content, types, and numbers are passed through.
    """

    def __init__(self) -> None:
        """Start a fresh formatter for one turn."""
        self._formatter = StreamFormatter()

    def add(self, text: str) -> list[tuple[str, str, int]]:
        """Format the next stretch of the turn's text."""
        return self._pieces(self._formatter.process(text))

    def flush(self) -> list[tuple[str, str, int]]:
        """Format what is still buffered, because the turn is over."""
        return self._pieces(self._formatter.flush())

    @staticmethod
    def _pieces(elements: list) -> list[tuple[str, str, int]]:
        return [(element.content, element.type, element.number) for element in elements]
