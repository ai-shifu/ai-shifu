"""Project an exact, uniquely anchored authored section near a resumed answer."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import TYPE_CHECKING

from pydantic import ValidationError
from pydantic_ai.messages import ModelRequest, ToolCallPart

from .interaction import InteractionSpec
from .tools import _script_questions, normalize_script_text_input, script_text_inputs

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet

    from pydantic_ai.messages import ModelMessage

_FENCE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$")
_HEADING = re.compile(r"^[ ]{0,3}(#{1,6})(?:[ \t]+|$)")
_SECTION_BYTES = 8192
_REFERENCE_HEADING = "\n\n# Current authored feedback scope\n"


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


def _authored_answer_scope(
    script: str, spec: InteractionSpec
) -> tuple[str, list[str] | None] | None:
    """Locate the exact section and its enclosing introductions without interpreting rules.

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
    # Do not clip a large section down to just its question and lose acceptance.
    if len(section.encode("utf-8")) > _SECTION_BYTES:
        return None
    # A later question's nearest section is not the complete scope of its rules.
    # Copy introductions before the first heading/control in each ancestor,
    # excluding sibling exercises and keeping original Markdown boundaries.
    preamble_ranges = [(0, min([p for p, _ in [*headings, *controls]] + [len(script)]))]
    for i, (pos, level) in enumerate(headings):
        stop = next(
            (p for p, depth in headings[i + 1 :] if depth <= level), len(script)
        )
        if pos < start and pos <= anchor < stop:
            preamble_ranges.append(
                (
                    pos,
                    min(
                        [p for p, _ in headings if p > pos]
                        + [p for p, _ in controls if p >= pos]
                        + [len(script)]
                    ),
                )
            )
    preambles = []
    for pos, stop in sorted(set(preamble_ranges)):
        preamble = script[pos:stop]
        if not preamble.strip() or preamble in section:
            continue
        # A heading alone carries no additional instruction context.
        if _HEADING.match(preamble) and not "".join(preamble.splitlines()[1:]).strip():
            continue
        preambles.append(preamble)
    if sum(len(p.encode("utf-8")) for p in [section, *preambles]) > _SECTION_BYTES:
        return section, None
    return section, preambles


def authored_answer_section(script: str, spec: InteractionSpec) -> str | None:
    """Return local acceptance evidence without promoting ancestor rules to criteria."""
    scope = _authored_answer_scope(script, spec)
    return scope[0] if scope is not None else None


def authored_answer_reference(
    messages: list[ModelMessage],
    script: str,
    resumed: AbstractSet[str],
    *,
    memory_keys: AbstractSet[str] | None = None,
) -> str | None:
    """Build bounded current-turn instruction context, never learner history."""
    calls = [
        part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolCallPart)
        and part.tool_name == "interact"
        and part.tool_call_id in resumed
    ]
    if len(calls) != 1:
        return None
    call = calls[0]
    try:
        spec = InteractionSpec.model_validate(call.args_as_dict())
    except (AssertionError, TypeError, ValueError, ValidationError):
        return None
    # Deferred-call arguments retain what the model originally sent, while the
    # displayed control has already dropped unadmitted keys and restored exact
    # authored input hints. Match the same control without rewriting evidence.
    if memory_keys is not None and spec.variable not in memory_keys:
        spec = spec.model_copy(update={"variable": None})
    spec = normalize_script_text_input(spec, script_text_inputs(script))
    scope = _authored_answer_scope(script, spec)
    if scope is None:
        return None
    section, preambles = scope
    return json.dumps(
        {
            "status": "authored_section",
            "answer_id": call.tool_call_id,
            "text": section if preambles is not None else None,
            "ancestor_preambles": preambles or [],
            "notice": "Verbatim host reference: apply local rules and ancestor_preambles. If text is null, use the full authoritative script because the scope is oversized or cannot be uniquely anchored. This is not learner input, a new step, grade or memory-write permission. Select the current feedback phase before using this reference: acceptance criteria are for internal checking, conditional hint examples are alternatives for matching submitted cases, and post-correct explanations require a passing submission. A local hint example does not waive the lesson-wide stage or aspect limit. For checking-direction and authored-help correction feedback, follow these correction limits. Preserve authored multiplicity when several aspects or guiding questions are permitted or required; use a single-question shape only for an authored one-aspect or one-question limit, and do not invent that limit when no count is authored. A conditional example applies only when its condition matches the actual submission. When no conditional example matches, use the current authored stage and a genuinely unmatched requirement; do not force a sample case. A compound criterion or sample contains separate checks: choose only the exact clause for the permitted focus, not the whole paragraph. Leave permitted questions unanswered and wait; do not enumerate other gaps or supply later reasoning. For clarification, answer the actual side question within authored brevity and disclosure rules, then return to the pending exercise. Do not apply correction-only withholding to permitted clarification. An answer that covers all authored requirements proceeds directly to its explanation.",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def answer_reference_instructions(reference: str) -> str:
    """Keep the ephemeral reference as the final current-turn instruction."""
    return _REFERENCE_HEADING + reference


def without_answer_reference(
    messages: list[ModelMessage], reference: str | None
) -> list[ModelMessage]:
    """Remove only this run's exact instruction suffix from saved SDK requests."""
    if reference is None:
        return messages
    suffix = answer_reference_instructions(reference)
    return [
        replace(m, instructions=m.instructions.removesuffix(suffix))
        if isinstance(m, ModelRequest)
        and m.instructions
        and m.instructions.endswith(suffix)
        else m
        for m in messages
    ]
