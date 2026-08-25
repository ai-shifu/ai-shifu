"""Official MarkdownFlow validation and profile-summary document assembly."""

from __future__ import annotations

from typing import Any

from flaskr.service.profile_research.session import (
    MAX_BLOCK_COUNT,
    MAX_DOCUMENT_CODEPOINTS,
    MAX_INPUT_KEY_CODEPOINTS,
    MAX_INPUT_TOTAL_CODEPOINTS,
    MAX_INPUT_VALUE_CODEPOINTS,
    MAX_INPUT_VALUE_COUNT,
    ProfileResearchValidationError,
)
from flaskr.util.prompt_loader import load_prompt_template
from markdown_flow import BlockType, InteractionParser, MarkdownFlow


def _profile_summary_prompt() -> str:
    research_source_prompt = load_prompt_template("profile_research_summary").strip()
    optimizer_prompt = load_prompt_template("learner_profile_optimizer").strip()
    return f"{research_source_prompt}\n\n{optimizer_prompt}"


def _append_profile_summary(document: str) -> str:
    return f"{document.rstrip()}\n\n---\n\n{_profile_summary_prompt()}"


def validate_profile_research_document(document: str) -> dict[str, Any]:
    """Validate the configured document with MarkdownFlow's own parser."""
    if not isinstance(document, str) or not document.strip():
        msg = "document is empty"
        raise ProfileResearchValidationError(msg)
    if len(document) > MAX_DOCUMENT_CODEPOINTS:
        msg = "document is too long"
        raise ProfileResearchValidationError(msg)
    flow = MarkdownFlow(document=document)
    blocks = flow.get_all_blocks()
    if not blocks:
        msg = "document has no blocks"
        raise ProfileResearchValidationError(msg)
    if len(blocks) >= MAX_BLOCK_COUNT:
        msg = "document has too many blocks"
        raise ProfileResearchValidationError(msg)
    interaction_count = sum(
        block.block_type == BlockType.INTERACTION for block in blocks
    )
    if interaction_count == 0:
        msg = "document must contain an interaction"
        raise ProfileResearchValidationError(msg)
    interaction_parser = InteractionParser()
    for block in blocks:
        if block.block_type != BlockType.INTERACTION:
            continue
        parsed_interaction = interaction_parser.parse(block.content)
        variable_name = parsed_interaction.get("variable")
        if (
            isinstance(variable_name, str)
            and len(variable_name) > MAX_INPUT_KEY_CODEPOINTS
        ):
            msg = "interaction variable name is too long"
            raise ProfileResearchValidationError(msg)
        question = parsed_interaction.get("question")
        has_question = isinstance(question, str) and bool(question.strip())
        buttons = parsed_interaction.get("buttons")
        button_values: list[str] = []
        if isinstance(buttons, list):
            if len(buttons) > MAX_INPUT_VALUE_COUNT:
                msg = "interaction options exceed runtime input limits"
                raise ProfileResearchValidationError(msg)
            for button in buttons:
                display = button.get("display") if isinstance(button, dict) else None
                value = button.get("value") if isinstance(button, dict) else None
                if (
                    not isinstance(display, str)
                    or not display.strip()
                    or not isinstance(value, str)
                    or not value.strip()
                ):
                    msg = "interaction has no answerable input"
                    raise ProfileResearchValidationError(msg)
                if len(value) > MAX_INPUT_VALUE_CODEPOINTS:
                    msg = "interaction options exceed runtime input limits"
                    raise ProfileResearchValidationError(msg)
                button_values.append(value)
            if (
                parsed_interaction.get("is_multi_select")
                and sum(len(value) for value in button_values)
                > MAX_INPUT_TOTAL_CODEPOINTS
            ):
                msg = "interaction options exceed runtime input limits"
                raise ProfileResearchValidationError(msg)
        if not has_question and not button_values:
            msg = "interaction has no answerable input"
            raise ProfileResearchValidationError(msg)
    return {
        "block_count": len(blocks),
        "interaction_block_count": interaction_count,
        "content_block_count": len(blocks) - interaction_count,
        "variables": list(flow.extract_variables()),
    }
