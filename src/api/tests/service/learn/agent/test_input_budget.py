"""Exercise complete model input limits at the real gateway boundary."""

import json
from collections.abc import Iterator

import pytest
from flaskr.service.learn.agent import gateway_model as gw
from flaskr.service.learn.agent.engine import (
    ContinueTurn,
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    Session,
    TurnDone,
)
from flaskr.service.learn.agent.engine.events import InputBudgetExceededError
from flaskr.service.learn.agent.input_budget import INPUT_BUDGET_BYTES
from flaskr.service.learn.agent.memory_admission import make_request_check
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.tools import ToolDefinition

from tests.service.learn.agent.test_gateway_model import FakeChunk, FakeSpan

pytestmark = pytest.mark.anyio


def _model(limit: int = INPUT_BUDGET_BYTES) -> gw.GatewayModel:
    return gw.GatewayModel(
        app=None,
        model="test-model",
        user_id="learner",
        span=FakeSpan(),
        input_budget_bytes=limit,
    )


def _size(messages: list, parameters: ModelRequestParameters) -> int:
    return len(
        json.dumps(
            {"messages": gw.map_messages(messages), "tools": gw.map_tools(parameters)},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("value", ["plain", '\n\t"\\' * 10, "é🙂" * 10])
async def test_exact_utf8_envelope_boundary_is_sent_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    stream: bool,
    value: str,
) -> None:
    seen = []

    def chat(**kwargs: object) -> Iterator[FakeChunk]:
        seen.append(kwargs)
        yield FakeChunk(result="A useful example.", finish_reason="stop")

    monkeypatch.setattr(gw, "chat_llm", chat)
    messages = [ModelRequest(parts=[UserPromptPart(value)], instructions="Teach.")]
    parameters = ModelRequestParameters(
        function_tools=[
            ToolDefinition(
                name="lookup",
                description=value,
                parameters_json_schema={"type": "object"},
            )
        ]
    )
    size = _size(messages, parameters)

    async def request(model: gw.GatewayModel) -> None:
        if stream:
            async with model.request_stream(messages, None, parameters) as response:
                async for _ in response:
                    pass
        else:
            await model.request(messages, None, parameters)

    for limit in (size, size - 1):
        model = _model(limit)
        if limit < size:
            with pytest.raises(InputBudgetExceededError):
                await request(model)
        else:
            await request(model)
    assert len(seen) == 1
    assert seen[0]["messages"] == gw.map_messages(messages)
    assert seen[0]["tools"] == gw.map_tools(parameters)
    assert messages[0].parts[0].content == value


@pytest.mark.parametrize(
    "source",
    [
        "instructions",
        "script",
        "history",
        "tool_arguments",
        "tool_results",
        "tools",
    ],
)
async def test_every_input_source_counts_before_gateway_io(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> None:
    calls = []
    monkeypatch.setattr(gw, "chat_llm", lambda **kw: calls.append(kw))
    large = "x" * INPUT_BUDGET_BYTES
    messages = [ModelRequest(parts=[UserPromptPart("Teach.")])]
    parameters = ModelRequestParameters()
    if source == "instructions":
        messages[0].instructions = large
    elif source == "script":
        messages[0].parts[0].content = "<script>" + large + "</script>"
    elif source == "history":
        messages.extend(
            [
                ModelResponse(parts=[TextPart(large)]),
                ModelRequest(parts=[UserPromptPart("Continue.")]),
            ]
        )
    elif source in {"tool_arguments", "tool_results"}:
        messages.extend(
            [
                ModelResponse(
                    parts=[
                        ToolCallPart(
                            "lookup",
                            {"text": large if source == "tool_arguments" else "small"},
                            "lookup-1",
                        )
                    ]
                ),
                ModelRequest(
                    parts=[
                        ToolReturnPart(
                            "lookup",
                            large if source == "tool_results" else "small",
                            "lookup-1",
                        )
                    ]
                ),
            ]
        )
    else:
        parameters = ModelRequestParameters(
            function_tools=[
                ToolDefinition(
                    name="lookup",
                    description=large,
                    parameters_json_schema={"type": "object"},
                )
            ]
        )
    with pytest.raises(InputBudgetExceededError, match="application budget"):
        await _model().request(messages, None, parameters)
    assert not calls


async def test_repeated_exact_substitutions_count_and_original_memory_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(gw, "chat_llm", lambda **kw: calls.append(kw))
    engine = Engine(_model(), memory_context_limit=32768)
    answer = "z" * 70000
    session = await engine.new_session("{{answer}}\n" * 4, memory={"answer": answer})
    events = [event async for event in engine.run_turn(session)]
    assert not calls
    assert events[-1].code == "input_budget_exceeded"
    assert events[-1].retryable is False
    assert session.memory["answer"] == answer
    assert not session.finished


async def test_oversized_pending_answer_survives_snapshot_and_successful_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = []

    def chat(**kwargs: object) -> Iterator[FakeChunk]:
        seen.append(kwargs["messages"])
        if len(seen) == 1:
            yield FakeChunk(
                tool_call_deltas=[
                    {
                        "index": 0,
                        "id": "q",
                        "name": "interact",
                        "arguments": json.dumps(
                            {"type": "text", "prompt": "Your goal?", "variable": "goal"}
                        ),
                    }
                ],
                finish_reason="tool_calls",
            )
        else:
            yield FakeChunk(result="Apply your goal.", finish_reason="stop")

    monkeypatch.setattr(gw, "chat_llm", chat)
    engine = Engine(_model(), memory_context_limit=32768)
    session = await engine.new_session("Ask %{{goal}} and explain.")
    _ = [event async for event in engine.run_turn(session)]
    history = session.to_dict()["messages"]
    answer = "complete learner answer " + "z" * INPUT_BUDGET_BYTES
    events = [
        event
        async for event in engine.run_turn(
            session,
            InteractionResponseTurn(id="q", values=[answer]),
        )
    ]
    assert len(seen) == 1
    assert isinstance(events[-1], ErrorEvent)
    assert events[-1].code == "input_budget_exceeded"
    assert session.memory["goal"] == answer
    assert session.answers
    assert session.to_dict()["messages"] == history
    assert not session.finished
    session = Session.loads(session.dumps())
    retry = Engine(_model(INPUT_BUDGET_BYTES * 4), memory_context_limit=32768)
    events = [event async for event in retry.run_turn(session, ContinueTurn())]
    assert isinstance(events[-1], TurnDone)
    assert answer in seen[-1][-1]["content"]
    assert session.memory["goal"] == answer
    assert not session.answers
    assert session.to_dict()["messages"][: len(history)] == history


async def test_every_tool_loop_request_is_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def chat(**kwargs: object) -> Iterator[FakeChunk]:
        calls.append(kwargs)
        yield FakeChunk(result="x" * INPUT_BUDGET_BYTES)
        yield FakeChunk(
            tool_call_deltas=[
                {
                    "index": 0,
                    "id": "m",
                    "name": "remember",
                    "arguments": json.dumps({"key": "note", "value": "useful"}),
                }
            ],
            finish_reason="tool_calls",
        )

    monkeypatch.setattr(gw, "chat_llm", chat)
    engine = Engine(_model())
    session = await engine.new_session("Teach and take a note.")
    events = [event async for event in engine.run_turn(session)]
    assert len(calls) == 1
    assert isinstance(events[-1], ErrorEvent)
    assert events[-1].code == "input_budget_exceeded"


async def test_oversized_admission_input_refuses_memory_without_gateway_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(gw, "chat_llm", lambda **kw: calls.append(kw))
    check = make_request_check(_model())
    assert (
        await check("Please remember " + "x" * INPUT_BUDGET_BYTES, "note", "value")
        is False
    )
    assert not calls


@pytest.mark.parametrize("limit", [0, -1])
def test_invalid_gateway_budget_is_rejected(limit: int) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        _model(limit)


async def test_budget_retries_do_not_consume_the_turn_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(gw, "chat_llm", lambda **kw: calls.append(kw))
    engine = Engine(_model(), turn_limit=200)
    session = await engine.new_session("Teach.")
    session.turn = 199
    session.messages = [
        ModelRequest(parts=[UserPromptPart("x" * INPUT_BUDGET_BYTES)]),
        ModelResponse(parts=[TextPart("Earlier explanation.")]),
    ]
    for _ in range(3):
        events = [event async for event in engine.run_turn(session, ContinueTurn())]
        assert isinstance(events[-1], ErrorEvent)
        assert events[-1].code == "input_budget_exceeded"
        assert session.turn == 199
        assert not session.finished
        session = Session.loads(session.dumps())
    assert not calls


async def test_accepted_finish_stands_when_its_followup_request_is_oversized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    gateway = _model()

    def chat(**kwargs: object) -> Iterator[FakeChunk]:
        calls.append(kwargs)
        gateway._input_budget_bytes = 1
        yield FakeChunk(
            tool_call_deltas=[
                {
                    "index": 0,
                    "id": "done",
                    "name": "finish",
                    "arguments": json.dumps(
                        {"summary": "All required teaching completed."}
                    ),
                }
            ],
            finish_reason="tool_calls",
        )

    monkeypatch.setattr(gw, "chat_llm", chat)
    engine = Engine(gateway)
    session = await engine.new_session("Finish when all required teaching is complete.")
    events = [event async for event in engine.run_turn(session)]
    assert len(calls) == 1
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "finished"
    assert session.finished is True
    assert not any(isinstance(event, ErrorEvent) for event in events)
