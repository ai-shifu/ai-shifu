"""Project authored source out of recognized legacy generation prompts."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

from markdown_flow import MarkdownFlow, replace_variables_in_text
from markdown_flow.constants import NEXT_INTERACTION_CONTEXT_INTRO

from .agent.engine.script_comments import strip_comments

if TYPE_CHECKING:
    from collections.abc import Callable

_VARIABLE = re.compile(r"(?<!%)\{\{([^{}]+)\}\}")
_OUTPUT_LANGUAGE = re.compile(
    r"\A<output_language_instruction>\n🚨 OUTPUT: 100% ([^\r\n]+?) - "
    r"Translate ALL non-\1 words/phrases to \1 🚨\n"
    r"</output_language_instruction>\n\n"
)


def _project_template(
    prompt: str,
    source: str,
    render: Callable[[str, dict[str, str]], str],
) -> str | None:
    """Recover only unambiguous quoted substitutions, then prove their rendering."""
    markers = {
        name: f"MDFLOW_HISTORY_{uuid4().hex}"
        for match in _VARIABLE.finditer(source)
        if (name := match[1].strip())
    }
    template = render(source, markers)
    marker_names = {marker: name for name, marker in markers.items()}
    marker_pattern = "|".join(re.escape(marker) for marker in marker_names)
    captures: list[str] = []
    parts: list[str] = []
    cursor = 0
    for match in re.finditer(marker_pattern, template) if marker_pattern else ():
        # Unquoted preserved values and embedded triple quotes cannot be inverted
        # without an original variable snapshot. Keep those saved prompts intact.
        if (
            template[max(0, match.start() - 3) : match.start()] != '"""'
            or template[match.end() : match.end() + 3] != '"""'
        ):
            return None
        parts.append(re.escape(template[cursor : match.start()]))
        parts.append('((?:(?!""").)*)')
        captures.append(marker_names[match[0]])
        cursor = match.end()
    parts.append(re.escape(template[cursor:]))
    match = re.fullmatch("".join(parts), prompt, re.DOTALL)
    if match is None:
        return None
    values: dict[str, str] = {}
    for name, value in zip(captures, match.groups(), strict=True):
        if name in values and values[name] != value:
            return None
        values[name] = value
    if render(source, values) != prompt:
        return None
    return render(strip_comments(source), values)


def project_legacy_generation_prompt(
    prompt: str,
    source: str,
    *,
    document: str,
    block_index: int,
) -> str:
    """Copy a proven host prompt with comments removed before substitution.

    ``source`` is the parsed block snapshot persisted alongside this prompt. The
    original row remains evidence; only the next request's projection changes.
    Never filter rendered text wholesale: learner substitutions can themselves
    contain literal HTML comments. Unrecognized or ambiguous historical prompts
    remain byte-identical, as does the separately rendered next-interaction note.
    """
    if not source:
        return prompt
    if "__MDFLOW_" in source:
        original = MarkdownFlow(document, llm_provider=None)
        blocks = original.get_all_blocks()
        if 0 <= block_index < len(blocks) and blocks[block_index].content == source:
            source = original._preprocessor.restore_code_blocks(source)
    if strip_comments(source) == source:
        return prompt

    language_match = _OUTPUT_LANGUAGE.match(prompt)
    language = language_match[1] if language_match else None

    def render_native(text: str, values: dict[str, str]) -> str:
        flow = MarkdownFlow(text, llm_provider=None)
        blocks = flow.get_all_blocks()
        if not blocks:
            return ""
        if len(blocks) != 1:
            # A block snapshot must not acquire a different block layout.
            return ""
        if language:
            flow.set_output_language(language)
        return flow._build_content_messages(0, values)[-1]["content"]

    separator = "\n\n" + NEXT_INTERACTION_CONTEXT_INTRO
    prefix, marker, suffix = prompt.rpartition(separator)
    if not marker:
        prefix = prompt
    projected = _project_template(prefix, source, render_native)
    if projected is not None:
        return projected + (marker + suffix if marker else "")

    # Preserved-content streams have no LLMResult.prompt. Their host fallback
    # stores the variables-rendered block source without native prompt wrappers.
    projected = _project_template(prompt, source, replace_variables_in_text)
    return projected if projected is not None else prompt
