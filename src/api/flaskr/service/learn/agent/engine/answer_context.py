"""Project an exact, uniquely anchored authored section near a resumed answer."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import TYPE_CHECKING

from pydantic import ValidationError
from pydantic_ai.messages import ModelRequest, ToolCallPart, UserPromptPart

from .interaction import InteractionSpec
from .tools import _script_questions, normalize_script_text_input, script_text_inputs

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet

    from pydantic_ai.messages import ModelMessage

_FENCE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$")
_HEADING = re.compile(r"^[ ]{0,3}(#{1,6})(?:[ \t]+|$)")
_SECTION_BYTES = 8192


def _masked_lines(script: str) -> list[str]:
    """Hide comment/code syntax while retaining original character offsets."""
    masked = re.sub(
        r"<!--(?:.*?-->|.*\Z)",
        lambda match: "".join("\n" if c == "\n" else " " for c in match[0]),
        script,
        flags=re.DOTALL,
    )
    result = []
    opening = None
    for line in masked.splitlines(keepends=True):
        fence = _FENCE.match(line)
        hidden = opening is not None or fence or line.expandtabs(4).startswith("    ")
        if opening is not None:
            if (
                fence
                and fence[1][0] == opening[0]
                and len(fence[1]) >= len(opening)
                and not fence[2].strip()
            ):
                opening = None
        elif fence:
            opening = fence[1]
        result.append(
            "".join("\n" if c == "\n" else " " for c in line) if hidden else line
        )
    return result


def authored_answer_section(script: str, spec: InteractionSpec) -> str | None:
    """Return one whole authored section, or decline ambiguity and oversized context.

    Only exact standalone text-input hints in static sections qualify. Markdown heading ancestry and
    the next authored interaction bound the reference; they never move a cursor,
    choose a grade or define new requirements. Unsupported controls retain the
    full script without a focused copy.
    """
    if spec.type != "text" or not spec.placeholder:
        return None
    lines = _masked_lines(script)
    controls = []
    headings = []
    offset = 0
    for line in lines:
        if heading := _HEADING.match(line):
            headings.append((offset, len(heading[1])))
        if line.lstrip(" ").startswith("?["):
            questions = _script_questions(line)
            if len(questions) == 1:
                controls.append((offset, questions[0]))
        offset += len(line)
    # Multiline or inline controls cannot establish exact standalone boundaries.
    if len(_script_questions("".join(lines))) != len(controls):
        return None
    matches = [
        i
        for i, (_, q) in enumerate(controls)
        if q.text
        and not any(c.strip() for c in q.choices)
        and q.placeholder == spec.placeholder
        and q.variable == spec.variable
    ]
    if len(matches) != 1:
        return None
    index = matches[0]
    anchor = controls[index][0]
    next_control = controls[index + 1][0] if index + 1 < len(controls) else len(script)
    candidates = [(0, next_control)]
    for i, (start, level) in enumerate(headings):
        end = next(
            (pos for pos, depth in headings[i + 1 :] if depth <= level), len(script)
        )
        if start <= anchor < end:
            candidates.append((start, min(end, next_control)))
    candidates = [
        (start, end)
        for start, end in candidates
        if sum(start <= pos < end for pos, _ in controls) == 1
    ]
    if not candidates:
        return None
    start, end = max(candidates, key=lambda bounds: bounds[1] - bounds[0])
    section = script[start:end]
    # Do not re-render variables from a newer memory snapshot or reinsert an old
    # fact near the current answer. Existing script/memory handling remains in charge.
    if "{{" in section:
        return None
    # Do not clip a large section down to just its question and lose acceptance.
    return section if len(section.encode("utf-8")) <= _SECTION_BYTES else None


def project_answer_context(
    messages: list[ModelMessage],
    script: str,
    resumed: AbstractSet[str],
    *,
    memory_keys: AbstractSet[str] | None = None,
) -> list[ModelMessage]:
    """Add an authored reference to a request copy, never to durable learner evidence."""
    calls = [
        (i, part)
        for i, message in enumerate(messages)
        for part in message.parts
        if isinstance(part, ToolCallPart)
        and part.tool_name == "interact"
        and part.tool_call_id in resumed
    ]
    if len(calls) != 1:
        return messages
    index, call = calls[0]
    try:
        spec = InteractionSpec.model_validate(call.args_as_dict())
    except (AssertionError, TypeError, ValueError, ValidationError):
        return messages
    # Deferred-call arguments retain what the model originally sent, while the
    # displayed control has already dropped unadmitted keys and restored exact
    # authored input hints. Match the same control without rewriting evidence.
    if memory_keys is not None and spec.variable not in memory_keys:
        spec = spec.model_copy(update={"variable": None})
    spec = normalize_script_text_input(spec, script_text_inputs(script))
    section = authored_answer_section(script, spec)
    if section is None:
        return messages
    prior = next(
        (i for i in range(index - 1, -1, -1) if isinstance(messages[i], ModelRequest)),
        None,
    )
    if prior is None:
        return messages
    reference = json.dumps(
        {
            "status": "authored_section",
            "notice": "Host reference copied verbatim from this interaction's static authored section. It is not learner input, a new step, a grade or permission to write memory. Apply the original acceptance alternatives; the complete script and lesson-wide requirements remain authoritative. Select the current feedback phase before using this reference: acceptance criteria are for internal checking, conditional hint examples are alternatives for matching submitted cases, and post-correct explanations require a passing submission. A local hint example does not waive the lesson-wide stage or aspect limit. When checking direction is the current authored stage, use only the permitted direction from the selected example, leave the guiding question unanswered, and wait for the learner; do not combine examples, enumerate the remaining answer or supply later reasoning. An answer that covers all authored requirements proceeds directly to its explanation.",
            "text": section,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    request = messages[prior]
    projected = list(messages)
    projected[prior] = replace(
        request, parts=[*request.parts, UserPromptPart(reference)]
    )
    return projected
