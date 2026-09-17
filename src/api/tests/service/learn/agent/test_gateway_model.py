"""Offline tests for the pydantic-ai model that calls this project's LLM gateway.

`chat_llm` is replaced by a fake generator, so nothing here reaches a provider or costs anything.
What is under test is the translation in both directions: the message and tool shapes the gateway
is handed, and the parts pydantic-ai gets back out of a stream.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from flaskr.service.learn.agent import gateway_model as gw
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.tools import ToolDefinition

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.anyio


class FakeChunk:
    """One `LLMStreamResponse` as far as this adapter is concerned."""

    def __init__(
        self,
        result: str = "",
        tool_call_deltas: list[dict] | None = None,
        finish_reason: str | None = None,
        usage: object = None,
    ) -> None:
        """Hold what the adapter reads off a chat_llm chunk."""
        self.result = result
        self.tool_call_deltas = tool_call_deltas or []
        self.finish_reason = finish_reason
        self.usage = usage


class FakeSpan:
    """A Langfuse observation handle as far as chat_llm is concerned.

    `chat_llm` opens a generation on the span before it reaches a provider, so a double that never
    touches it would hide a model built without one.
    """

    def __init__(self) -> None:
        """Record what was opened on it."""
        self.generations: list[str] = []

    def generation(self, **kwargs: object) -> FakeSpan:
        """Open a generation, as chat_llm does."""
        self.generations.append(str(kwargs.get("name", "")))
        return self


class FakeUsage:
    """Token counts in the shape chat_llm reports them."""

    def __init__(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Hold the two counts the adapter maps."""
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


def _params(tools: list[ToolDefinition] | None = None) -> ModelRequestParameters:
    return ModelRequestParameters(function_tools=tools or [], output_tools=[])


async def _drain(chunks: list[FakeChunk]) -> ModelResponse:
    """Run a chunk list through the streamed response and return the assembled message."""
    response = gw.GatewayStreamedResponse(
        model_request_parameters=_params(),
        _model_name="test-model",
        _chunks=iter(chunks),
    )
    async for _ in response:
        pass
    return response.get()


# -- message mapping ---------------------------------------------------------------------


def test_system_parts_are_merged_into_one_leading_message() -> None:
    """Several providers reject a second system message, so they have to arrive as one."""
    messages = [
        ModelRequest(
            parts=[
                SystemPromptPart(content="first"),
                UserPromptPart(content="hello"),
                SystemPromptPart(content="second"),
            ]
        )
    ]
    out = gw.map_messages(messages)
    assert [m["role"] for m in out] == ["system", "user"]
    assert out[0]["content"] == "first\n\nsecond"


def test_a_tool_return_becomes_a_tool_message_keyed_by_call_id() -> None:
    messages = [
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="interact",
                    content="Learner chose: good",
                    tool_call_id="c1",
                )
            ]
        )
    ]
    out = gw.map_messages(messages)
    assert out[0]["role"] == "tool"
    assert out[0]["tool_call_id"] == "c1"
    assert "good" in out[0]["content"]


def test_a_retry_aimed_at_a_call_is_a_tool_message_and_a_bare_one_is_user_feedback() -> (
    None
):
    aimed = gw.map_messages(
        [
            ModelRequest(
                parts=[
                    RetryPromptPart(
                        content="try again", tool_name="interact", tool_call_id="c1"
                    )
                ]
            )
        ]
    )
    assert aimed[0]["role"] == "tool"
    assert aimed[0]["tool_call_id"] == "c1"

    bare = gw.map_messages([ModelRequest(parts=[RetryPromptPart(content="try again")])])
    assert bare[0]["role"] == "user"


def test_an_assistant_turn_carries_its_tool_calls_and_drops_thinking() -> None:
    """Reasoning is not part of the conversation a provider expects back."""
    messages = [
        ModelResponse(
            parts=[
                ThinkingPart(content="deliberating"),
                TextPart(content="Here you go."),
                ToolCallPart(
                    tool_name="interact",
                    args={"type": "confirm", "prompt": "Ready?"},
                    tool_call_id="c9",
                ),
            ]
        )
    ]
    out = gw.map_messages(messages)
    assert len(out) == 1
    assert out[0]["content"] == "Here you go."
    assert "deliberating" not in json.dumps(out)
    call = out[0]["tool_calls"][0]
    assert call["id"] == "c9"
    assert call["function"]["name"] == "interact"
    assert json.loads(call["function"]["arguments"])["prompt"] == "Ready?"


def test_tools_are_described_for_the_chat_api() -> None:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {"key": {"type": "string"}},
    }
    params = _params(
        [
            ToolDefinition(
                name="remember", description="store it", parameters_json_schema=schema
            )
        ]
    )
    tools = gw.map_tools(params)
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "remember"
    assert tools[0]["function"]["parameters"] == schema


# -- stream reassembly -------------------------------------------------------------------


async def test_text_chunks_become_one_text_part() -> None:
    response = await _drain(
        [
            FakeChunk(result="Hello "),
            FakeChunk(result="learner."),
            FakeChunk(finish_reason="stop"),
        ]
    )
    assert [p.content for p in response.parts if isinstance(p, TextPart)] == [
        "Hello learner."
    ]


async def test_tool_arguments_split_across_chunks_are_stitched_back_together() -> None:
    """A provider sends one call's arguments in fragments; the index is what joins them."""
    spec = {"type": "confirm", "prompt": "Ready?"}
    raw = json.dumps(spec)
    response = await _drain(
        [
            FakeChunk(
                tool_call_deltas=[
                    {"index": 0, "id": "c1", "name": "interact", "arguments": raw[:10]}
                ]
            ),
            FakeChunk(
                tool_call_deltas=[
                    {"index": 0, "id": None, "name": None, "arguments": raw[10:]}
                ]
            ),
            FakeChunk(finish_reason="tool_calls"),
        ]
    )
    calls = [p for p in response.parts if isinstance(p, ToolCallPart)]
    assert len(calls) == 1
    assert calls[0].tool_name == "interact"
    assert calls[0].tool_call_id == "c1"
    assert json.loads(calls[0].args_as_json_str()) == spec


async def test_two_calls_in_one_turn_stay_separate() -> None:
    """The engine raises several interactions in a turn; they must not merge into one call."""
    response = await _drain(
        [
            FakeChunk(
                tool_call_deltas=[
                    {"index": 0, "id": "a", "name": "interact", "arguments": '{"a":1}'},
                    {"index": 1, "id": "b", "name": "interact", "arguments": '{"b":2}'},
                ]
            ),
            FakeChunk(finish_reason="tool_calls"),
        ]
    )
    calls = [p for p in response.parts if isinstance(p, ToolCallPart)]
    assert [c.tool_call_id for c in calls] == ["a", "b"]
    assert json.loads(calls[0].args_as_json_str()) == {"a": 1}
    assert json.loads(calls[1].args_as_json_str()) == {"b": 2}


async def test_a_tool_calls_finish_reason_is_mapped_to_pydantic_ais_name() -> None:
    response = gw.GatewayStreamedResponse(
        model_request_parameters=_params(),
        _model_name="test-model",
        _chunks=iter([FakeChunk(finish_reason="tool_calls")]),
    )
    async for _ in response:
        pass
    assert response.finish_reason == "tool_call"


async def test_usage_is_carried_through() -> None:
    response = gw.GatewayStreamedResponse(
        model_request_parameters=_params(),
        _model_name="test-model",
        _chunks=iter(
            [
                FakeChunk(result="hi"),
                FakeChunk(usage=FakeUsage(prompt_tokens=11, completion_tokens=7)),
            ]
        ),
    )
    async for _ in response:
        pass
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 7


# -- driving the real engine -------------------------------------------------------------


async def test_the_engine_runs_a_full_interaction_cycle_through_the_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The point of this adapter: the engine pauses, resumes and finishes over chat_llm.

    `chat_llm` is faked, so this asserts the wiring rather than any model behaviour: the request
    the gateway builds, the parts it reassembles, and that pydantic-ai accepts both.
    """
    from flaskr.service.learn.agent.engine import (
        Engine,
        InteractionRequest,
        InteractionResponseTurn,
        MemoryUpdated,
        TurnDone,
    )

    spec = {
        "type": "single",
        "prompt": "How do you feel?",
        "options": [{"display": "Good", "value": "good"}],
        "variable": "feeling",
    }
    seen: list[list[dict]] = []
    turns = {"n": 0}

    def fake_chat_llm(**kwargs: object) -> Iterator[FakeChunk]:
        # Mirror what chat_llm does with the span, so a missing one fails here too.
        kwargs["span"].generation(name=kwargs["generation_name"])
        seen.append(kwargs["messages"])
        turns["n"] += 1
        if turns["n"] == 1:
            yield FakeChunk(result="Hello.\n")
            yield FakeChunk(
                tool_call_deltas=[
                    {
                        "index": 0,
                        "id": "q1",
                        "name": "interact",
                        "arguments": json.dumps(spec),
                    }
                ]
            )
            yield FakeChunk(finish_reason="tool_calls")
        else:
            yield FakeChunk(result="Thanks for telling me.\n")
            yield FakeChunk(finish_reason="stop")

    monkeypatch.setattr(gw, "chat_llm", fake_chat_llm)

    span = FakeSpan()
    model = gw.GatewayModel(app=None, model="test-model", user_id="u1", span=span)
    engine = Engine(model)
    session = await engine.new_session("Ask the learner how they feel.")

    first = [e async for e in engine.run_turn(session)]
    requests = [e for e in first if isinstance(e, InteractionRequest)]
    assert requests, [type(e).__name__ for e in first]
    request = requests[0]
    assert request.spec.variable == "feeling"
    assert isinstance(first[-1], TurnDone)
    assert first[-1].reason == "interaction"

    second = [
        e
        async for e in engine.run_turn(
            session, InteractionResponseTurn(values=["Good"])
        )
    ]
    assert any(isinstance(e, MemoryUpdated) and e.key == "feeling" for e in second)
    assert session.memory["feeling"] == "good"

    # The resumed request carries the tool result back, keyed by the call it answers.
    resumed = seen[-1]
    assert resumed[0]["role"] == "system"  # exactly one, and it leads
    assert sum(1 for m in resumed if m["role"] == "system") == 1
    tool_messages = [m for m in resumed if m["role"] == "tool"]
    assert tool_messages
    assert tool_messages[-1]["tool_call_id"] == "q1"


async def test_the_gateway_sends_tools_but_never_forces_a_choice() -> None:
    """Some providers reject tool_choice while reasoning, and the engine relies on the model."""
    captured: dict[str, Any] = {}

    def fake_chat_llm(**kwargs: object) -> Iterator[FakeChunk]:
        kwargs["span"].generation(name=kwargs["generation_name"])
        captured.update(kwargs)
        yield FakeChunk(result="ok", finish_reason="stop")

    span = FakeSpan()
    model = gw.GatewayModel(app=None, model="test-model", user_id="u1", span=span)
    params = _params(
        [
            ToolDefinition(
                name="interact",
                description="ask",
                parameters_json_schema={"type": "object"},
            )
        ]
    )
    import flaskr.service.learn.agent.gateway_model as module

    original, module.chat_llm = module.chat_llm, fake_chat_llm
    try:
        list(
            model._stream([ModelRequest(parts=[UserPromptPart(content="hi")])], params)
        )
    finally:
        module.chat_llm = original

    assert [t["function"]["name"] for t in captured["tools"]] == ["interact"]
    assert "tool_choice" not in captured
    assert captured["emit_tool_calls"] is True


def test_agent_instructions_reach_the_model_as_the_system_message() -> None:
    """An agent built with `instructions=` carries them on the request, not among its parts.

    Reading only the parts drops the engine's entire system prompt, and silently: the call still
    succeeds, the model just has no instructions.
    """
    messages = [
        ModelRequest(parts=[UserPromptPart(content="hi")], instructions="be brief")
    ]
    out = gw.map_messages(messages)
    assert out[0] == {"role": "system", "content": "be brief"}


def test_repeated_instructions_are_not_stacked_up() -> None:
    """The same instructions ride on every request in the history."""
    messages = [
        ModelRequest(parts=[UserPromptPart(content="one")], instructions="be brief"),
        ModelResponse(parts=[TextPart(content="ok")]),
        ModelRequest(parts=[UserPromptPart(content="two")], instructions="be brief"),
    ]
    out = gw.map_messages(messages)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "user"]
    assert out[0]["content"] == "be brief"


# -- review follow-up --------------------------------------------------------------------


def test_a_model_cannot_be_built_without_a_span() -> None:
    """`chat_llm` opens a generation on the span before reaching a provider, so None cannot work."""
    with pytest.raises(TypeError):
        gw.GatewayModel(app=None, model="test-model", user_id="u1")  # type: ignore[call-arg]


def test_only_the_current_instructions_are_sent() -> None:
    """Each request records what applied when it was made; older values are superseded."""
    messages = [
        ModelRequest(
            parts=[UserPromptPart(content="one")], instructions="teach section 1"
        ),
        ModelResponse(parts=[TextPart(content="ok")]),
        ModelRequest(
            parts=[UserPromptPart(content="two")], instructions="teach section 2"
        ),
    ]
    out = gw.map_messages(messages)
    assert out[0]["content"] == "teach section 2"
    assert "section 1" not in out[0]["content"]


def test_a_withheld_tool_is_not_sent_to_the_provider() -> None:
    """The adapter sends the resolved set, not every authored tool.

    A run can withhold a tool until it is revealed; sending its schema anyway would let the model
    call a capability the engine has not offered.
    """
    visible = ToolDefinition(
        name="interact", description="ask", parameters_json_schema={"type": "object"}
    )
    withheld = ToolDefinition(
        name="delete_draft",
        description="destructive",
        parameters_json_schema={"type": "object"},
    )
    params = ModelRequestParameters(
        function_tools=[visible, withheld],
        output_tools=[],
        tool_visibility={"interact": "visible", "delete_draft": "withheld"},
    )
    names = [t["function"]["name"] for t in gw.map_tools(params)]
    assert names == ["interact"]


def test_prepare_request_runs_before_the_tools_are_read() -> None:
    """Skipping it leaves tool visibility unresolved and the engine's settings unmerged."""
    captured: dict[str, Any] = {}

    def fake_chat_llm(**kwargs: object) -> Iterator[FakeChunk]:
        kwargs["span"].generation(name=kwargs["generation_name"])
        captured.update(kwargs)
        yield FakeChunk(result="ok", finish_reason="stop")

    params = ModelRequestParameters(
        function_tools=[
            ToolDefinition(
                name="interact",
                description="ask",
                parameters_json_schema={"type": "object"},
            )
        ],
        output_tools=[],
    )
    assert params.tool_visibility is None  # unresolved as authored

    model = gw.GatewayModel(app=None, model="test-model", user_id="u1", span=FakeSpan())
    _, prepared = model.prepare_request(None, params)
    assert prepared.tool_visibility == {"interact": "visible"}
    assert captured == {}


async def test_cancelling_a_stream_closes_the_gateway_generator() -> None:
    """A learner who stops a lesson must not leave the chat_llm generator open."""
    closed = {"yes": False}

    def chunks() -> Iterator[FakeChunk]:
        try:
            yield FakeChunk(result="one")
            yield FakeChunk(result="two")
        finally:
            closed["yes"] = True

    response = gw.GatewayStreamedResponse(
        model_request_parameters=_params(),
        _model_name="test-model",
        _chunks=chunks(),
    )
    iterator = response.__aiter__()
    await iterator.__anext__()  # start the generator, then abandon it
    await response.close_stream()
    assert closed["yes"] is True
    await response.close_stream()  # idempotent
