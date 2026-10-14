"""Exercise computed artifacts through native tools, accepted delivery and reload."""

from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import Engine, InteractionResponseTurn, Session
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .test_computed_example import _loop
from .test_direction_feedback import _call, _collect, _text


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_native_computed_table_pauses_once_and_survives_reload(
    reload: bool,
) -> None:
    """Bind rendered numbers to saved teaching without an extra model request."""
    calls = 0

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Return a single tool response at each real learner boundary."""
        nonlocal calls
        calls += 1
        assert (
            "computed_example"
            in info.function_tools[0].parameters_json_schema["properties"]
        ) is (calls > 1)
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "first"
            )
        else:
            assert (
                "Show two iterations."
                in ModelMessagesTypeAdapter.dump_json(messages).decode()
            )
            yield "A generated illustration follows.\n\n"
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "computed_example": _loop(),
                },
                "second",
            )

    engine = Engine(
        FunctionModel(stream_function=stream), computed_examples=True, request_limit=1
    )
    session = await engine.new_session("Explain counters.\n?[...Answer]\n")
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    original = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text="Show two iterations."))
    )
    assert calls == 2
    assert "| 5 | 101 | 102 | 1 | 3 |" in _text(events)
    assert session.pending[0].tool_call_id == "second"
    assert not session.finished
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == original
    restored = Session.loads(session.dumps())
    assert (
        "| 5 | 101 | 102 | 1 | 3 |"
        in ModelMessagesTypeAdapter.dump_json(restored.messages).decode()
    )


@pytest.mark.anyio
async def test_missing_initial_value_retries_without_displaying_rejected_prose() -> (
    None
):
    """Retain an invalid native payload without laundering its prose into teaching."""
    calls = 0

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """First omit a source value, then correct the complete response."""
        nonlocal calls
        calls += 1
        assert (
            "computed_example"
            in info.function_tools[0].parameters_json_schema["properties"]
        ) is (calls > 1)
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
            return
        example = _loop()
        if calls == 2:
            del example["registers"]["R1"]
            yield "Rejected numeric assertion: R1 becomes four."
        else:
            assert "R1" in ModelMessagesTypeAdapter.dump_json(messages).decode()
            yield "Accepted general explanation.\n\n"
        yield _call(
            {
                "type": "text",
                "prompt": "",
                "placeholder": "Answer",
                "computed_example": example,
            },
            f"attempt{calls}",
        )

    engine = Engine(
        FunctionModel(stream_function=stream), computed_examples=True, request_limit=2
    )
    session = await engine.new_session("Explain counters.\n?[...Answer]\n")
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text="Show two iterations."))
    )
    assert calls == 3
    assert "Rejected numeric assertion" not in _text(events)
    assert "Accepted general explanation" in _text(events)
    assert "| 5 | 101 | 102 | 1 | 3 |" in _text(events)
    history = ModelMessagesTypeAdapter.dump_json(session.messages).decode()
    assert "Rejected numeric assertion" not in history
    calls_saved = [
        part.args_as_dict()
        for message in session.messages
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    ]
    assert len(calls_saved) == 3
    assert "R1" not in calls_saved[1]["computed_example"]["registers"]
    assert calls_saved[2]["computed_example"] == _loop()
    assert session.pending[0].tool_call_id == "attempt3"


@pytest.mark.anyio
async def test_computed_payload_with_memory_sibling_cannot_write_or_display() -> None:
    """Reject the complete mixed response before a sibling writes learner memory."""
    from pydantic_ai.models.function import DeltaToolCall

    calls = 0

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Attempt mixed calls, then return the one existing input without a side effect."""
        nonlocal calls
        calls += 1
        assert info.function_tools
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
            return
        if calls == 2:
            yield "Withheld mixed response."
            batch = _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "computed_example": _loop(),
                },
                "mixed",
            )
            batch[1] = DeltaToolCall(
                name="remember",
                json_args='{"key":"bad_note","value":"must not persist"}',
                tool_call_id="memory",
            )
            yield batch
        else:
            assert (
                "sole existing interact"
                in ModelMessagesTypeAdapter.dump_json(messages).decode()
            )
            yield "Accepted response."
            yield _call(
                {
                    "type": "text",
                    "prompt": "",
                    "placeholder": "Answer",
                    "computed_example": _loop(),
                },
                "accepted",
            )

    engine = Engine(
        FunctionModel(stream_function=stream), computed_examples=True, request_limit=2
    )
    session = await engine.new_session("Explain a counter.\n?[...Answer]\n")
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text="Show two iterations."))
    )
    assert session.memory == {}
    assert calls == 3
    assert "Withheld mixed response" not in _text(events)
    assert session.pending[0].tool_call_id == "accepted"
    assert "| 5 | 101 | 102 | 1 | 3 |" in _text(events)


@pytest.mark.anyio
async def test_portable_schema_does_not_offer_computed_artifacts() -> None:
    """Keep the existing tool payload and supporting definitions off by default."""

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Inspect the actual SDK definition without enabling a host capability."""
        tool = info.function_tools[0]
        assert "computed_example" not in tool.parameters_json_schema["properties"]
        assert "ComputedExample" not in tool.parameters_json_schema.get("$defs", {})
        yield _call({"type": "text", "prompt": "", "placeholder": "Answer"}, "ordinary")

    engine = Engine(FunctionModel(stream_function=stream), request_limit=1)
    session = await engine.new_session("?[...Answer]")
    await _collect(engine.run_turn(session))
    assert session.pending[0].tool_call_id == "ordinary"


@pytest.mark.anyio
@pytest.mark.parametrize("provider", ["ark", "openai", "dashscope"])
async def test_provider_conversion_retains_example_and_feedback_contract(
    provider: str,
) -> None:
    """Inspect the real mapped tool schema without making a provider request."""
    import copy
    import json

    from flaskr.service.learn.agent.gateway_model import map_tools
    from jsonschema import Draft202012Validator
    from litellm.llms.dashscope.chat.transformation import DashScopeChatConfig
    from litellm.llms.openai.chat.gpt_transformation import OpenAIGPTConfig
    from litellm.llms.volcengine.chat.transformation import VolcEngineChatConfig
    from pydantic_ai.models import ModelRequestParameters

    calls = 0
    question = "Show a permitted numeric example."
    review = {
        "answer_id": "original",
        "phase": "clarification",
        "submission_quote": question,
        "reason": "Answer the knowledge question and retain the authored input.",
    }
    ordinary = {"type": "text", "prompt": "", "placeholder": "Answer"}

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Pass the current SDK definitions through each pinned provider adapter."""
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(ordinary, "original")
            return
        config, model, endpoint = {
            "ark": (
                VolcEngineChatConfig(),
                "deepseek-v4-1-flash-260910",
                "https://ark.cn-beijing.volces.com/api/v3",
            ),
            "openai": (OpenAIGPTConfig(), "gpt-6-astra", "https://api.openai.com/v1"),
            "dashscope": (
                DashScopeChatConfig(),
                "glm-5.3",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
        }[provider]
        tools = map_tools(ModelRequestParameters(function_tools=info.function_tools))
        body = config.transform_request(
            model=model,
            messages=[{"role": "user", "content": "Synthetic schema check."}],
            optional_params={"tools": copy.deepcopy(tools)},
            litellm_params={
                "custom_llm_provider": "volcengine" if provider == "ark" else provider,
                "api_base": endpoint,
            },
            headers={},
        )
        schema = next(
            t["function"]["parameters"]
            for t in body["tools"]
            if t["function"]["name"] == "interact"
        )
        args = {**ordinary, "feedback": review, "computed_example": _loop()}
        validator = Draft202012Validator(schema)
        assert "feedback" in schema["required"]
        assert schema["properties"]["computed_example"]["type"] == "object"
        assert validator.is_valid(args)
        assert not validator.is_valid({**args, "feedback": json.dumps(review)})
        assert not validator.is_valid({**args, "computed_example": json.dumps(_loop())})
        assert not validator.is_valid(
            {**args, "computed_example": {**_loop(), "trace": []}}
        )
        yield "A general explanation.\n\n"
        yield _call(args, "continued")

    engine = Engine(
        FunctionModel(stream_function=stream),
        computed_examples=True,
        feedback_contract=True,
        request_limit=1,
    )
    session = await engine.new_session(
        "Explain briefly using permitted examples.\n?[...Answer]\n"
    )
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=question))
    )
    assert calls == 2
    assert "| 5 | 101 | 102 | 1 | 3 |" in _text(events)


@pytest.mark.anyio
async def test_capability_preserves_initial_content_streaming() -> None:
    """Initial text must arrive before the model finishes producing its first response."""
    import asyncio

    import anyio
    from flaskr.service.learn.agent.engine import ContentDelta

    displayed = asyncio.Event()

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Wait for the consumer before providing the first interaction."""
        assert (
            "computed_example"
            not in info.function_tools[0].parameters_json_schema["properties"]
        )
        assert "# Computed numeric artifacts" not in (info.instructions or "")
        yield "Initial "
        yield "teaching."
        with anyio.fail_after(2):
            await displayed.wait()
        yield _call({"type": "text", "prompt": "", "placeholder": "Answer"}, "initial")

    engine = Engine(
        FunctionModel(stream_function=stream), computed_examples=True, request_limit=1
    )
    session = await engine.new_session("Explain briefly.\n?[...Answer]\n")
    events = []
    async for event in engine.run_turn(session):
        events.append(event)
        if isinstance(event, ContentDelta):
            displayed.set()
    assert displayed.is_set()
    assert _text(events) == "Initial teaching."
    assert session.pending[0].tool_call_id == "initial"


@pytest.mark.anyio
@pytest.mark.parametrize("invalid", ["string", "asserted_trace", "unavailable_pause"])
async def test_invalid_artifact_response_never_becomes_visible_teaching(
    invalid: str,
) -> None:
    """Reject malformed payloads and unavailable pauses without losing the artifact."""
    import json

    calls = 0

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Correct a rejected response using the original authored text input."""
        nonlocal calls
        calls += 1
        assert info.function_tools
        ordinary = {"type": "text", "prompt": "", "placeholder": "Answer"}
        if calls == 1:
            yield _call(ordinary, "original")
            return
        example = _loop()
        args = {**ordinary, "computed_example": example}
        if calls == 2:
            yield "Withheld artifact response."
            if invalid == "string":
                args["computed_example"] = json.dumps(example)
            elif invalid == "asserted_trace":
                args["computed_example"] = {**example, "trace": [{"R1": 4}]}
            else:
                args["type"] = "confirm"
        else:
            yield "Accepted artifact response."
        yield _call(args, f"artifact{calls}")

    engine = Engine(
        FunctionModel(stream_function=stream),
        computed_examples=True,
        pauses_from_notation=True,
        request_limit=2,
    )
    session = await engine.new_session("Explain briefly.\n?[...Answer]\n")
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text="Show two iterations."))
    )
    assert calls == 3
    assert "Withheld artifact response" not in _text(events)
    assert "Accepted artifact response" in _text(events)
    assert "| 5 | 101 | 102 | 1 | 3 |" in _text(events)
    assert session.pending[0].tool_call_id == "artifact3"
    restored = Session.loads(session.dumps())
    history = ModelMessagesTypeAdapter.dump_json(restored.messages).decode()
    assert "Withheld artifact response" not in history
    assert "| 5 | 101 | 102 | 1 | 3 |" in history


@pytest.mark.anyio
@pytest.mark.parametrize("arguments", ['{"computed_example":[', "[]"])
async def test_unparseable_interact_keeps_prose_held_through_native_retry(
    arguments: str,
) -> None:
    """Unknown JSON cannot bypass buffering when the separate feedback flag is off."""
    from pydantic_ai.models.function import DeltaToolCall

    calls = 0

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Return invalid native JSON before correcting the complete interaction."""
        nonlocal calls
        calls += 1
        assert info.function_tools
        ordinary = {"type": "text", "prompt": "", "placeholder": "Answer"}
        if calls == 1:
            yield _call(ordinary, "original")
        elif calls == 2:
            yield "Rejected unparseable response."
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=arguments, tool_call_id="unparseable"
                )
            }
        else:
            yield "Accepted computed response."
            yield _call({**ordinary, "computed_example": _loop()}, "accepted")

    engine = Engine(
        FunctionModel(stream_function=stream),
        computed_examples=True,
        feedback_contract=False,
        request_limit=2,
    )
    session = await engine.new_session("Explain briefly.\n?[...Answer]\n")
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text="Show two iterations."))
    )
    assert calls == 3
    assert "Rejected unparseable response" not in _text(events)
    assert "Accepted computed response" in _text(events)
    restored = Session.loads(session.dumps())
    history = ModelMessagesTypeAdapter.dump_json(restored.messages).decode()
    assert "Rejected unparseable response" not in history
    original_calls = [
        p
        for m in restored.messages
        if isinstance(m, ModelResponse)
        for p in m.parts
        if isinstance(p, ToolCallPart) and p.tool_call_id == "unparseable"
    ]
    assert len(original_calls) == 1
    assert original_calls[0].args == arguments
