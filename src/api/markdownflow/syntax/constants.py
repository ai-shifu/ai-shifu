"""Shared MarkdownFlow syntax constants."""

import re

COMPILED_VARIABLE_NAME_PLACEHOLDER_REGEX = re.compile(r"\x00mdf-name:+[0-9]+\x00")

# Inline HTML owns braces in its tag source before document-level MDF scanning.
_HTML_SPACE = r"[ \t\r\n]"

_HTML_ATTRIBUTE = (
    r"[A-Za-z_:][A-Za-z0-9_.:-]*(?:"
    + _HTML_SPACE
    + r"*="
    + _HTML_SPACE
    + r"*(?:[^ \t\r\n\"'=<>`]+|'[^']*'|\"[^\"]*\"))?"
)

COMPILED_INLINE_HTML_REGEX = re.compile(
    r"(?:<[A-Za-z][A-Za-z0-9-]*(?:"
    + _HTML_SPACE
    + r"+"
    + _HTML_ATTRIBUTE
    + r")*"
    + _HTML_SPACE
    + r"*/?>"
    r"|</[A-Za-z][A-Za-z0-9-]*" + _HTML_SPACE + r"*>"
    r"|<!--[\s\S]*?-->|<\?[\s\S]*?\?>|<![A-Z]+"
    + _HTML_SPACE
    + r"+[^>]*>|<!\[CDATA\[[\s\S]*?\]\]>)"
)

COMPILED_RAW_HTML_START_REGEX = re.compile(
    r" {0,3}<(script|style|pre|textarea)(?=[ \t\r\n\f>])", re.IGNORECASE
)

COMPILED_RAW_HTML_END_REGEX = {
    name: re.compile(r"</" + name + r"[ \t\r\n]*>", re.IGNORECASE)
    for name in ("script", "style", "pre", "textarea")
}

COMPILED_DOLLAR_RUN_REGEX = re.compile(r"\$+")

COMPILED_BLANK_LINE_REGEX = re.compile(
    r"(?:\r\n|\r(?!\n)|(?<!\r)\n)[ \t]*(?:\r\n|\r(?!\n)|(?<!\r)\n)"
)

COMPILED_ATX_START_REGEX = re.compile(r"^ {0,3}#{1,6}(?=[ \t\r\n]|$)", re.MULTILINE)

COMPILED_PHYSICAL_LINE_END_REGEX = re.compile(r"\r\n|\r|\n")

# Context message extension field carrying the user's answer to a
# non-assignment interaction. Stripped before messages reach the LLM.
USER_ANSWER_CONTEXT_KEY = "user_answer"

# Separators
BLOCK_SEPARATOR = r"\n\s*---\s*\n"

# Multiline preserved block fence: starts with '!' followed by 3 or more '='
PRESERVE_FENCE_PATTERN = r"^!={3,}\s*$"

COMPILED_PRESERVE_FENCE_REGEX = re.compile(PRESERVE_FENCE_PATTERN)

# Inline preserved content pattern: ===content=== format (historical compatibility)
INLINE_PRESERVE_PATTERN = r"^===(.+)=== *$"

COMPILED_INLINE_PRESERVE_REGEX = re.compile(INLINE_PRESERVE_PATTERN)


# Code fence patterns (CommonMark specification compliant)
# Code block fence start: 0-3 spaces + at least 3 backticks or tildes + optional info string
CODE_FENCE_START_PATTERN = r"^[ ]{0,3}([`~]{3,})(.*)$"

COMPILED_CODE_FENCE_START_REGEX = re.compile(CODE_FENCE_START_PATTERN)

# Code block fence end: 0-3 spaces + at least 3 backticks or tildes + optional whitespace
CODE_FENCE_END_PATTERN = r"^[ ]{0,3}([`~]{3,})\s*$"

COMPILED_CODE_FENCE_END_REGEX = re.compile(CODE_FENCE_END_PATTERN)

# Output instruction markers
OUTPUT_INSTRUCTION_PREFIX = "<原样输出>"

OUTPUT_INSTRUCTION_SUFFIX = "</原样输出>"

VARIABLE_DEFAULT_VALUE = "UNKNOWN"
