"""Check model-visible feedback requirements alongside unchanged native validation."""

import json
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import Engine, InteractionResponseTurn, Session
from jsonschema import Draft202012Validator
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from .test_direction_feedback import _call, _collect, _direction, _text


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
        assert interact.is_valid({**args, "review": review})
        assert interact.is_valid({**args, "direction": _direction()})
        assert finish.is_valid({"summary": "Done.", "review": review})
        if calls == 2:
            yield "A concise knowledge explanation."
            yield _call(
                {**args, **({"review": review} if required else {})}, "continued"
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
            {"type": "text", "prompt": "", "placeholder": "First", "review": review},
            {"type": "text", "prompt": "", "placeholder": "Second", "review": second},
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
