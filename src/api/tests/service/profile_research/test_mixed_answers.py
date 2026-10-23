"""Preserve selected options and typed text through real profile-agent turns."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.service.profile_research.test_v2_runtime import (
    StreamChunks,
    _evidence,
    _finish,
    _finished,
    _interact,
    _run,
    _runtime,
    _start,
    _terminal,
    _tool_returns,
)

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


@pytest.mark.parametrize("kind", ["single_or_text", "multi_or_text"])
@pytest.mark.parametrize("with_selection", [True, False])
def test_mixed_control_keeps_typed_text_in_tool_result_memory_and_summary(
    kind: str, with_selection: bool
) -> None:
    typed = "I mentor adults after their working day."
    selected = ["teacher"] if kind == "single_or_text" else ["teacher", "engineer"]
    submitted = ["Teacher"] if kind == "single_or_text" else ["Teacher", "Engineer"]
    if not with_selection:
        selected = []
        submitted = []
    expected_memory = ", ".join(selected) + f"; {typed}" if selected else typed
    returned_answers: list[str] = []
    summary_evidence: list[dict[str, Any]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif factories[-1] == 1:
            summary_evidence.append(_evidence(messages))
            yield "Mentors adults after their working day."
        elif answers := _tool_returns(messages):
            returned_answers.append(str(answers[0].content))
            yield _finish()
        else:
            yield {
                0: _interact(
                    variable="background",
                    kind=kind,
                    prompt="Other background",
                    options=[
                        {"display": "Teacher", "value": "teacher"},
                        {"display": "Engineer", "value": "engineer"},
                    ],
                )
            }

    _app, runtime, factories = _runtime(script)
    separator = " | " if kind == "single_or_text" else " || "
    view = _start(
        runtime,
        "?[%{{background}} Teacher//teacher"
        + separator
        + "Engineer//engineer"
        + separator
        + "...Other background]",
    )
    _run(runtime, view)
    answered = _run(
        runtime,
        view,
        values={"background": [*submitted, typed]},
        request_id="mixed-answer",
        expected_interaction_id="question",
    )

    assert _terminal(answered)["next_block_index"] == 1
    assert len(returned_answers) == 1
    assert typed in returned_answers[0]
    if selected:
        assert (
            f"Learner chose: {', '.join(selected)}; and wrote: {typed}"
            in (returned_answers[0])
        )
    else:
        assert returned_answers[0] == f"Learner wrote: {typed}"
    stored = runtime.store.load(view["session_id"])
    assert stored.variables["background"] == expected_memory
    assert stored.accepted_answers == [*selected, typed]

    summary = _run(runtime, view, index=1, request_id="summary")

    assert _terminal(summary)["done"] is True
    assert (
        _terminal(summary)["profile_draft"] == "Mentors adults after their working day."
    )
    assert summary_evidence[0]["accepted_answers"]["background"] == expected_memory
    assert summary_evidence[0]["accepted_interaction_answers"] == [*selected, typed]
