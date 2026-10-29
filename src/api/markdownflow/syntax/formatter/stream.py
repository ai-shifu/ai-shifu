"""Streaming Content Formatter.

Processes SSE chunks incrementally, maintaining line buffer and numbering state.
Mirrors Go formatter/stream.go.
"""

from .classifier import Classifier
from .types import ClassifyResult, ElementType, FormattedElement, is_text_family


class StreamFormatter:
    """Streaming formatter that processes SSE chunks in real time.

    Each call to ``process()`` accepts an SSE chunk and returns a list of
    :class:`FormattedElement` instances for all complete lines found in
    the chunk (combined with any buffered partial line from prior calls).

    Call ``flush()`` at the end of the stream to emit any remaining
    buffered content.
    """

    def __init__(self) -> None:
        """Start with an empty line buffer."""
        self._classifier = Classifier()
        self._line_buffer: str = ""
        self._current_number: int = 0
        self._last_html_number: int = 0
        self._last_type: str = ""
        self._started: bool = False
        self._pending_newlines: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, chunk: str) -> list[FormattedElement]:
        """Process an SSE chunk and return formatted elements for complete lines."""
        if not chunk:
            return []

        combined = self._line_buffer + chunk
        self._line_buffer = ""

        elements: list[FormattedElement] = []

        while True:
            nl_idx = combined.find("\n")
            if nl_idx == -1:
                # No newline; buffer the remainder
                self._line_buffer = combined
                break

            line = combined[:nl_idx]
            combined = combined[nl_idx + 1 :]

            # Empty lines: buffer the \n instead of discarding
            if line.strip() == "":
                self._pending_newlines += 1
                continue

            # Consume pending newlines
            line_content = line + "\n"
            if self._pending_newlines > 0:
                extra = "\n" * self._pending_newlines
                if elements:
                    elements[-1].content += extra
                elif self._started:
                    # Previous elements already returned; prepend to current line
                    line_content = extra + line_content
                else:
                    # Leading empty lines: prepend to first element
                    line_content = extra + line_content
                self._pending_newlines = 0

            cr = self._classifier.classify_line(line)

            if cr.is_append:
                self._current_number = self._last_html_number
            elif self._should_new_number(cr):
                self._current_number += 1

            if (
                cr.type == ElementType.HTML
                and not cr.is_continuation
                and not cr.is_append
            ):
                self._last_html_number = self._current_number

            elements.append(
                FormattedElement(
                    content=line_content, type=cr.type, number=self._current_number
                )
            )
            self._last_type = cr.type
            self._started = True

        return elements

    def flush(self) -> list[FormattedElement]:
        """Release remaining buffered content at stream end."""
        remaining = self._line_buffer
        self._line_buffer = ""

        if not remaining or remaining.strip() == "":
            # No real content to flush; any pending newlines are trailing
            # They cannot be attached since caller must handle via returned list
            self._pending_newlines = 0
            return []

        # Consume pending newlines: prepend to remaining content
        if self._pending_newlines > 0:
            extra = "\n" * self._pending_newlines
            remaining = extra + remaining
            self._pending_newlines = 0

        cr = self._classifier.classify_line(remaining.lstrip("\n"))

        if cr.is_append:
            self._current_number = self._last_html_number
        elif self._should_new_number(cr):
            self._current_number += 1

        if cr.type == ElementType.HTML and not cr.is_continuation and not cr.is_append:
            self._last_html_number = self._current_number

        elem = FormattedElement(
            content=remaining, type=cr.type, number=self._current_number
        )
        self._last_type = cr.type
        self._started = True

        return [elem]

    def current_number(self) -> int:
        """Return the current element number."""
        return self._current_number

    def next_number(self) -> int:
        """Increment and return the next element number."""
        if self._started:
            self._current_number += 1
        self._started = True
        return self._current_number

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _should_new_number(self, cr: ClassifyResult) -> bool:
        if not self._started:
            return False
        if cr.is_continuation:
            return False
        if is_text_family(cr.type) and is_text_family(self._last_type):
            return False
        if cr.type == ElementType.HTML:
            return True
        return cr.type != self._last_type
