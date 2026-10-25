"""Published questionnaire validation and private profile transformation prompts."""

from __future__ import annotations

from typing import Any

from flaskr.service.profile_research.authored_interaction import authored_option_values
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
from markdown_flow import MarkdownFlow
from markdownflow.engine.marker_context import (
    analyze_marker_context,
    marker_syntax_source,
)
from markdownflow.engine.questions import find_interaction_spans
from markdownflow.engine.script import collected_questions
from markdownflow.engine.tools import _script_questions


def _profile_summary_prompt() -> str:
    research_source_prompt = load_prompt_template("profile_research_summary").strip()
    optimizer_prompt = load_prompt_template("learner_profile_optimizer").strip()
    return f"{research_source_prompt}\n\n{optimizer_prompt}"


def validate_profile_research_document(document: str) -> dict[str, Any]:
    """Validate the configured document with MarkdownFlow's own parser."""
    if not isinstance(document, str) or not document.strip():
        msg = "document is empty"
        raise ProfileResearchValidationError(msg)
    if len(document) > MAX_DOCUMENT_CODEPOINTS:
        msg = "document is too long"
        raise ProfileResearchValidationError(msg)
    authored_questions = _script_questions(document)
    context = analyze_marker_context(document, fence_indent=3)
    spans = list(
        find_interaction_spans(
            document, syntax_source=marker_syntax_source(document, context)
        )
    )
    # Only use the block SDK to count content outside native question spans.
    # Its legacy brace scanner must never authorize or hide Profile controls.
    content_count = 0
    offset = 0
    for start, end in [*spans, (len(document), len(document))]:
        content = document[offset:start]
        if content.strip():
            content_count += len(MarkdownFlow(document=content).get_all_blocks())
        offset = end
    interaction_count = len(authored_questions)
    block_count = content_count + interaction_count
    if not block_count:
        msg = "document has no blocks"
        raise ProfileResearchValidationError(msg)
    if block_count >= MAX_BLOCK_COUNT:
        msg = "document has too many blocks"
        raise ProfileResearchValidationError(msg)
    for question in authored_questions:
        if question.question and len(question.question) > MAX_INPUT_KEY_CODEPOINTS:
            msg = "interaction question is too long"
            raise ProfileResearchValidationError(msg)
        has_question = question.text and bool((question.placeholder or "").strip())
        buttons = [
            {"display": display, "value": value}
            for display, value in authored_option_values(question)
        ]
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
                question.multi
                and sum(len(value) for value in button_values)
                > MAX_INPUT_TOTAL_CODEPOINTS
            ):
                msg = "interaction options exceed runtime input limits"
                raise ProfileResearchValidationError(msg)
        if not has_question and not button_values:
            msg = "interaction has no answerable input"
            raise ProfileResearchValidationError(msg)
    return {
        "block_count": block_count,
        "interaction_block_count": interaction_count,
        "content_block_count": content_count,
        "questions": sorted(collected_questions(document)),
    }
