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

One thing the formatter does not know about is `---`. In a script it separates blocks, and a 1.0
lesson generates each block on its own, so the line never appears in output and each block is its
own page. The engine reproduces the script's separators in its text, so here they are dropped from
what is shown and spoken, and each one starts a new page -- which gives a listening 2.0 lesson the
page rhythm the author wrote into the script.
"""

from __future__ import annotations

from markdown_flow.formatter.stream import StreamFormatter

# A line that is only a horizontal rule: MarkdownFlow's block separator, or Markdown's own.
_RULE_LINES = frozenset({"---", "***", "___"})


def _is_rule(content: str) -> bool:
    return content.strip() in _RULE_LINES


class LessonPager:
    """The formatter a 1.0 lesson streams through, applied to a 2.0 turn.

    `add` returns `(content, type, number)` pieces for every complete line in the text so far, in
    order; `flush` returns whatever is still buffered when the turn ends. Text is never withheld
    beyond the line it is on, and nothing but separator lines is dropped.
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

    @property
    def number(self) -> int:
        """The number of the piece the turn is on now.

        For text that belongs with the current piece without having gone through the formatter --
        the prompt beside a question, say. Such text is not fed in, so it cannot move a boundary.
        """
        return self._formatter.current_number()

    def _pieces(self, elements: list) -> list[tuple[str, str, int]]:
        pieces: list[tuple[str, str, int]] = []
        # The formatter numbers a whole batch before this sees any of it, so a separator's effect
        # on the pieces after it in the same batch is applied here, and its effect on later batches
        # by advancing the formatter's own counter. Both are needed: prose on either side of a
        # separator is the same type, which the formatter alone would keep on one number.
        shift = 0
        for element in elements:
            content = str(element.content or "")
            if not content:
                continue
            if _is_rule(content):
                # A block boundary in the script: not shown, not spoken, and the text after it is
                # a new page, as it would be a new block in a 1.0 lesson.
                self._formatter.next_number()
                shift += 1
                continue
            pieces.append(
                (content, str(element.type or "text"), int(element.number) + shift)
            )
        return pieces
