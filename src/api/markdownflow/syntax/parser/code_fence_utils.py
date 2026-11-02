"""Code Fence Utilities.

Provides CommonMark-compliant code fence parsing utility functions.
"""

from dataclasses import dataclass

from markdownflow.syntax.constants import (
    COMPILED_CODE_FENCE_END_REGEX,
    COMPILED_CODE_FENCE_START_REGEX,
)


@dataclass
class CodeFenceInfo:
    """Code fence information.

    Used to track the opening fence of a code block for proper matching with closing fence.

    Attributes:
        char: Fence character ('`' or '~')
        length: Fence length (≥3)
        indent: Number of indent spaces (≤3)
        line: Full opening fence line (including info string, e.g., language identifier)

    """

    char: str
    length: int
    indent: int
    line: str


def validate_fence_characters(fence_str: str) -> bool:
    """Validate that all characters in the fence string are the same.

    CommonMark specification: fence must consist of the same character (all ` or all ~)

    Args:
        fence_str: Fence string (e.g., "```" or "~~~~")

    Returns:
        True if all characters are the same, False otherwise

    Examples:
        >>> validate_fence_characters("```")
        True
        >>> validate_fence_characters("~~~~")
        True
        >>> validate_fence_characters("``~")
        False
        >>> validate_fence_characters("")
        False

    """
    if not fence_str:
        return False

    fence_char = fence_str[0]
    return all(ch == fence_char for ch in fence_str)


def parse_code_fence_start(line: str) -> CodeFenceInfo | None:
    """Parse code block opening fence marker.

    CommonMark specification:
      - 0-3 spaces indent
      - At least 3 consecutive ` or ~ characters
      - All characters must be the same
      - Optional info string (language identifier)

    Args:
        line: Line to detect

    Returns:
        CodeFenceInfo if valid opening fence marker, None otherwise

    Examples:
        >>> parse_code_fence_start("```")
        CodeFenceInfo(char='`', length=3, ...)
        >>> parse_code_fence_start("```go")
        CodeFenceInfo(char='`', length=3, line="```go", ...)
        >>> parse_code_fence_start("   ~~~python")
        CodeFenceInfo(char='~', length=3, indent=3, ...)
        >>> parse_code_fence_start("    ```")
        None  # indent > 3
        >>> parse_code_fence_start("``~")
        None  # mixed characters

    """
    match = COMPILED_CODE_FENCE_START_REGEX.match(line)
    if not match:
        return None  # type: ignore[unreachable]

    # match.group(1) is the fence string (e.g., ```, ~~~~)
    # match.group(2) is the info string (e.g., go, python)
    fence_str = match.group(1)

    # Validate all characters are the same (backticks or tildes)
    if not validate_fence_characters(fence_str):
        return None  # type: ignore[unreachable]

    # Calculate indent
    indent = len(line) - len(line.lstrip(" "))

    # Validate indent ≤ 3 (CommonMark specification)
    if indent > 3:
        return None

    # Fence length
    fence_length = len(fence_str)

    # Validate fence length ≥ 3 (regex already ensures this, but check to be safe)
    if fence_length < 3:
        return None  # type: ignore[unreachable]

    return CodeFenceInfo(
        char=fence_str[0],
        length=fence_length,
        indent=indent,
        line=line,
    )


def is_code_fence_end(line: str, start_fence: CodeFenceInfo) -> bool:
    """Detect if line is a matching code block closing fence marker.

    CommonMark specification:
      - Use same type of fence character (` or ~)
      - Fence length ≥ opening fence
      - 0-3 spaces indent
      - Only contains fence characters and whitespace

    Args:
        line: Line to detect
        start_fence: Opening fence information

    Returns:
        Whether line is a matching closing fence

    Examples:
        >>> start = CodeFenceInfo(char='`', length=3, indent=0, line="```")
        >>> is_code_fence_end("```", start)
        True
        >>> is_code_fence_end("````", start)
        True  # length ≥ opening fence
        >>> is_code_fence_end("~~~", start)
        False  # character type mismatch
        >>> is_code_fence_end("``", start)
        False  # length < opening fence
        >>> is_code_fence_end("    ```", start)
        False  # indent > 3

    """
    match = COMPILED_CODE_FENCE_END_REGEX.match(line)
    if not match:
        return False  # type: ignore[unreachable]

    # Extract indent
    indent = len(line) - len(line.lstrip(" "))

    # Validate indent ≤ 3
    if indent > 3:
        return False  # type: ignore[unreachable]

    # Extract fence string (remove indent and trailing whitespace)
    fence_str = line.strip()

    # Validate non-empty
    if not fence_str:
        return False

    first_char = fence_str[0]

    # Character type must match
    if first_char != start_fence.char:
        return False  # type: ignore[unreachable]

    # Calculate fence length (count consecutive same characters)
    fence_length = 0
    for ch in fence_str:
        if ch == first_char:
            fence_length += 1
        else:
            # Contains other characters, not a valid closing fence
            return False

    # Length must be ≥ opening fence
    return fence_length >= start_fence.length
