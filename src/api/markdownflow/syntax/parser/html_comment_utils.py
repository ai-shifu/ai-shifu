"""HTML Comment Utilities.

Provides functions to detect and manipulate HTML comments in MarkdownFlow documents.
"""


class HTMLCommentInfo:
    """Store HTML comment information."""

    def __init__(self, start_line: str) -> None:
        """Initialize HTML comment info.

        Args:
            start_line: The line where the comment starts

        """
        self.start_line = start_line


def is_html_comment_start(line: str) -> tuple[HTMLCommentInfo | None, bool]:
    """Detect HTML comment start.

    Returns:
        tuple[info, is_single_line]:
            - info: Comment info if this is a comment start (single or multi-line), None otherwise
            - is_single_line: True if this is a single-line comment (closed on same line)

    Behavior:
        - Single-line comment (closed on same line): returns (info, True) - needs extraction
        - Multi-line comment start: returns (info, False) - needs extraction
        - No comment: returns (None, False)

    Examples:
        >>> is_html_comment_start("<!-- single line -->")
        (HTMLCommentInfo(...), True)
        >>> is_html_comment_start("<!-- multi-line start")
        (HTMLCommentInfo(...), False)
        >>> is_html_comment_start("normal text")
        (None, False)

    """
    # Check if line contains comment start marker
    if "<!--" not in line:
        return None, False

    # Find start and end marker positions
    start_idx = line.find("<!--")
    end_idx = line.find("-->", start_idx)

    info = HTMLCommentInfo(start_line=line)

    # Single-line comment (closed on same line) - also needs extraction
    if end_idx != -1:
        return info, True

    # Multi-line comment start
    return info, False


def is_html_comment_end(line: str) -> bool:
    """Detect HTML comment end.

    Args:
        line: Line to check

    Returns:
        True if line contains comment end marker -->
        False otherwise

    Examples:
        >>> is_html_comment_end("comment end -->")
        True
        >>> is_html_comment_end("-->")
        True
        >>> is_html_comment_end("normal text")
        False

    """
    return "-->" in line


def remove_inline_comment(line: str) -> str:
    """Remove inline single-line comment, preserving other content.

    Args:
        line: Line containing single-line comment

    Returns:
        Line with comment removed

    Examples:
        >>> remove_inline_comment("prefix <!-- comment --> suffix")
        'prefix  suffix'
        >>> remove_inline_comment("===Title=== <!-- comment -->")
        '===Title=== '
        >>> remove_inline_comment("<!-- comment -->")
        ''

    """
    start_idx = line.find("<!--")
    if start_idx == -1:
        return line

    end_idx = line.find("-->", start_idx)
    if end_idx == -1:
        return line

    # Calculate actual end position (relative to full line)
    actual_end_idx = end_idx + 3  # 3 is length of "-->"

    # Concatenate content before and after comment
    before = line[:start_idx]
    after = line[actual_end_idx:] if actual_end_idx < len(line) else ""

    return before + after
