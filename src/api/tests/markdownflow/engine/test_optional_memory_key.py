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
    Session,
)
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("question", ["", " \t\n", "\u0085\u001f\u3000"])
async def test_blank_optional_question_does_not_retry_or_store_an_answer(
    question: str,
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
                        "question": question,
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
    assert request.spec.question is None
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


@pytest.mark.parametrize("legacy", [False, True])
async def test_question_text_is_the_only_tool_field_and_exact_memory_key(
    legacy: bool,
) -> None:
    """An authored question reaches the tool schema, pending state and saved answer intact."""
    question = 'What is your goal? [today] / "quoted"'
    calls = 0

    async def model(
        _messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        schema = next(tool for tool in info.function_tools if tool.name == "interact")
        assert "question" in schema.parameters_json_schema["properties"]
        assert "variable" not in schema.parameters_json_schema["properties"]
        if calls > 1:
            yield "Thanks."
            return
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="question",
                json_args=json.dumps(
                    {
                        "type": "text",
                        "prompt": question,
                        "question": "  " + question + "  ",
                    }
                ),
            )
        }

    engine = Engine(FunctionModel(stream_function=model), memory_admission=True)
    session = await engine.new_session("?[%{{ " + question + " }} ...Your answer]")
    first = [event async for event in engine.run_turn(session)]
    assert not any(isinstance(event, ErrorEvent) for event in first)
    request = next(event for event in first if isinstance(event, InteractionRequest))
    assert request.spec.question == question
    state = session.to_dict()
    if legacy:
        old_spec = state["pending"][0]["spec"]
        old_spec["variable"] = old_spec.pop("question")
        for message in state["messages"]:
            for part in message["parts"]:
                if part.get("tool_name") != "interact":
                    continue
                arguments = part["args"]
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                arguments["variable"] = arguments.pop("question")
                part["args"] = arguments
    session = Session.from_dict(state)
    second = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(text="Learn")
        )
    ]
    assert not any(isinstance(event, ErrorEvent) for event in second)
    assert session.memory == {question: "Learn"}
    assert [event.key for event in second if isinstance(event, MemoryUpdated)] == [
        question
    ]


@pytest.mark.parametrize("length", [255, 256])
async def test_question_storage_limit_never_truncates_the_authored_key(
    length: int,
) -> None:
    """Overlong questions are retried before a learner can answer under a changed key."""
    from types import SimpleNamespace

    from markdownflow.engine.tools import Deps, interact
    from pydantic_ai import CallDeferred, ModelRetry, RunContext

    question = "q" * length
    deps = Deps(memory={}, user_memory={})
    ctx = RunContext(
        deps=deps,
        model=FunctionModel(stream_function=lambda *_args: None),
        usage=SimpleNamespace(),
        prompt="Teach.",
        messages=[],
        tool_name="interact",
        tool_call_id="q",
    )
    expected = CallDeferred if length == 255 else ModelRetry
    with pytest.raises(expected) as raised:
        await interact(ctx, type="text", prompt="Your answer?", question=question)
    if length > 255:
        assert "never truncate" in str(raised.value)
    assert deps.memory == {}
