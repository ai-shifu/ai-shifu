"""Line-level Classifier.

State machine that classifies each line of content into an ElementType.
Mirrors Go formatter/classifier.go.
"""

from enum import IntEnum

from markdownflow.syntax.parser.code_fence_utils import (
    CodeFenceInfo,
    is_code_fence_end,
    parse_code_fence_start,
)

from .patterns import (
    block_html_open_re,
    diff_fence_re,
    display_math_re,
    doctype_re,
    heading_re,
    html_close_re,
    html_close_tag_re,
    html_img_re,
    html_link_re,
    html_open_tag_re,
    image_line_re,
    inline_math_line_re,
    script_close_re,
    style_close_re,
    svg_close_re,
    svg_open_re,
    table_row_re,
)
from .types import ClassifyResult, ElementType


class _State(IntEnum):
    TEXT = 0
    CODE_FENCE = 1
    HTML_BLOCK = 2
    SVG_BLOCK = 3
    TABLE = 4
    DOCTYPE = 5
    DIFF = 6
    LATEX_BLOCK = 7


class Classifier:
    """Line-level classifier maintaining a state machine."""

    def __init__(self) -> None:
        """Start in plain text with no open fence."""
        self._state: _State = _State.TEXT
        # Code fence state
        self._code_fence: CodeFenceInfo | None = None
        self._code_fence_type: str = ElementType.CODE
        # HTML block state
        self._html_tag: str = ""
        self._html_depth: int = 0
        # Table state
        self._table_confirmed: bool = False

    def classify_line(self, line: str) -> ClassifyResult:
        """Classify a single line, returning a ClassifyResult."""
        if self._state == _State.CODE_FENCE:
            return self._handle_code_fence(line)
        if self._state == _State.SVG_BLOCK:
            return self._handle_svg_block(line)
        if self._state == _State.HTML_BLOCK:
            return self._handle_html_block(line)
        if self._state == _State.DOCTYPE:
            return self._handle_doctype(line)
        if self._state == _State.TABLE:
            return self._handle_table(line)
        if self._state == _State.DIFF:
            return self._handle_diff(line)
        if self._state == _State.LATEX_BLOCK:
            return self._handle_latex_block(line)
        return self._handle_text(line)

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _handle_code_fence(self, line: str) -> ClassifyResult:
        if self._code_fence is not None and is_code_fence_end(line, self._code_fence):
            t = self._code_fence_type
            self._state = _State.TEXT
            self._code_fence = None
            self._code_fence_type = ""
            return ClassifyResult(type=t, is_continuation=True)
        return ClassifyResult(type=self._code_fence_type, is_continuation=True)

    def _handle_svg_block(self, line: str) -> ClassifyResult:
        if svg_close_re.search(line):
            self._state = _State.TEXT
        return ClassifyResult(type=ElementType.SVG, is_continuation=True)

    def _handle_html_block(self, line: str) -> ClassifyResult:
        tag = self._html_tag

        # style / script / iframe use dedicated close detection
        if tag == "style":
            if style_close_re.search(line):
                self._state = _State.TEXT
                self._html_tag = ""
                self._html_depth = 0
            return ClassifyResult(type=ElementType.HTML, is_continuation=True)

        if tag == "script":
            if script_close_re.search(line):
                self._state = _State.TEXT
                self._html_tag = ""
                self._html_depth = 0
            return ClassifyResult(type=ElementType.HTML, is_continuation=True)

        if tag == "iframe":
            if "</iframe>" in line.lower():
                self._state = _State.TEXT
                self._html_tag = ""
                self._html_depth = 0
            return ClassifyResult(type=ElementType.HTML, is_continuation=True)

        # Generic block HTML: track nesting depth
        for m in html_open_tag_re.finditer(line):
            if m.group(1).lower() == tag:
                self._html_depth += 1
        for m in html_close_tag_re.finditer(line):
            if m.group(1).lower() == tag:
                self._html_depth -= 1
                self._html_depth = max(self._html_depth, 0)

        if self._html_depth <= 0:
            self._state = _State.TEXT
            self._html_tag = ""
            self._html_depth = 0

        return ClassifyResult(type=ElementType.HTML, is_continuation=True)

    def _handle_doctype(self, line: str) -> ClassifyResult:
        if html_close_re.search(line):
            self._state = _State.TEXT
        return ClassifyResult(type=ElementType.HTML, is_continuation=True)

    def _handle_table(self, line: str) -> ClassifyResult:
        if table_row_re.match(line):
            self._table_confirmed = True
            return ClassifyResult(type=ElementType.TABLES, is_continuation=True)
        # No longer a table row, table ends
        self._state = _State.TEXT  # type: ignore[unreachable]
        self._table_confirmed = False
        return self._handle_text(line)

    def _handle_diff(self, line: str) -> ClassifyResult:
        if diff_fence_re.match(line):
            self._state = _State.TEXT
        return ClassifyResult(type=ElementType.DIFF, is_continuation=True)

    def _handle_latex_block(self, line: str) -> ClassifyResult:
        if display_math_re.match(line):
            self._state = _State.TEXT
        return ClassifyResult(type=ElementType.LATEX, is_continuation=True)

    # ------------------------------------------------------------------
    # Text state: detect new block starts (12 steps)
    # ------------------------------------------------------------------

    def _handle_text(self, line: str) -> ClassifyResult:
        trimmed = line.strip()

        # Empty line stays text
        if trimmed == "":
            return ClassifyResult(type=ElementType.TEXT)

        # 1. Code fence start
        fence = parse_code_fence_start(line)
        if fence is not None:
            self._state = _State.CODE_FENCE
            self._code_fence = fence

            # Distinguish mermaid from code via info string
            info_str = fence.line.lstrip(" ").lstrip(fence.char).strip()
            if info_str.lower().startswith("mermaid"):
                self._code_fence_type = ElementType.MERMAID
            else:
                self._code_fence_type = ElementType.CODE
            return ClassifyResult(type=self._code_fence_type)

        # 2. Diff fence
        if diff_fence_re.match(line):
            self._state = _State.DIFF
            return ClassifyResult(type=ElementType.DIFF)

        # 3. Display math ($$)
        if display_math_re.match(line):  # type: ignore[unreachable]
            self._state = _State.LATEX_BLOCK
            return ClassifyResult(type=ElementType.LATEX)

        # 4. <!DOCTYPE html>
        if doctype_re.match(line):
            self._state = _State.DOCTYPE
            if html_close_re.search(line):
                self._state = _State.TEXT
            return ClassifyResult(type=ElementType.HTML)

        # 5. <svg
        if svg_open_re.search(line):
            self._state = _State.SVG_BLOCK
            if svg_close_re.search(line):
                self._state = _State.TEXT
            return ClassifyResult(type=ElementType.SVG)

        # 6. HTML <img> tag
        if html_img_re.match(line):
            return ClassifyResult(type=ElementType.IMG)

        # 6.5 HTML <link> tag (void element, append to previous HTML block)
        if html_link_re.match(line):
            return ClassifyResult(type=ElementType.HTML, is_append=True)

        # 7. Block-level HTML open tag
        m = block_html_open_re.match(line)
        if m:
            tag_name = m.group(1).lower()

            # script/style mark IsAppend, attaching to previous html block
            is_append = tag_name in ("script", "style")

            self._state = _State.HTML_BLOCK
            self._html_tag = tag_name
            self._html_depth = 1

            # Check if close tag is on the same line
            for cm in html_close_tag_re.finditer(line):
                if cm.group(1).lower() == tag_name:
                    self._html_depth -= 1
                    self._html_depth = max(self._html_depth, 0)
            if self._html_depth <= 0:
                self._state = _State.TEXT
                self._html_tag = ""
                self._html_depth = 0

            return ClassifyResult(type=ElementType.HTML, is_append=is_append)

        # 8. Markdown table row
        if table_row_re.match(line):
            self._state = _State.TABLE
            self._table_confirmed = False
            return ClassifyResult(type=ElementType.TABLES)

        # 9. Markdown image ![alt](url)
        if image_line_re.match(line):
            return ClassifyResult(type=ElementType.IMG)

        # 10. Inline LaTeX (whole line $...$)
        if inline_math_line_re.match(line):
            return ClassifyResult(type=ElementType.LATEX)

        # 11. Markdown heading
        if heading_re.match(line):
            return ClassifyResult(type=ElementType.TITLE)

        # 12. Default -> text
        return ClassifyResult(type=ElementType.TEXT)
