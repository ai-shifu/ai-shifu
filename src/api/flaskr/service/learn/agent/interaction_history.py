"""Project submitted answers onto the controls that asked for them."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from flaskr.api.markdownflow import (
    InteractionAnswer,
    InteractionSpec,
    answer_is_usable,
    normalize_answer,
)
from markdownflow import InteractionParser
from pydantic import ValidationError

from .legacy_protocol import render_interaction
from .rewind import read_turn_learner_values, read_turn_record

if TYPE_CHECKING:
    from flaskr.service.learn.models import LearnGeneratedBlock, LearnGeneratedElement


def structured_user_input(raw_spec: object, values: list[str]) -> str | None:
    """Encode a submitted answer as the renderer's structured control defaults.

    Existing structured defaults preserve commas/newlines inside each submitted value.
    Returns None for a confirmation, an invalid spec or an unusable answer.
    """
    try:
        spec = InteractionSpec.model_validate(raw_spec)
    except ValidationError:
        return None
    if spec.type == "confirm":
        return None
    answer = normalize_answer(spec, InteractionAnswer(values=values))
    if not answer_is_usable(spec, answer):
        return None
    option_values = {option.stored for option in spec.options}
    selected = [value for value in answer.values if value in option_values]
    free_text = [value for value in answer.values if value not in option_values]
    return json.dumps(
        {
            "selectedValues": selected,
            "inputText": ", ".join(free_text),
            "buttonText": selected[0]
            if selected and spec.type in ("single", "single_or_text")
            else "",
        },
        ensure_ascii=False,
    )


def _matches_control(spec: InteractionSpec, content: str) -> bool:
    """Compare original controls without translating an omitted input hint again."""
    parser = InteractionParser()
    parsed = parser.parse(content)
    if not spec.placeholder and spec.type in (
        "text",
        "single_or_text",
        "multi_or_text",
    ):
        if not parsed or not parsed.get("question"):
            return False
        spec = spec.model_copy(update={"placeholder": parsed["question"]})
    return parser.parse(render_interaction(spec)) == parsed


def _unanswered_call_ids(block: LearnGeneratedBlock) -> set[str]:
    """Carry identities only while their original deferred queue remains pending."""
    record = read_turn_record(block)
    pending = record["checkpoint"].get("pending") if record else None
    if not isinstance(pending, list) or not pending:
        return set()
    if any(
        not isinstance(question, dict)
        or not isinstance(question.get("tool_call_id"), str)
        for question in pending
    ):
        return set()
    ids = {question["tool_call_id"] for question in pending}
    try:
        spec = InteractionSpec.model_validate(pending[0].get("spec"))
    except ValidationError:
        return set()
    answer = normalize_answer(
        spec, InteractionAnswer(values=read_turn_learner_values(block))
    )
    if answer_is_usable(spec, answer):
        ids.discard(pending[0]["tool_call_id"])
    return ids


def project_interaction_inputs(
    blocks: list[LearnGeneratedBlock], rows: list[LearnGeneratedElement]
) -> dict[str, str]:
    """Read answers from checkpoint inputs, keyed by the original interaction element.

    A checkpoint names the pending controls when its request began. Match the preceding
    turn's controls in emission order to that queue, retaining tool-call identities across
    later turns that re-display remaining questions. Identical controls stay independent.
    """
    controls: dict[str, dict[str, LearnGeneratedElement]] = {}
    for row in sorted(
        rows,
        key=lambda row: (
            int(getattr(row, "sequence_number", 0) or 0),
            int(getattr(row, "run_event_seq", 0) or 0),
            int(row.id or 0),
        ),
    ):
        if row.event_type != "element" or row.element_type != "interaction":
            continue
        identity = (
            row.target_element_bid
            if not row.is_new and row.target_element_bid
            else row.element_bid
        )
        if identity:
            controls.setdefault(row.generated_block_bid, {})[identity] = row

    previous_by_scope: dict[tuple[str, str, str, str], LearnGeneratedBlock] = {}
    questions_by_scope: dict[tuple[str, str, str, str], dict[str, list[str]]] = {}
    result: dict[str, str] = {}
    for block in blocks:
        scope = (
            block.user_bid,
            block.shifu_bid,
            block.outline_item_bid,
            block.progress_record_bid,
        )
        previous = previous_by_scope.get(scope)
        previous_by_scope[scope] = block
        record = read_turn_record(block)
        if previous is None or record is None or read_turn_record(previous) is None:
            questions_by_scope.pop(scope, None)
            continue
        pending = record["checkpoint"].get("pending")
        if not isinstance(pending, list) or not pending:
            continue
        questions = questions_by_scope.setdefault(scope, {})
        remaining = _unanswered_call_ids(previous)
        for old_id in list(questions):
            if old_id not in remaining:
                del questions[old_id]
        previous_controls = controls.get(previous.generated_block_bid, {})
        if len(previous_controls) <= len(pending):
            for (identity, row), question in zip(
                previous_controls.items(), pending, strict=False
            ):
                if (
                    not isinstance(question, dict)
                    or not isinstance(question.get("tool_call_id"), str)
                    or not question["tool_call_id"]
                ):
                    continue
                try:
                    spec = InteractionSpec.model_validate(question.get("spec"))
                    if spec.type == "confirm" or not _matches_control(
                        spec, row.content_text
                    ):
                        continue
                except (ValidationError, ValueError):
                    continue
                identities = questions.setdefault(question["tool_call_id"], [])
                if identity not in identities:
                    identities.append(identity)
        first = pending[0]
        values = read_turn_learner_values(block)
        if (
            not isinstance(first, dict)
            or not isinstance(first.get("tool_call_id"), str)
            or not values
        ):
            continue
        identities = questions.get(first.get("tool_call_id"), [])
        if not identities:
            continue
        user_input = structured_user_input(first.get("spec"), values)
        if user_input is None:
            continue
        for identity in identities:
            result[identity] = user_input
    return result
