"""Markdown-Flow Enumeration Definitions.

Defines various enumeration types used throughout the system, including input types and block types.
"""

from enum import Enum


class BlockType(Enum):
    """Document block type enumeration.

    Defines different types of blocks identified during document parsing.
    """

    CONTENT = "content"  # Regular document content blocks
    INTERACTION = "interaction"  # Interactive blocks requiring user input
    PRESERVED_CONTENT = "preserved_content"  # Special blocks: inline !===content!=== or multiline !===...!===
