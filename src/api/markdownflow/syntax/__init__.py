"""MarkdownFlow syntax: blocks, interactions, variables, escaping and stream formatting.

Taken from the parsing layer of the external ``markdown-flow`` 0.4.2 package so the
engine and the application share one implementation. The package's 1.0 LLM
execution flow and providers are not part of it.
"""

from .constants import USER_ANSWER_CONTEXT_KEY
from .document import MarkdownFlowDocument
from .enums import BlockType
from .escaping import (
    escape_interaction_text,
    find_unescaped,
    unescape_interaction_text,
)
from .formatter.stream import StreamFormatter
from .models import Block
from .parser.interaction import InteractionParser, InteractionType
from .parser.variable import extract_variables_from_text, replace_variables_in_text
from .variable_names import normalize_variable_name

__all__ = [
    "USER_ANSWER_CONTEXT_KEY",
    "Block",
    "BlockType",
    "InteractionParser",
    "InteractionType",
    "MarkdownFlowDocument",
    "StreamFormatter",
    "escape_interaction_text",
    "extract_variables_from_text",
    "find_unescaped",
    "normalize_variable_name",
    "replace_variables_in_text",
    "unescape_interaction_text",
]
