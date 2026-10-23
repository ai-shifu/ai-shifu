"""Reject a stale saved question produced by the real declared memory tool."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from flaskr.service.profile_research.runtime import (
    PROFILE_ONBOARDING_PURPOSE,
    ProfileResearchError,
)
from markdown_flow import InteractionParser
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall

from tests.service.profile_research.test_v2_runtime import (
    StreamChunks,
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


def test_remember_cannot_turn_an_unconsumed_selection_into_accepted_evidence() -> None:
    calls: list[list[ModelMessage]] = []
    accepted_tool_results: list[str] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls.append(messages)
        if _finished(messages):
            yield " "
        elif answers := _tool_returns(messages):
            accepted_tool_results.extend(str(answer.content) for answer in answers)
            yield _finish()
        elif factories[-1] == 0:
            yield {
                0: _interact(
                    call_id="initial-goal", variable="goal", prompt="What goal?"
                )
            }
        elif any(
            isinstance(part, ToolReturnPart) and part.tool_name == "remember"
            for message in messages
            for part in message.parts
        ):
            yield {
                0: _interact(
                    call_id="choice-goal",
                    variable="goal",
                    kind="single",
                    prompt="Keep your prior goal?",
                    options=[
                        {"display": "Old", "value": "Old"},
                        {"display": "Other", "value": "Other"},
                    ],
                )
            }
        else:
            # This is a supported declared memory write, not an edited cache.
            yield {
                0: DeltaToolCall(
                    name="remember",
                    tool_call_id="update-goal",
                    json_args=json.dumps(
                        {
                            "key": "goal",
                            "value": "New",
                            "scope": "session",
                            "request": None,
                        }
                    ),
                )
            }

    _app, runtime, factories = _runtime(script)
    view = _start(
        runtime,
        "?[%{{goal}}...What goal?]\n\n---\n\n?[%{{goal}} {{goal}} | Other]",
    )
    _run(runtime, view)
    first_answer = _run(
        runtime,
        view,
        values={"goal": ["Old"]},
        request_id="first-answer",
        expected_interaction_id="initial-goal",
    )
    first_saved = runtime.store.load(view["session_id"])
    assert _terminal(first_answer)["next_block_index"] == 1
    assert accepted_tool_results == ["Learner wrote: Old"]
    assert first_saved.variables == {"goal": "Old"}
    assert first_saved.accepted_answers == ["Old"]

    rendered = _run(runtime, view, index=1, request_id="render-choice")
    interaction = next(
        event for event in rendered if event["event_type"] == "interaction"
    )
    controls = interaction["content"].rsplit("\n\n", 1)[-1]
    assert interaction["interaction_id"] == "choice-goal"
    assert InteractionParser().parse(controls)["buttons"] == [
        {"display": "Old", "value": "Old"},
        {"display": "Other", "value": "Other"},
    ]
    saved = runtime.store.load(view["session_id"])
    assert saved.variables == {"goal": "New"}
    assert saved.engine_session["pending"][0]["tool_call_id"] == "choice-goal"
    assert saved.engine_session["profile_research_answered_count"] == 0
    original = saved.to_cache_payload()
    calls_before_answer = len(calls)
    events: list[dict] = []

    with pytest.raises(
        ProfileResearchError, match="cannot resume the saved profile question"
    ):
        events.extend(
            runtime.stream_session(
                user_bid="v2-learner",
                session_id=view["session_id"],
                user_input={"goal": ["Old"]},
                expected_purpose=PROFILE_ONBOARDING_PURPOSE,
                expected_block_index=1,
                request_id="choice-answer",
                expected_interaction_id="choice-goal",
            )
        )

    assert events == []
    assert len(calls) == calls_before_answer
    assert accepted_tool_results == ["Learner wrote: Old"]
    assert runtime.store.load(view["session_id"]).to_cache_payload() == original
