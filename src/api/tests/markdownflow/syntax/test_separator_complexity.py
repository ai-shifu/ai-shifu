"""Keep document separators compatible and bounded on malformed input."""

import re
import subprocess
import sys

import pytest
from markdownflow import MarkdownFlowDocument
from markdownflow.syntax.constants import BLOCK_SEPARATOR
from markdownflow.syntax.document import _find_block_separator_spans


@pytest.mark.parametrize(
    "source",
    [
        "First\n---\nSecond",
        "First\n\n \t---\r\n\n  Second",
        "First\r\n\t---\r\nSecond",
        "First\n\v\f\u2003---\u2003\n\tSecond",
        "First\n--- \tSecond\nThird",
        "First\n----\nSecond\n---\nThird",
        "First\n---\n---\nSecond",
        "First\n\n---\n\n---\n\nSecond",
        "First\n---",
        "---\nSecond",
    ],
)
def test_separator_spans_preserve_whitespace_and_nonoverlap(source: str) -> None:
    assert list(_find_block_separator_spans(source)) == [
        match.span() for match in re.finditer(BLOCK_SEPARATOR, source)
    ]


def test_separator_inside_raw_html_remains_protected() -> None:
    source = "<script>\nFirst\n---\nSecond\n</script>\n\n---\n\nLast"
    assert [
        block.content for block in MarkdownFlowDocument(source).get_all_blocks()
    ] == [
        "<script>\nFirst\n---\nSecond\n</script>",
        "Last",
    ]


def test_long_blank_line_near_misses_finish_within_process_deadline() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from markdownflow import MarkdownFlowDocument; "
            "source = '\\n' * 200000 + '---x\\nTail'; "
            "blocks = MarkdownFlowDocument(source).get_all_blocks(); "
            "assert [block.content for block in blocks] == ['---x\\nTail']",
        ],
        check=True,
        timeout=20,
    )
