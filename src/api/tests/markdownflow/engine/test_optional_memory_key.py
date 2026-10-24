"""Blank optional tool fields preserve unnamed questions without model retries."""

import json
from collections.abc import AsyncIterator

import pytest
from markdownflow.engine import (
    Engine,
    ErrorEvent,
    InteractionRequest,
    InteractionResponseTurn,
    MemoryUpdated,
)
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("variable", ["", " \t\n", "\u0085\u001f\u3000"])
async def test_blank_optional_variable_does_not_retry_or_store_an_answer(
    variable: str,
) -> None:
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls > 1:
            yield "Thanks. Here is the next example."
            return
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="question",
                json_args=json.dumps(
                    {
                        "type": "single",
                        "prompt": "Choose one",
                        "variable": variable,
                        "options": [{"display": "A"}, {"display": "B"}],
                    }
                ),
            )
        }

    engine = Engine(FunctionModel(stream_function=model), memory_admission=True)
    session = await engine.new_session("?[A|B]")
    first = [event async for event in engine.run_turn(session)]
    assert not any(isinstance(event, ErrorEvent) for event in first)
    assert calls == 1
    request = next(event for event in first if isinstance(event, InteractionRequest))
    assert request.spec.variable is None
    second = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(values=["A"])
        )
    ]
    assert not any(isinstance(event, (ErrorEvent, MemoryUpdated)) for event in second)
    assert calls == 2
    assert session.memory == {}
    assert second[-1].reason == "end"
