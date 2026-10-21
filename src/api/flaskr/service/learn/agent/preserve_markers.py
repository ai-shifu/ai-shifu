"""Remove MDF markers from classified prose, leaving visual elements opaque.

The pinned MarkdownFlow formatter is the only authority on element boundaries.
This adapter retains physical source lines (including CRLF and trailing blanks)
while reusing its classifications and element numbers. It contains no HTML parser.
"""

from __future__ import annotations

import re
from copy import deepcopy

from markdown_flow.formatter.classifier import Classifier, _State
from markdown_flow.formatter.stream import StreamFormatter
from markdown_flow.formatter.types import ClassifyResult, FormattedElement

from .markdown_text import analyze_markdown_text, clean_markdown_text

_PROSE = {"text", "title"}
_PREFIX = re.compile(r"^([ \t]*)(!?={3,})")
_SUFFIX = re.compile(r"!?={3,}([ \t]*\r?)$")
_MARKER_LINE = re.compile(r"[ \t]*!={3,}[ \t]*\r?$")


class _EnvelopeClassifier(Classifier):
    """Let native classification recognize elements inside an MDF envelope.

    `_handle_text` and `_state` are hooks in the pinned markdown-flow 0.3.4
    implementation. Reuse that state rather than guessing whether a line is inside HTML or code.
    Only an outer MDF prefix/suffix is removed from a non-prose element.
    """

    def __init__(self) -> None:
        super().__init__()
        self.source = ""
        self._envelope = False

    def _handle_text(self, line: str) -> ClassifyResult:
        prefix = _PREFIX.match(line)
        candidate = _PREFIX.sub(r"\1", line, count=1) if prefix else line
        result = super()._handle_text(candidate)
        if prefix and result.type not in _PROSE:
            self.source = candidate
            self._envelope = True
        return result

    def classify_line(self, line: str) -> ClassifyResult:
        if self._envelope and _SUFFIX.search(line):
            candidate = _SUFFIX.sub(r"\1", line, count=1)
            probe = deepcopy(self)
            # A wrapped code closer such as ```=== must be unwrapped before
            # classification. Ask the native grammar whether it ends the block;
            # do not remove marker-like data from an opaque continuation line.
            super(_EnvelopeClassifier, probe).classify_line(candidate)
            if probe._state == _State.TEXT:
                line = candidate
        self.source = line
        result = super().classify_line(line)
        if self._envelope and self._state == _State.TEXT:
            self.source = _SUFFIX.sub(r"\1", self.source, count=1)
            self._envelope = False
        return result


class PreserveMarkerFormatter:
    """Format once, then remove markers only from text/title pieces.

    Plain lines stream immediately. A prose suffix containing Markdown openers
    waits for its grammar to finish. Reference links can resolve later in the
    document, so queued pieces share a native Markdown reference environment at
    flush. Visual source is never passed to the Markdown prose cleaner.
    """

    def __init__(self) -> None:
        """Start one source-preserving projection."""
        self._formatter = StreamFormatter()
        self._classifier = _EnvelopeClassifier()
        self._formatter._classifier = self._classifier
        self._line = ""
        self._leading = ""
        self._last: FormattedElement | None = None
        self._pending: list[FormattedElement] = []
        self._references = False
        self._environment: dict = {}

    def process(self, chunk: str) -> list[FormattedElement]:
        """Consume complete physical lines without changing their bytes."""
        lines = (self._line + chunk).split("\n")
        self._line = lines.pop()
        out: list[FormattedElement] = []
        for line in lines:
            out.extend(self._line_piece(line + "\n"))
        return out

    def _line_piece(
        self, source: str, *, final: bool = False
    ) -> list[FormattedElement]:
        line = source.removesuffix("\n")
        if (
            not self._pending
            and self._classifier._state == _State.TEXT
            and _MARKER_LINE.fullmatch(line)
        ):
            return []
        if not line.strip():
            if self._last is None:
                self._leading += source
                return []
            element = FormattedElement(
                content=source, type=self._last.type, number=self._last.number
            )
        else:
            elements = (
                self._formatter.process(source) + self._formatter.flush()
                if final
                else self._formatter.process(source)
            )
            if not elements:
                return []
            element = elements[0]
            cleaned = self._classifier.source
            element.content = (
                self._leading + cleaned + ("\n" if source.endswith("\n") else "")
            )
            self._leading = ""
            self._last = element
        out: list[FormattedElement] = []
        boundary = (
            not line.strip()
            or element.type not in _PROSE
            or (self._pending and element.type != self._pending[-1].type)
        )
        if self._pending and boundary:
            if self._references:
                self._references = analyze_markdown_text(
                    self._prose_source(), deepcopy(self._environment)
                ).needs_references
            if not self._references:
                if not line.strip():
                    self._pending.append(element)
                    return self._drain()
                out.extend(self._drain())
        if self._pending or (
            element.type in _PROSE and any(char in element.content for char in "`[<")
        ):
            self._pending.append(element)
            if element.type in _PROSE and not self._references:
                analysis = analyze_markdown_text(
                    self._prose_source(), deepcopy(self._environment)
                )
                self._references = analysis.needs_references
                if not analysis.needs_references and not analysis.incomplete:
                    out.extend(self._drain())
            return out
        if element.type in _PROSE:
            element.content = clean_markdown_text(element.content)
        return out + ([element] if element.content else [])

    def flush(self) -> list[FormattedElement]:
        """Finish a turn; repeated flushes are empty."""
        out: list[FormattedElement] = []
        if self._line:
            remaining, self._line = self._line, ""
            out.extend(self._line_piece(remaining, final=True))
        if self._leading:
            out.append(FormattedElement(content=self._leading, type="text", number=0))
            self._leading = ""
        return out + self._drain()

    def _groups(self) -> list[list[FormattedElement]]:
        groups: list[list[FormattedElement]] = []
        for element in self._pending:
            if (
                groups
                and element.type in _PROSE
                and element.type == groups[-1][-1].type
                and element.number == groups[-1][-1].number
            ):
                groups[-1].append(element)
            else:
                groups.append([element])
        return groups

    def _prose_source(self) -> str:
        return "\n\n".join(
            "".join(element.content for element in group)
            for group in self._groups()
            if group[0].type in _PROSE
        )

    def _drain(self) -> list[FormattedElement]:
        if not self._pending:
            return []
        out: list[FormattedElement] = []
        # Commit reference definitions only when the prose grammar is complete.
        # The same environment resolves links in later, already-streamed pieces.
        clean_markdown_text(self._prose_source(), self._environment)
        groups = self._groups()
        for group in groups:
            first = group[0]
            source = "".join(element.content for element in group)
            content = (
                clean_markdown_text(source, self._environment)
                if first.type in _PROSE
                else source
            )
            if content:
                out.append(
                    FormattedElement(
                        content=content, type=first.type, number=first.number
                    )
                )
        self._pending.clear()
        self._references = False
        return out


class PreserveMarkerFilter:
    """String projection of the same typed cleanup used for lesson delivery."""

    def __init__(self) -> None:
        """Start one source-preserving projection."""
        self._formatter = PreserveMarkerFormatter()

    def feed(self, text: str) -> str:
        """Release safely classified content in stream order."""
        return "".join(element.content for element in self._formatter.process(text))

    def flush(self) -> str:
        """Release a final partial line and any ambiguous Markdown suffix."""
        return "".join(element.content for element in self._formatter.flush())
