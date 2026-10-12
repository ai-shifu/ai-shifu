"""Project submitted answers onto the controls that asked for them."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import ValidationError

from .engine.interaction import (
    InteractionAnswer,
    InteractionSpec,
    answer_is_usable,
    normalize_answer,
)
from .legacy_protocol import render_interaction
from .rewind import _read_turn_record, read_turn_learner_values

if TYPE_CHECKING:
    from flaskr.service.learn.models import LearnGeneratedBlock, LearnGeneratedElement


def project_interaction_inputs(
    blocks: list[LearnGeneratedBlock], rows: list[LearnGeneratedElement]
) -> dict[str, str]:
    """Read each answer from the next turn's checkpoint, never from teacher prose or memory.

    The checkpoint names the pending control when that request began. Require its exact
    rendered controls on the preceding active turn in the same classroom attempt. This also
    restores old records without a data migration and keeps repeated variables independent.
    """
    controls: dict[str, set[str]] = {}
    for row in rows:
        if row.event_type == "element" and row.element_type == "interaction":
            controls.setdefault(row.generated_block_bid, set()).add(row.content_text)

    previous_by_scope: dict[tuple[str, str, str, str], LearnGeneratedBlock] = {}
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
        record = _read_turn_record(block)
        if previous is None or record is None or _read_turn_record(previous) is None:
            continue
        pending = record["checkpoint"].get("pending")
        values = read_turn_learner_values(block)
        if not isinstance(pending, list) or not pending or not values:
            continue
        first = pending[0]
        if not isinstance(first, dict) or not first.get("tool_call_id"):
            continue
        try:
            spec = InteractionSpec.model_validate(first.get("spec"))
            if spec.type == "confirm":
                continue
            rendered = render_interaction(spec)
        except (ValidationError, ValueError):
            continue
        if controls.get(previous.generated_block_bid) != {rendered}:
            continue
        answer = normalize_answer(spec, InteractionAnswer(values=values))
        if not answer_is_usable(spec, answer):
            continue
        option_values = {option.stored for option in spec.options}
        selected = [value for value in answer.values if value in option_values]
        free_text = [value for value in answer.values if value not in option_values]
        # The renderer already accepts structured defaults; preserve commas/newlines inside
        # each value rather than making an ambiguous comma-separated selection string.
        result[previous.generated_block_bid] = json.dumps(
            {
                "selectedValues": selected,
                "inputText": ", ".join(free_text),
                "buttonText": selected[0]
                if selected and spec.type in ("single", "single_or_text")
                else "",
            },
            ensure_ascii=False,
        )
    return result
