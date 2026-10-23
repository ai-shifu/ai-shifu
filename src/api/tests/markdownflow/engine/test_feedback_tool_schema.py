"""Check model-visible feedback requirements alongside unchanged native validation."""

import json
from collections.abc import AsyncIterator

import pytest
from jsonschema import Draft202012Validator
from markdownflow.engine import Engine, InteractionResponseTurn, Session
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from .test_direction_feedback import (
    DISPLAY,
    SCRIPT,
    WRONG,
    _call,
    _collect,
    _direction,
    _text,
)


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("supported", [False, True])
async def test_feedback_schema_requires_a_branch_only_for_a_supported_reply(
    reload: bool, enabled: bool, supported: bool
) -> None:
    """Expose required non-null branches on real resumed SDK calls without global mutation."""
    calls = 0
    question = "Please explain briefly, then keep my answer input pending."
    args = {"type": "text", "prompt": "", "placeholder": "Explanation"}
    review = {
        "answer_id": "original",
        "phase": "clarification",
        "submission_quote": question,
        "reason": "Respond to the knowledge question and retain the pending exercise.",
    }

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Validate offered JSON schemas, then use the actual native deferred tool."""
        nonlocal calls
        calls += 1
        definitions = {t.name: t for t in info.function_tools}
        interact = Draft202012Validator(definitions["interact"].parameters_json_schema)
        finish = Draft202012Validator(definitions["finish"].parameters_json_schema)
        required = enabled and supported and calls == 2
        assert interact.is_valid(args) is not required
        assert finish.is_valid({"summary": "Done."}) is not required
        assert interact.is_valid({**args, "review": None}) is not required
        assert interact.is_valid({**args, "direction": None}) is not required
        assert interact.is_valid({**args, "review": review}) is not required
        assert interact.is_valid({**args, "direction": _direction()}) is not required
        assert finish.is_valid({"summary": "Done.", "review": review}) is not required
        if not required:
            assert (
                "feedback"
                not in definitions["interact"].parameters_json_schema["properties"]
            )
            assert (
                "feedback"
                not in definitions["finish"].parameters_json_schema["properties"]
            )
        if required:
            assert (
                "review"
                not in definitions["interact"].parameters_json_schema["properties"]
            )
            assert (
                "direction"
                not in definitions["interact"].parameters_json_schema["properties"]
            )
            assert "anyOf" not in definitions["interact"].parameters_json_schema
            assert interact.is_valid({**args, "feedback": review})
            assert interact.is_valid({**args, "feedback": _direction()})
            assert not interact.is_valid({**args, "feedback": None})
            assert finish.is_valid({"summary": "Done.", "feedback": review})
        if calls == 2:
            yield "A concise knowledge explanation."
            yield _call(
                {**args, **({"feedback": review} if required else {})}, "continued"
            )
        else:
            yield _call(args, "original")

    engine = Engine(
        FunctionModel(stream_function=stream),
        feedback_contract=enabled,
        request_limit=1,
    )
    script = (
        "Explain briefly.\n?[...Explanation]\n"
        if supported
        else "Teach an open conversation."
    )
    session = await engine.new_session(script)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    before = session.script.script
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=question))
    )
    assert _text(events) == "A concise knowledge explanation."
    assert session.pending[0].tool_call_id == "continued"
    assert not session.finished
    assert not session.all_memory()
    assert session.script.script == before
    # A fresh session on the same engine must regain the initial optional schema.
    fresh = await engine.new_session(script)
    await _collect(engine.run_turn(fresh))
    assert calls == 3


@pytest.mark.anyio
@pytest.mark.parametrize("same_response", [False, True])
async def test_declared_branch_keeps_legacy_sibling_and_later_calls_valid(
    same_response: bool,
) -> None:
    """Keep response-wide native validation and optional later calls after a declaration."""
    calls = 0
    args = {"type": "text", "prompt": "", "placeholder": "Explanation"}
    question = "Remember that I prefer concise examples, and explain briefly."
    review = {
        "answer_id": "original",
        "phase": "clarification",
        "submission_quote": question,
        "reason": "Honor the requested preference and explanation.",
    }

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Use a memory sibling to declare the branch, then collect the current answer."""
        nonlocal calls
        calls += 1
        definitions = {t.name: t for t in info.function_tools}
        required = calls == 2
        for name, payload in [("interact", args), ("finish", {"summary": "Done."})]:
            validator = Draft202012Validator(definitions[name].parameters_json_schema)
            assert validator.is_valid(payload) is not required
        if calls == 1:
            yield _call(args, "original")
        elif calls == 2:
            yield "Your preference is retained."
            output = {
                0: DeltaToolCall(
                    name="remember",
                    json_args=json.dumps(
                        {
                            "key": "preference",
                            "value": "concise examples",
                            "review": review,
                        }
                    ),
                    tool_call_id="preference",
                )
            }
            if same_response:
                # The model schema advertises a canonical declaration on interact;
                # existing callers may still declare it on a sibling native call.
                output[1] = DeltaToolCall(
                    name="interact",
                    json_args=json.dumps(args),
                    tool_call_id="continued",
                )
            yield output
        else:
            assert calls == 3
            assert not same_response
            yield "A concise explanation."
            yield _call(args, "continued")

    engine = Engine(
        FunctionModel(stream_function=stream), feedback_contract=True, request_limit=2
    )
    session = await engine.new_session("Explain briefly.\n?[...Explanation]\n")
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=question))
    )
    assert "Your preference is retained." in _text(events)
    assert session.memory["preference"] == "concise examples"
    assert session.pending[0].tool_call_id == "continued"
    assert not session.finished
    assert calls == (2 if same_response else 3)


@pytest.mark.anyio
@pytest.mark.parametrize("conflict", [None, "reason", "phase"])
async def test_multiple_interactions_share_one_exact_feedback_decision(
    conflict: str | None,
) -> None:
    """Keep schema-valid simultaneous inputs and reject inconsistent sibling decisions."""
    calls = 0
    answer = "A complete answer."
    script = "Explain.\n?[...Original]\nThen ask both fields together.\n?[...First]\n?[...Second]\n"
    review = {
        "answer_id": "original",
        "phase": "accepted",
        "submission_quote": answer,
        "reason": "The actual submitted answer meets the authored requirement.",
    }

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Exercise real native parallel deferred calls under the offered schema."""
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Original"}, "original"
            )
            return
        assert calls <= 3
        schema = next(
            t.parameters_json_schema
            for t in info.function_tools
            if t.name == "interact"
        )
        validator = Draft202012Validator(schema)
        second = dict(review)
        invalid = conflict is not None and calls == 2
        if invalid:
            second[conflict] = (
                "clarification" if conflict == "phase" else "A conflicting explanation."
            )
        payloads = [
            {"type": "text", "prompt": "", "placeholder": "First", "feedback": review},
            {"type": "text", "prompt": "", "placeholder": "Second", "feedback": second},
        ]
        assert all(validator.is_valid(p) for p in payloads)
        yield (
            "Undisplayed conflicting feedback." if invalid else "Accepted explanation."
        )
        yield {
            i: DeltaToolCall(
                name="interact",
                json_args=json.dumps(p),
                tool_call_id=p["placeholder"].lower(),
            )
            for i, p in enumerate(payloads)
        }

    engine = Engine(
        FunctionModel(stream_function=stream), feedback_contract=True, request_limit=2
    )
    session = await engine.new_session(script)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=answer))
    )
    assert _text(events) == "Accepted explanation."
    assert [p.spec.placeholder for p in session.pending] == ["First", "Second"]
    assert not session.finished
    assert not session.all_memory()
    assert session.script.script == script
    assert "Undisplayed conflicting feedback." not in session.dumps()
    assert calls == (2 if conflict is None else 3)


@pytest.mark.anyio
@pytest.mark.parametrize("provider", ["ark", "openai", "dashscope"])
async def test_provider_transforms_keep_required_feedback(provider: str) -> None:
    """Retain the actual SDK requirement through pinned provider request conversion."""
    import copy

    from flaskr.api.llm.markdownflow_model import map_tools
    from litellm.llms.dashscope.chat.transformation import DashScopeChatConfig
    from litellm.llms.openai.chat.gpt_transformation import OpenAIGPTConfig
    from litellm.llms.volcengine.chat.transformation import VolcEngineChatConfig
    from pydantic_ai.models import ModelRequestParameters

    calls = 0
    args = {"type": "text", "prompt": "", "placeholder": "Explanation"}
    review = {
        "answer_id": "original",
        "phase": "clarification",
        "submission_quote": "Explain briefly.",
        "reason": "Answer the question and retain the authored exercise.",
    }

    async def stream(_messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator:
        """Inspect converted offered tools without making a provider request."""
        nonlocal calls
        calls += 1
        if calls == 2:
            config, model, endpoint = {
                "ark": (
                    VolcEngineChatConfig(),
                    "deepseek-v4-1-flash-260910",
                    "https://ark.cn-beijing.volces.com/api/v3",
                ),
                "openai": (
                    OpenAIGPTConfig(),
                    "gpt-6-astra",
                    "https://api.openai.com/v1",
                ),
                "dashscope": (
                    DashScopeChatConfig(),
                    "glm-5.3",
                    "https://dashscope.aliyuncs.com/compatible-mode/v1",
                ),
            }[provider]
            tools = map_tools(
                ModelRequestParameters(function_tools=info.function_tools)
            )
            body = config.transform_request(
                model=model,
                messages=[{"role": "user", "content": "Synthetic schema check."}],
                optional_params={"tools": copy.deepcopy(tools)},
                litellm_params={
                    "custom_llm_provider": "volcengine"
                    if provider == "ark"
                    else provider,
                    "api_base": endpoint,
                },
                headers={},
            )
            schema = next(
                t["function"]["parameters"]
                for t in body["tools"]
                if t["function"]["name"] == "interact"
            )
            assert "feedback" in schema["required"]
            validator = Draft202012Validator(schema)
            assert not validator.is_valid(args)
            assert not validator.is_valid({**args, "feedback": None})
            assert validator.is_valid({**args, "feedback": review})
            assert validator.is_valid({**args, "feedback": _direction()})
            assert not validator.is_valid({**args, "feedback": json.dumps(review)})
            for name in ("interact", "finish"):
                offered = next(
                    t["function"]["parameters"]
                    for t in body["tools"]
                    if t["function"]["name"] == name
                )
                assert offered["properties"]["feedback"]["type"] == "object"
            yield "A concise explanation."
            yield _call({**args, "feedback": review}, "continued")
        else:
            yield _call(args, "original")

    engine = Engine(
        FunctionModel(stream_function=stream), feedback_contract=True, request_limit=1
    )
    session = await engine.new_session("Explain briefly.\n?[...Explanation]\n")
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text="Explain briefly."))
    )
    assert _text(events) == "A concise explanation."
    assert calls == 2
    assert not session.finished


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_feedback_string_is_rejected_without_rewriting_native_evidence(
    reload: bool,
) -> None:
    """Require a corrected object while retaining the original invalid arguments."""
    question = "Explain briefly."
    args = {"type": "text", "prompt": "", "placeholder": "Explanation"}
    review = {
        "answer_id": "original",
        "phase": "clarification",
        "submission_quote": question,
        "reason": "Answer the side question and keep the authored input pending.",
    }
    serialized = json.dumps(review)
    calls = 0

    async def stream(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        """Run a genuine SDK validation retry, without parsing strings in the host."""
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(args, "original")
        elif calls == 2:
            yield "Undisplayed invalid-object explanation."
            yield _call({**args, "feedback": serialized}, "invalid")
        else:
            assert "Input should be an object" in str(messages)
            yield "Corrected object explanation."
            yield _call({**args, "feedback": review}, "continued")

    engine = Engine(
        FunctionModel(stream_function=stream), feedback_contract=True, request_limit=2
    )
    session = await engine.new_session("Explain briefly.\n?[...Explanation]\n")
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=question))
    )
    assert calls == 3
    assert _text(events) == "Corrected object explanation."
    assert session.pending[0].tool_call_id == "continued"
    assert not session.finished
    assert not session.all_memory()
    assert "Undisplayed invalid-object explanation." not in session.dumps()
    invalid = [
        part
        for message in session.messages
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart) and part.tool_call_id == "invalid"
    ]
    assert len(invalid) == 1
    assert invalid[0].args_as_dict()["feedback"] == serialized


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("sibling_first", [None, False, True])
async def test_canonical_direction_preserves_native_boundaries(
    reload: bool,
    sibling_first: bool | None,
) -> None:
    """Keep grounded display/history and reject sibling writes in either tool order."""
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        """Deliver one grounded direction, repairing prohibited sibling calls first."""
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
            return
        direction = _direction()
        payload = {
            "type": "text",
            "prompt": "",
            "placeholder": "Answer",
            "feedback": direction,
        }
        output = _call(payload, "corrected")
        if calls == 2 and sibling_first is not None:
            sibling = DeltaToolCall(
                name="remember",
                json_args='{"key":"unsafe","value":"must not write"}',
                tool_call_id="unsafe",
            )
            output = (
                {0: sibling, 1: output[0]}
                if sibling_first
                else {0: output[0], 1: sibling}
            )
            yield "Rejected free reasoning."
        yield output

    engine = Engine(
        FunctionModel(stream_function=stream), feedback_contract=True, request_limit=2
    )
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert _text(events) == DISPLAY
    assert not session.all_memory()
    assert not session.finished
    assert len(session.pending) == 1
    assert session.pending[0].spec.placeholder == "Answer"
    assert "Rejected free reasoning." not in session.dumps()
    assert any(
        p.args_as_dict().get("feedback") == _direction()
        for m in session.messages
        if isinstance(m, ModelResponse)
        for p in m.parts
        if isinstance(p, ToolCallPart)
    )
    assert calls == (2 if sibling_first is None else 3)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad", ["legacy_direction", "legacy_review", "ambiguous", "non_object"]
)
async def test_canonical_feedback_rejects_mixed_or_ambiguous_declarations(
    bad: str,
) -> None:
    """Reject conflicting spellings before display without losing original evidence."""
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        """Repair a rejected declaration using the same grounded direction."""
        nonlocal calls
        calls += 1
        payload = {"type": "text", "prompt": "", "placeholder": "Answer"}
        if calls > 1:
            payload["feedback"] = _direction()
        if calls == 2:
            if bad == "legacy_direction":
                payload["direction"] = _direction()
            elif bad == "legacy_review":
                payload["review"] = {
                    "answer_id": "original",
                    "phase": "clarification",
                    "submission_quote": WRONG,
                    "reason": "Conflicting interpretation.",
                }
            elif bad == "ambiguous":
                payload["feedback"] = {**_direction(), "phase": "clarification"}
            else:
                payload["feedback"] = "not an object"
            yield "Rejected ambiguous feedback."
        yield _call(payload, "original" if calls == 1 else "corrected")

    engine = Engine(
        FunctionModel(stream_function=stream), feedback_contract=True, request_limit=2
    )
    session = await engine.new_session(SCRIPT)
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=WRONG))
    )
    assert calls == 3
    assert _text(events) == DISPLAY
    assert "Rejected ambiguous feedback." not in session.dumps()
    assert not session.all_memory()
    assert not session.finished


@pytest.mark.anyio
@pytest.mark.parametrize("mixed", [False, True])
async def test_canonical_finish_keeps_review_validation(mixed: bool) -> None:
    """Finish with one valid canonical review, retrying mixed legacy spelling."""
    calls = 0
    review = {
        "answer_id": "original",
        "phase": "accepted",
        "submission_quote": "Complete.",
        "reason": "The answer meets the authored ending.",
    }

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        """Use real SDK terminal validation and retain only accepted prose."""
        nonlocal calls
        calls += 1
        if calls == 1:
            yield _call(
                {"type": "text", "prompt": "", "placeholder": "Answer"}, "original"
            )
            return
        if calls == (4 if mixed else 3):
            return
        invalid = mixed and calls == 2
        payload = {"summary": "Completed.", "feedback": review}
        if invalid:
            payload["review"] = review
        yield "Rejected mixed finish." if invalid else "Authored completion."
        yield {
            0: DeltaToolCall(
                name="finish", json_args=json.dumps(payload), tool_call_id="finish"
            )
        }

    engine = Engine(
        FunctionModel(stream_function=stream), feedback_contract=True, request_limit=3
    )
    session = await engine.new_session(
        "Ask for a complete answer.\n?[...Answer]\nAccept and finish."
    )
    await _collect(engine.run_turn(session))
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text="Complete."))
    )
    assert _text(events) == "Authored completion."
    assert session.finished
    assert "Rejected mixed finish." not in session.dumps()
    assert calls == (4 if mixed else 3)
