"""Verify question-first instructions and authored interaction ordering reach the model."""

import json
from collections.abc import AsyncIterator
from typing import Literal

import pytest
from markdownflow.engine import ContentDelta, Engine, InteractionRequest
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel


@pytest.mark.anyio
@pytest.mark.parametrize("listen_mode", [False, True])
@pytest.mark.parametrize("render", ["sandbox", "none"])
async def test_question_first_contract_preserves_prose_then_authored_controls(
    listen_mode: bool, render: Literal["sandbox", "none"]
) -> None:
    """Check actual request instructions and engine events, not model compliance rates."""
    question = "Which examples match?"
    options = [{"display": "A", "value": "a"}, {"display": "B", "value": "b"}]

    async def model(
        _messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        instructions = info.instructions or ""
        assert "first ask the complete current question" in instructions
        assert "learner-facing content in the same turn" in instructions
        assert "outside HTML, code and other visuals" in instructions
        assert "not a substitute for asking the question in content" in instructions
        assert "Call `interact` in the same response" in instructions
        assert "without inventing an extra teaching question" in instructions
        assert "its questions are rendered by the host" in instructions
        assert "write no free prose and keep the tool prompt empty" in instructions
        yield question
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="examples",
                json_args=json.dumps(
                    {"type": "multi", "prompt": "Matching examples", "options": options}
                ),
            )
        }

    engine = Engine(FunctionModel(stream_function=model), render=render)
    session = await engine.new_session(
        question + "\n?[A//a || B//b]", listen_mode=listen_mode
    )
    events = [event async for event in engine.run_turn(session)]
    assert not any(event.type == "error" for event in events)
    (interaction,) = [e for e in events if isinstance(e, InteractionRequest)]
    before = events[: events.index(interaction)]
    if not listen_mode:
        assert (
            "".join(e.text for e in before if isinstance(e, ContentDelta)) == question
        )
    else:
        assert (
            "".join(e.text for e in before if e.type == "narration.delta") == question
        )
    assert interaction.spec.prompt == "Matching examples"
    assert interaction.spec.type == "multi"
    assert [option.model_dump() for option in interaction.spec.options] == options
    assert [pending.tool_call_id for pending in session.pending] == ["examples"]
