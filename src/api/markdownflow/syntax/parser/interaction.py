"""Interaction Parser Module.

Provides three-layer interaction parsing for MarkdownFlow ?[] format validation,
variable detection, and content parsing.
"""

from enum import Enum
from typing import Any

from markdownflow.syntax.escaping import (
    find_unescaped,
    split_on_ellipsis,
    split_on_single_pipe,
    split_unescaped,
    unescape_interaction_text,
)
from markdownflow.syntax.variable_names import (
    find_interaction_spans,
    read_interaction_variable,
)


class InteractionType(Enum):
    """Interaction input type enumeration."""

    TEXT_ONLY = "text_only"  # Text input only: ?[{{var}}...question]
    BUTTONS_ONLY = "buttons_only"  # Button selection only: ?[{{var}} A|B]
    BUTTONS_WITH_TEXT = (
        "buttons_with_text"  # Buttons + text: ?[{{var}} A|B|...question]
    )
    BUTTONS_MULTI_SELECT = (
        "buttons_multi_select"  # Multi-select buttons: ?[{{var}} A||B]
    )
    BUTTONS_MULTI_WITH_TEXT = (
        "buttons_multi_with_text"  # Multi-select + text: ?[{{var}} A||B||...question]
    )
    NON_ASSIGNMENT_BUTTON = (
        "non_assignment_button"  # Display buttons: ?[Continue|Cancel]
    )


class InteractionParser:
    """Three-layer interaction parser for ?[] blocks.

    It validates the format, detects the variable and parses the content.
    """

    def __init__(self) -> None:
        """Initialize parser."""

    def parse(self, content: str) -> dict[str, Any]:
        """Parse one interaction block.

        Args:
            content: Raw interaction block content

        Returns:
            Standardized parsing result with type, variable, buttons, and question fields

        """
        try:
            # Layer 1: Validate basic format
            inner_content = self._layer1_validate_format(content)
            if inner_content is None:
                return self._create_error_result(
                    f"Invalid interaction format: {content}"
                )

            # Layer 2: Variable detection. It returns a name exactly when it found a
            # variable; an invalid name raises instead.
            _, variable_name, remaining_content = self._layer2_detect_variable(
                inner_content
            )

            # Layer 3: Specific content parsing
            if variable_name is not None:
                return self._layer3_parse_variable_interaction(
                    variable_name, remaining_content
                )
            return self._layer3_parse_display_buttons(inner_content)

        except Exception as e:
            return self._create_error_result(f"Parsing error: {e!s}")

    def _layer1_validate_format(self, content: str) -> str | None:
        """Layer 1: Validate ?[] format and extract content.

        Args:
            content: Raw content

        Returns:
            Extracted bracket content, None if validation fails

        """
        content = content.strip()
        spans = list(find_interaction_spans(content))
        if spans != [(0, len(content))]:
            return None  # type: ignore[unreachable]
        return content[2:-1]

    def _layer2_detect_variable(
        self, inner_content: str
    ) -> tuple[bool, str | None, str]:
        """Layer 2: Detect a leading `{{var}}` binding, with or without the legacy `%`.

        Args:
            inner_content: Content extracted from layer 1

        Returns:
            Tuple of (has_variable, variable_name, remaining_content)

        """
        marker = read_interaction_variable(inner_content)
        if marker is None:
            # No variable, use entire content for display button parsing
            return False, None, inner_content
        if marker.name is None:
            msg = "Invalid variable name"
            raise ValueError(msg)
        return True, marker.name, inner_content[marker.end :].strip()

    def _layer3_parse_variable_interaction(
        self, variable_name: str, content: str
    ) -> dict[str, Any]:
        """Layer 3: Parse variable interactions (variable assignment type).

        Args:
            variable_name: Variable name
            content: Content after variable

        Returns:
            Parsing result dictionary

        """
        # Detect ... separator, ignoring any an option escaped.
        ellipsis = split_on_ellipsis(content)

        if ellipsis is not None:
            # Has ... separator
            before_ellipsis = ellipsis[0].strip()
            question = unescape_interaction_text(ellipsis[1]).strip()

            if before_ellipsis:
                # Has prefix content (buttons or single option) + text input
                buttons, is_multi_select = self._parse_buttons(before_ellipsis)
                interaction_type = (
                    InteractionType.BUTTONS_MULTI_WITH_TEXT
                    if is_multi_select
                    else InteractionType.BUTTONS_WITH_TEXT
                )
                return {
                    "type": interaction_type,
                    "variable": variable_name,
                    "buttons": buttons,
                    "question": question,
                    "is_multi_select": is_multi_select,
                }
            # Pure text input
            return {
                "type": InteractionType.TEXT_ONLY,
                "variable": variable_name,
                "question": question,
                "is_multi_select": False,
            }
        # No ... separator
        if content and find_unescaped(content, "|") >= 0:  # type: ignore[unreachable]
            # Pure button group
            buttons, is_multi_select = self._parse_buttons(content)
            interaction_type = (
                InteractionType.BUTTONS_MULTI_SELECT
                if is_multi_select
                else InteractionType.BUTTONS_ONLY
            )
            return {
                "type": interaction_type,
                "variable": variable_name,
                "buttons": buttons,
                "is_multi_select": is_multi_select,
            }
        if content:  # type: ignore[unreachable]
            # Single button
            button = self._parse_single_button(content)
            return {
                "type": InteractionType.BUTTONS_ONLY,
                "variable": variable_name,
                "buttons": [button],
                "is_multi_select": False,
            }
        # Pure text input (no hint)
        return {
            "type": InteractionType.TEXT_ONLY,
            "variable": variable_name,
            "question": "",
            "is_multi_select": False,
        }

    def _layer3_parse_display_buttons(self, content: str) -> dict[str, Any]:
        """Layer 3: Parse non-assignment interactions (no variable).

        Mirrors the variable branch: supports button groups (single/multi
        select) and the `...` text-input suffix. The collected answer is not
        assigned to a variable; callers feed it back into the conversation
        context instead.

        Args:
            content: Content to parse

        Returns:
            Parsing result dictionary

        """
        if not content:
            # Empty content: ?[]
            return {
                "type": InteractionType.NON_ASSIGNMENT_BUTTON,
                "buttons": [{"display": "", "value": ""}],
            }

        ellipsis = split_on_ellipsis(content)
        if ellipsis is not None:
            before_ellipsis = ellipsis[0].strip()
            question = unescape_interaction_text(ellipsis[1]).strip()

            if before_ellipsis:
                # Buttons + text input: ?[A | B | ...question]
                buttons, is_multi_select = self._parse_buttons(before_ellipsis)
                return {
                    "type": InteractionType.NON_ASSIGNMENT_BUTTON,
                    "buttons": buttons,
                    "question": question,
                    "is_multi_select": is_multi_select,
                }
            # Pure text input: ?[...question]
            return {
                "type": InteractionType.NON_ASSIGNMENT_BUTTON,
                "buttons": [],
                "question": question,
                "is_multi_select": False,
            }

        if find_unescaped(content, "|") >= 0:  # type: ignore[unreachable]
            # Button group: ?[A | B] or ?[A || B]
            buttons, is_multi_select = self._parse_buttons(content)
            return {
                "type": InteractionType.NON_ASSIGNMENT_BUTTON,
                "buttons": buttons,
                "is_multi_select": is_multi_select,
            }
        # Single button
        button = self._parse_single_button(content)
        return {
            "type": InteractionType.NON_ASSIGNMENT_BUTTON,
            "buttons": [button],
            "is_multi_select": False,
        }

    def _parse_buttons(self, content: str) -> tuple[list[dict[str, str]], bool]:
        """Parse button group with fault tolerance.

        Args:
            content: Button content separated by | or ||

        Returns:
            Tuple of (button list, is_multi_select)

        """
        if not content or not isinstance(content, str):
            return [], False

        _, is_multi_select = self._detect_separator_type(content)

        buttons = []
        try:
            # Use different splitting logic based on separator type
            if is_multi_select:
                # Multi-select mode: split on ||, preserve single |
                button_parts = split_unescaped(content, "||")
            else:
                # Single-select mode: split on single |, but preserve ||
                button_parts = split_on_single_pipe(content)

            for button_text in button_parts:
                button_text = button_text.strip()  # noqa: PLW2901
                if button_text:
                    button = self._parse_single_button(button_text)
                    buttons.append(button)
        except (TypeError, ValueError):
            # Fallback to treating entire content as single button
            whole = unescape_interaction_text(content).strip()
            return [{"display": whole, "value": whole}], False

        # For empty content (like just separators), return empty list
        if not buttons and (content.strip() == "||" or content.strip() == "|"):
            return [], is_multi_select

        # Ensure at least one button exists (but only if there's actual content)
        if not buttons and content.strip():
            whole = unescape_interaction_text(content).strip()
            buttons = [{"display": whole, "value": whole}]

        return buttons, is_multi_select

    def _parse_single_button(self, button_text: str) -> dict[str, str]:
        """Parse single button with fault tolerance, supports Button//value format.

        Args:
            button_text: Button text

        Returns:
            Dictionary with display and value keys

        """
        if not button_text or not isinstance(button_text, str):
            return {"display": "", "value": ""}

        button_text = button_text.strip()
        if not button_text:
            return {"display": "", "value": ""}

        try:
            # Detect Button//value format - split only on the first unescaped //
            at = find_unescaped(button_text, "//")
            if at >= 0:
                display = unescape_interaction_text(button_text[:at]).strip()
                # Don't strip value to preserve intentional spacing/formatting
                value = unescape_interaction_text(button_text[at + 2 :])
                return {"display": display, "value": value}
        except (ValueError, IndexError):
            # Fallback: use text as both display and value
            pass

        resolved = unescape_interaction_text(button_text)
        return {"display": resolved, "value": resolved}

    def _detect_separator_type(self, content: str) -> tuple[str, bool]:
        """Detect separator type and whether it's multi-select.

        Implements fault tolerance: first separator type encountered determines the behavior.
        Mixed separators are handled by treating the rest as literal text.

        Args:
            content: Button content to analyze

        Returns:
            Tuple of (separator, is_multi_select) where separator is '|' or '||'

        """
        if not content or not isinstance(content, str):
            return "|", False

        # Find first occurrence of separators. A bar an option escaped is not one.
        single_pos = find_unescaped(content, "|")
        double_pos = find_unescaped(content, "||")

        # If no separators found
        if single_pos == -1 and double_pos == -1:
            return "|", False

        # If only single separator found
        if double_pos == -1:
            return "|", False

        # If only double separator found
        if single_pos == -1:
            return "||", True

        # Both found - fault tolerance: first occurrence wins
        # This handles mixed cases like "A||B|C" (multi-select) and "A|B||C" (single-select)
        if double_pos <= single_pos:
            return "||", True
        return "|", False

    def _create_error_result(self, error_message: str) -> dict[str, Any]:
        """Create error result.

        Args:
            error_message: Error message

        Returns:
            Error result dictionary

        """
        return {"type": None, "error": error_message}  # type: ignore[unreachable]
