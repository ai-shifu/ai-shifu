"""Keep selected choices and typed text across native questionnaire turns."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.service.profile_research.test_v2_runtime import (
    StreamChunks,
    _finish,
    _finished,
    _interact,
    _run,
    _runtime,
    _start,
    _SummaryProvider,
    _terminal,
    _tool_returns,
)

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


@pytest.mark.parametrize("kind", ["single_or_text", "multi_or_text"])
@pytest.mark.parametrize("with_selection", [True, False])
def test_mixed_control_keeps_typed_text_in_model_memory_and_private_facts(
    kind: str, with_selection: bool
) -> None:
    typed = "I mentor adults after work."
    selected = (
        (["teacher"] if kind == "single_or_text" else ["teacher", "engineer"])
        if with_selection
        else []
    )
    summary = _SummaryProvider("Mentors adults after work.")
    returns: list[str] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif answers := _tool_returns(messages):
            returns.append(str(answers[0].content))
            yield _finish()
        else:
            yield {
                0: _interact(
                    question="background",
                    kind=kind,
                    prompt="Your background?",
                    options=[
                        {"display": "Teacher", "value": "teacher"},
                        {"display": "Engineer", "value": "engineer"},
                    ],
                )
            }

    _app, runtime, _factories = _runtime(script)
    runtime._provider_factory = lambda *_args: summary
    separator = "||" if kind == "multi_or_text" else "|"
    view = _start(
        runtime,
        "?[%{{background}}Teacher//teacher"
        + separator
        + "Engineer//engineer"
        + separator
        + "...Other]",
    )
    _run(runtime, view)
    final = _run(
        runtime,
        view,
        values={"background": [*selected, typed]},
        request_id="answer",
        expected_interaction_id="question",
    )
    assert typed in returns[0]
    assert (
        "and wrote:" in returns[0]
        if selected
        else returns[0] == f"Learner wrote: {typed}"
    )
    expected = ", ".join(selected) + f"; {typed}" if selected else typed
    assert runtime.store.load(view["session_id"]).memory["background"] == expected
    assert _terminal(final)["done"] is True
    facts = summary.messages[0][-1]["content"]
    assert typed in facts
    assert all(value in facts for value in selected)
