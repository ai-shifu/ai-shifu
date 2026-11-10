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
from .rewind import (
    narrated_answer,
    read_turn_learner_values,
    read_turn_record,
    recorded_question_ids,
)

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


def narrated_user_input(control: str, values: list[str]) -> str | None:
    """Validate message values against the rendered control and encode its defaults."""
    parsed = InteractionParser().parse(control)
    if not parsed.get("type"):
        return None
    options = {option["value"].strip() for option in parsed.get("buttons", [])}
    selected = [value for value in values if value in options]
    text = [value for value in values if value not in options]
    multi = parsed.get("is_multi_select", False)
    if (len(selected) > 1 and not multi) or (
        text and ("question" not in parsed or len(text) != 1)
    ):
        return None
    return json.dumps(
        {
            "selectedValues": selected,
            "inputText": text[0] if text else "",
            "buttonText": selected[0] if selected and not multi else "",
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
    if "answered_question_id" in record:
        accepted = record["answered_question_id"]
        if isinstance(accepted, str):
            ids.discard(accepted)
        return ids
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


def _scope(
    row: LearnGeneratedBlock | LearnGeneratedElement,
) -> tuple[str, str, str, str]:
    return row.user_bid, row.shifu_bid, row.outline_item_bid, row.progress_record_bid


def _project_repeated_controls(
    blocks: list[LearnGeneratedBlock],
    controls: dict[str, dict[str, LearnGeneratedElement]],
    repeated: dict[str, dict[str, str]],
) -> None:
    visible: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for block in blocks:
        scope = _scope(block)
        identities = controls.get(block.generated_block_bid, {})
        question_ids = recorded_question_ids(read_turn_record(block), len(identities))
        if (
            not block.progress_record_bid
            or question_ids is None
            or any(_scope(row) != scope for row in identities.values())
        ):
            visible.pop(scope, None)
            continue
        shown = visible.setdefault(scope, {})
        for finished_id in shown.keys() - _unanswered_call_ids(block):
            del shown[finished_id]
        for identity, question_id in zip(identities, question_ids, strict=True):
            original = shown.setdefault(question_id, identity)
            if original != identity:
                repeated.setdefault(block.progress_record_bid, {})[identity] = original


def project_interaction_inputs(
    blocks: list[LearnGeneratedBlock],
    rows: list[LearnGeneratedElement],
    *,
    repeated_controls: dict[str, dict[str, str]] | None = None,
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

    if repeated_controls is not None:
        _project_repeated_controls(blocks, controls, repeated_controls)

    previous_by_scope: dict[tuple[str, str, str, str], LearnGeneratedBlock] = {}
    questions_by_scope: dict[tuple[str, str, str, str], dict[str, list[str]]] = {}
    result: dict[str, str] = {}
    for block in blocks:
        scope = _scope(block)
        previous = previous_by_scope.get(scope)
        previous_by_scope[scope] = block
        record = read_turn_record(block)
        if previous is None or record is None:
            questions_by_scope.pop(scope, None)
            continue
        previous_record = read_turn_record(previous)
        if previous_record is None:
            questions_by_scope.pop(scope, None)
        pending = record["checkpoint"].get("pending")
        previous_controls = controls.get(previous.generated_block_bid, {})
        if pending == [] and len(previous_controls) == 1:
            identity, row = next(iter(previous_controls.items()))
            if _scope(row) == scope:
                answer = narrated_answer(
                    previous_record, record, row.content_text or ""
                )
                if answer is not None:
                    result[identity] = answer.user_input
        if not isinstance(pending, list) or not pending:
            continue
        if previous_record is None:
            # Older native turn blocks have an empty config. An inferred match is
            # local to this pair of turns and must not seed repeated-control tracking.
            if (
                previous.block_content_conf
                or not block.progress_record_bid
                or len(previous_controls) != 1
                or len(pending) != 1
                or any(_scope(row) != scope for row in previous_controls.values())
            ):
                continue
            questions = {}
        else:
            questions = questions_by_scope.setdefault(scope, {})
            remaining = _unanswered_call_ids(previous)
            for old_id in list(questions):
                if old_id not in remaining:
                    del questions[old_id]
        recorded = recorded_question_ids(previous_record, len(previous_controls))
        if recorded is not None:
            pending_ids = {
                item["tool_call_id"]
                for item in pending
                if isinstance(item, dict) and isinstance(item.get("tool_call_id"), str)
            }
            for identity, question_id in zip(previous_controls, recorded, strict=True):
                if (
                    question_id in pending_ids
                    and _scope(previous_controls[identity]) == scope
                ):
                    identities = questions.setdefault(question_id, [])
                    if identity not in identities:
                        identities.append(identity)
        elif len(previous_controls) <= len(pending):
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
        if (
            "answered_question_id" in record
            and record["answered_question_id"] != first["tool_call_id"]
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
