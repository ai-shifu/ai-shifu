"""Exercise guided profiles through the real MarkdownFlow 2.0 interaction lifecycle."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from types import SimpleNamespace
from typing import Any

import pytest
from flask import Flask
from flaskr.common.cache_provider import InMemoryCacheProvider
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.service.profile_research.provider import create_profile_research_model
from flaskr.service.profile_research.runtime import (
    PROFILE_ONBOARDING_PURPOSE,
    PROFILE_RESEARCH_SESSION_TTL_SECONDS,
    ProfileResearchError,
    ProfileResearchRuntime,
    ProfileResearchValidationError,
    _ProfileResearchSessionStore,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.tools import ToolDefinition

StreamChunks = AsyncIterator[str | dict[int, DeltaToolCall]]
ModelScript = Callable[[list[ModelMessage], AgentInfo], StreamChunks]


def _tool_returns(messages: list[ModelMessage]) -> list[ToolReturnPart]:
    return [
        part
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "interact"
    ]


def _finished(messages: list[ModelMessage]) -> bool:
    return any(
        isinstance(message, ModelRequest)
        and any(
            isinstance(part, ToolReturnPart) and part.tool_name == "finish"
            for part in message.parts
        )
        for message in messages
    )


def _evidence(messages: list[ModelMessage]) -> dict[str, Any]:
    for message in messages:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if not isinstance(part, UserPromptPart):
                continue
            text = str(part.content)
            opening = "<profile_research_prior_evidence>\n"
            if opening in text:
                return json.loads(text.split(opening, 1)[1].split("\n</", 1)[0])
    pytest.fail("The agent request has no tagged profile evidence")


def _interact(
    *,
    call_id: str = "question",
    variable: str | None = "learning_goal",
    kind: str = "text",
    prompt: str = "What do you want to learn?",
    options: list[dict[str, str]] | None = None,
) -> DeltaToolCall:
    spec: dict[str, Any] = {"type": kind, "prompt": prompt}
    if variable is not None:
        spec["variable"] = variable
    if options:
        spec["options"] = options
    return DeltaToolCall(
        name="interact", tool_call_id=call_id, json_args=json.dumps(spec)
    )


def _finish() -> dict[int, DeltaToolCall]:
    return {
        0: DeltaToolCall(
            name="finish",
            tool_call_id="finish",
            json_args='{"summary":"Profile question answered"}',
        )
    }


def _runtime(
    script: ModelScript,
) -> tuple[Flask, ProfileResearchRuntime, list[int]]:
    app = Flask("profile-v2-tests")
    app.config.update(
        LLM_MODEL_1_ID="gpt-test",
        DEFAULT_LLM_TEMPERATURE=0.3,
        REDIS_KEY_PREFIX="profile-v2:",
    )
    factories: list[int] = []

    def model_factory(_app: object, session: object, _span: object) -> FunctionModel:
        factories.append(session.block_index)
        return FunctionModel(stream_function=script)

    runtime = ProfileResearchRuntime(
        app,
        store=_ProfileResearchSessionStore(app, cache=InMemoryCacheProvider()),
        model_factory=model_factory,
    )
    return app, runtime, factories


def _start(runtime: ProfileResearchRuntime, document: str) -> dict[str, Any]:
    return runtime.start_session(
        user_bid="v2-learner",
        document=document,
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=12,
        output_language="en-US",
    )


def _run(
    runtime: ProfileResearchRuntime,
    view: dict[str, Any],
    *,
    values: dict[str, list[str]] | None = None,
    index: int = 0,
    request_id: str = "render",
    expected_interaction_id: str | None = None,
) -> list[dict[str, Any]]:
    return list(
        runtime.stream_session(
            user_bid="v2-learner",
            session_id=view["session_id"],
            user_input=values,
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            expected_block_index=index,
            request_id=request_id,
            expected_interaction_id=expected_interaction_id,
        )
    )


def _terminal(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next(event["content"] for event in reversed(events) if event["is_terminal"])


def test_real_tool_pause_survives_store_reload_and_retry_does_not_call_model() -> None:
    calls: list[list[ModelMessage]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls.append(messages)
        answers = _tool_returns(messages)
        if not answers:
            yield {0: _interact()}
        else:
            assert "solve practical problems" in str(answers[0].content)
            yield _finish()

    app, runtime, factories = _runtime(script)
    view = _start(runtime, "?[%{{learning_goal}}...What do you want to learn?]")
    rendered = _run(runtime, view)
    question = next(event for event in rendered if event["event_type"] == "interaction")
    assert "What do you want to learn?" in question["content"]
    assert "?[%{{learning_goal}}" in question["content"]
    assert _terminal(rendered)["awaiting_input"] is True
    stored = runtime.store.load(view["session_id"])
    assert stored.engine_session["pending"][0]["tool_call_id"] == "question"

    resumed = ProfileResearchRuntime(
        app, store=runtime.store, model_factory=runtime._model_factory
    )
    answered = _run(
        resumed,
        view,
        values={"learning_goal": ["solve practical problems"]},
        request_id="answer",
    )
    assert _terminal(answered)["next_block_index"] == 1
    assert _terminal(answered)["awaiting_input"] is False
    assert resumed.store.load(view["session_id"]).variables["learning_goal"] == (
        "solve practical problems"
    )
    before = (len(calls), len(factories))
    assert (
        _run(
            resumed,
            view,
            values={"learning_goal": ["solve practical problems"]},
            request_id="answer",
        )
        == answered
    )
    assert (len(calls), len(factories)) == before


def test_invalid_choice_keeps_the_persisted_tool_pending() -> None:
    calls: list[list[ModelMessage]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls.append(messages)
        yield {
            0: _interact(
                variable="role",
                kind="single",
                prompt="Choose your role",
                options=[{"display": "Teacher", "value": "teacher"}],
            )
        }

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "?[%{{role}} Teacher//teacher]")
    _run(runtime, view)
    original = runtime.store.load(view["session_id"]).engine_session
    events = _run(
        runtime, view, values={"role": ["invented-role"]}, request_id="invalid"
    )

    assert len(calls) == 1
    assert _terminal(events)["advanced"] is False
    assert _terminal(events)["next_block_index"] == 0
    assert _terminal(events)["awaiting_input"] is True
    assert any(event["event_type"] == "interaction" for event in events)
    stored = runtime.store.load(view["session_id"])
    assert stored.engine_session["pending"] == original["pending"]
    assert "role" not in stored.variables


def test_agent_generated_html_preserves_the_profile_element_protocol() -> None:
    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield "Intro text\n"
        yield "<div>Visual card</div>\n"
        yield "Closing text"

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "Present the introduction.\n\n---\n\n?[Continue]")
    events = _run(runtime, view)
    segments: list[dict[str, Any]] = []
    for event in events:
        if event["event_type"] != "content":
            continue
        if (
            segments
            and segments[-1]["generated_block_bid"] == event["generated_block_bid"]
        ):
            segments[-1] = event
        else:
            segments.append(event)

    assert [event["element_type"] for event in segments] == ["text", "html", "text"]
    assert [event["content"].strip() for event in segments] == [
        "Intro text",
        "<div>Visual card</div>",
        "Closing text",
    ]
    assert len({event["generated_block_bid"] for event in segments}) == 3


def test_summary_sees_unassigned_answers_and_only_returns_the_private_draft() -> None:
    question_accepted = False
    summary_messages: list[list[ModelMessage]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal question_accepted
        if any(
            isinstance(message, ModelRequest)
            and any(
                isinstance(part, ToolReturnPart) and part.tool_name == "finish"
                for part in message.parts
            )
            for message in messages
        ):
            yield " "
            return
        if not question_accepted:
            if _tool_returns(messages):
                question_accepted = True
                yield _finish()
            else:
                yield {
                    0: _interact(variable=None, prompt="What is your main challenge?")
                }
        else:
            summary_messages.append(messages)
            assert "short practice sessions" in str(messages)
            yield "Prefers short "
            yield "practice sessions."

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "?[...What is your main challenge?]")
    _run(runtime, view)
    _run(
        runtime,
        view,
        values={"input": ["short practice sessions"]},
        request_id="answer",
    )
    events = _run(runtime, view, index=1, request_id="summary")

    assert [event["event_type"] for event in events] == ["done"]
    assert _terminal(events)["done"] is True
    assert _terminal(events)["profile_draft"] == "Prefers short practice sessions."
    assert _terminal(events)["config_revision"] == 12
    assert runtime.store.load(view["session_id"]).variables == {}
    assert len(summary_messages) == 1


def test_static_question_token_and_retry_identity_cannot_be_reused_for_another_call() -> (
    None
):
    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif _tool_returns(messages):
            yield _finish()
        else:
            yield {0: _interact(call_id="goal", variable="goal", prompt="Your goal?")}

    _app, runtime, factories = _runtime(script)
    view = _start(runtime, "?[%{{goal}}...Your goal?]")
    rendered = _run(runtime, view)
    goal_question = next(
        event for event in rendered if event["event_type"] == "interaction"
    )
    assert goal_question["interaction_id"] == "goal"
    before_answer = runtime.store.load(view["session_id"]).to_cache_payload()
    factory_count = len(factories)
    with pytest.raises(ProfileResearchValidationError, match="interaction"):
        _run(
            runtime,
            view,
            values={"goal": ["practical tasks"]},
            request_id="stale-tab",
            expected_interaction_id="another-question",
        )
    assert runtime.store.load(view["session_id"]).to_cache_payload() == before_answer
    assert len(factories) == factory_count
    first = _run(
        runtime,
        view,
        values={"goal": ["practical tasks"]},
        request_id="goal",
        expected_interaction_id="goal",
    )
    assert _terminal(first)["next_block_index"] == 1
    assert _terminal(first)["awaiting_input"] is False
    stored = runtime.store.load(view["session_id"])
    assert stored.variables["goal"] == "practical tasks"
    unchanged = stored.to_cache_payload()
    factory_count = len(factories)
    with pytest.raises(ProfileResearchValidationError, match="reused"):
        _run(
            runtime,
            view,
            values={"goal": ["practical tasks"]},
            request_id="goal",
            expected_interaction_id="another-question",
        )
    assert runtime.store.load(view["session_id"]).to_cache_payload() == unchanged
    assert len(factories) == factory_count
    assert (
        _run(
            runtime,
            view,
            values={"goal": ["practical tasks"]},
            request_id="goal",
            expected_interaction_id="goal",
        )
        == first
    )
    assert len(factories) == factory_count


def test_multiple_dynamic_questions_in_content_do_not_publish_partial_state() -> None:
    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield {
            0: _interact(call_id="goal", variable="goal", prompt="Your goal?"),
            1: _interact(call_id="pace", variable="pace", prompt="Your pace?"),
        }

    _app, runtime, _factories = _runtime(script)
    view = _start(
        runtime,
        "Introduce the goal and pace questions.\n\n---\n\n?[Continue]",
    )
    original = runtime.store.load(view["session_id"]).to_cache_payload()
    with pytest.raises(ProfileResearchError, match="failed to execute"):
        _run(runtime, view)
    assert runtime.store.load(view["session_id"]).to_cache_payload() == original


def test_provider_failure_after_answer_does_not_persist_partial_agent_state() -> None:
    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _tool_returns(messages):
            message = "model unavailable"
            raise RuntimeError(message)
        yield {0: _interact()}

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "?[%{{learning_goal}}...What do you want to learn?]")
    _run(runtime, view)
    original = runtime.store.load(view["session_id"]).to_cache_payload()
    with pytest.raises(ProfileResearchError, match="failed to execute"):
        _run(
            runtime,
            view,
            values={"learning_goal": ["practice"]},
            request_id="failed-answer",
        )
    assert runtime.store.load(view["session_id"]).to_cache_payload() == original


def test_schema_one_pending_session_bootstraps_the_agent_before_accepting_answer() -> (
    None
):
    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _tool_returns(messages):
            yield _finish()
        else:
            yield {0: _interact()}

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "?[%{{learning_goal}}...What do you want to learn?]")
    legacy = runtime.store.load(view["session_id"]).to_cache_payload()
    legacy.pop("engine_session", None)
    legacy.pop("engine_block_index", None)
    legacy["schema_version"] = 1
    legacy["awaiting_input"] = True
    legacy["context"] = [{"role": "assistant", "content": "What do you want to learn?"}]
    runtime.store._cache.setex(
        runtime.store._key(view["session_id"]),
        PROFILE_RESEARCH_SESSION_TTL_SECONDS,
        json.dumps(legacy),
    )

    events = _run(
        runtime,
        view,
        values={"learning_goal": ["practice"]},
        request_id="legacy-answer",
    )

    assert _terminal(events)["next_block_index"] == 1
    assert _terminal(events)["awaiting_input"] is False
    assert (
        runtime.store.load(view["session_id"]).variables["learning_goal"] == "practice"
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_authored_prompts_remain_distinct_from_learner_facts_in_summary(
    legacy: bool,
) -> None:
    authored_prompt = (
        "Use a fictional pilot as an example; this is not the learner's job."
    )
    summary_evidence: list[dict[str, Any]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif factories[-1] == 0:
            yield "This is an example."
        elif factories[-1] == 1:
            if _tool_returns(messages):
                yield _finish()
            else:
                yield {
                    0: _interact(
                        variable=None,
                        kind="single",
                        prompt="",
                        options=[{"display": "Continue", "value": "Continue"}],
                    )
                }
        else:
            summary_evidence.append(_evidence(messages))
            yield "No personal facts supplied."

    _app, runtime, factories = _runtime(script)
    view = _start(runtime, f"{authored_prompt}\n\n---\n\n?[Continue]")
    _run(runtime, view)
    _run(runtime, view, index=1, request_id="render-continue")
    _run(
        runtime,
        view,
        index=1,
        values={"choice": ["Continue"]},
        request_id="continue",
    )
    if legacy:
        payload = runtime.store.load(view["session_id"]).to_cache_payload()
        payload["schema_version"] = 1
        payload.pop("engine_session", None)
        payload.pop("engine_block_index", None)
        runtime.store._cache.setex(
            runtime.store._key(view["session_id"]),
            PROFILE_RESEARCH_SESSION_TTL_SECONDS,
            json.dumps(payload),
        )
    _run(runtime, view, index=2, request_id="summary")

    conversation = summary_evidence[0]["conversation"]
    assert {"role": "authored_prompt", "content": authored_prompt} in conversation
    assert not any(
        message["role"] == "user" and "pilot" in message["content"]
        for message in conversation
    )


def test_unassigned_answer_to_an_authored_question_reaches_summary() -> None:
    summary_evidence: list[dict[str, Any]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif factories[-1] == 2:
            summary_evidence.append(_evidence(messages))
            yield "Prefers ten-minute sessions."
        elif _tool_returns(messages):
            yield _finish()
        elif factories[-1] == 0:
            yield {0: _interact(variable=None, prompt="How long should a session be?")}
        else:
            yield {
                0: _interact(
                    variable=None,
                    kind="single",
                    prompt="",
                    options=[{"display": "Continue", "value": "Continue"}],
                )
            }

    _app, runtime, factories = _runtime(script)
    view = _start(runtime, "?[...How long should a session be?]\n\n---\n\n?[Continue]")
    _run(runtime, view)
    _run(runtime, view, values={"input": ["Ten minutes"]}, request_id="answer")
    _run(runtime, view, index=1, request_id="render-continue")
    _run(
        runtime,
        view,
        index=1,
        values={"choice": ["Continue"]},
        request_id="continue",
    )
    _run(runtime, view, index=2, request_id="summary")

    assert {"role": "user", "content": "Ten minutes"} in summary_evidence[0][
        "conversation"
    ]
    assert summary_evidence[0]["accepted_answers"] == {}


def test_production_model_routes_native_tools_through_the_free_shared_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unused(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield "unused"

    app, runtime, _factories = _runtime(unused)
    view = _start(runtime, "?[%{{learning_goal}}...What do you want to learn?]")
    session = runtime.store.load(view["session_id"])
    calls: list[dict[str, Any]] = []

    def chat_llm(**kwargs: object) -> object:
        calls.append(kwargs)
        yield SimpleNamespace(
            result="",
            tool_call_deltas=[
                {
                    "index": 0,
                    "name": "interact",
                    "id": "native-question",
                    "arguments": '{"type":"text","prompt":"Your goal?"}',
                }
            ],
            finish_reason="tool_calls",
            usage=None,
        )

    monkeypatch.setattr("flaskr.service.learn.agent.gateway_model.chat_llm", chat_llm)
    span = object()
    model = create_profile_research_model(app, session, span)
    response = asyncio.run(
        model.request(
            [ModelRequest(parts=[UserPromptPart(content="Ask the profile question.")])],
            {"temperature": session.temperature},
            ModelRequestParameters(
                function_tools=[
                    ToolDefinition(
                        name="interact",
                        parameters_json_schema={"type": "object", "properties": {}},
                    )
                ]
            ),
        )
    )

    call = calls[0]
    assert call["app"] is app
    assert call["user_id"] == "v2-learner"
    assert call["model"] == session.model
    assert call["span"] is span
    assert call["generation_name"] == "profile_research_markdownflow"
    assert call["emit_tool_calls"] is True
    assert call["tools"][0]["function"]["name"] == "interact"
    assert call["usage_scene"] == BILL_USAGE_SCENE_DEBUG
    assert call["billable"] == 0
    assert call["usage_context"].billable == 0
    assert call["usage_context"].usage_scene == BILL_USAGE_SCENE_DEBUG
    assert call["temperature"] == session.temperature
    native_call = next(
        part for part in response.parts if isinstance(part, ToolCallPart)
    )
    assert native_call.tool_call_id == "native-question"
    assert native_call.tool_name == "interact"


def test_unassigned_answer_after_a_named_question_survives_into_summary() -> None:
    summary_evidence: list[dict[str, Any]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif factories[-1] == 2:
            summary_evidence.append(_evidence(messages))
            yield "Learns practical skills through short sessions."
        elif _tool_returns(messages):
            yield _finish()
        elif factories[-1] == 0:
            yield {0: _interact(variable="learning_goal", prompt="Your goal?")}
        else:
            yield {0: _interact(variable=None, prompt="What makes learning difficult?")}

    _app, runtime, factories = _runtime(script)
    view = _start(
        runtime,
        "?[%{{learning_goal}}...Your goal?]\n\n---\n\n?[...What makes learning difficult?]",
    )
    _run(runtime, view)
    _run(
        runtime, view, values={"learning_goal": ["Practical skills"]}, request_id="goal"
    )
    _run(runtime, view, index=1, request_id="render-challenge")
    _run(
        runtime,
        view,
        index=1,
        values={"input": ["I only have ten minutes at a time"]},
        request_id="challenge",
    )
    _run(runtime, view, index=2, request_id="summary")

    assert summary_evidence[0]["accepted_answers"] == {
        "learning_goal": "Practical skills"
    }
    assert {
        "role": "user",
        "content": "I only have ten minutes at a time",
    } in summary_evidence[0]["conversation"]


def test_assistant_import_keeps_an_unassigned_answer_while_the_next_question_is_pending() -> (
    None
):
    summary_evidence: list[dict[str, Any]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif factories[-1] == 2:
            summary_evidence.append(_evidence(messages))
            yield "Prefers examples from the classroom."
        elif _tool_returns(messages):
            yield _finish()
        elif factories[-1] == 0:
            yield {
                0: _interact(
                    call_id="background", variable=None, prompt="Your background?"
                )
            }
        else:
            yield {
                0: _interact(
                    call_id="challenge", variable=None, prompt="Your challenge?"
                )
            }

    app, runtime, factories = _runtime(script)
    view = runtime.start_session(
        user_bid="v2-learner",
        document="?[...Your background?]\n\n---\n\n?[...Your challenge?]",
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=12,
        output_language="en-US",
        assistant_prompt="Answer the learner's background and challenge questionnaire.",
    )
    _run(runtime, view)
    answered = _run(
        runtime,
        view,
        values={"input": ["I teach in a classroom"]},
        request_id="background",
    )
    assert _terminal(answered)["next_block_index"] == 1
    pending = _run(runtime, view, index=1, request_id="render-challenge")
    assert _terminal(pending)["awaiting_input"] is True
    runtime._provider_factory = lambda *_args: SimpleNamespace(
        complete=lambda **_kwargs: '{"answers":"","nickname":""}'
    )
    with app.app_context():
        events = list(
            runtime.stream_assistant_answers(
                user_bid="v2-learner",
                session_id=view["session_id"],
                raw_text="No supplemental personal details",
                expected_block_index=1,
                request_id="delegate",
            )
        )

    assert _terminal(events)["done"] is True
    assert _terminal(events)["profile_draft"] == "Prefers examples from the classroom."
    assert summary_evidence[0]["accepted_interaction_answers"] == [
        "I teach in a classroom"
    ]


def test_sequential_authored_questions_keep_distinct_content_and_feedback_bids() -> (
    None
):
    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        answers = _tool_returns(messages)
        if _finished(messages):
            yield " "
        elif not answers and factories[-1] == 0:
            yield "Let's understand how you learn.\n"
            yield {0: _interact(call_id="goal", variable="goal", prompt="Your goal?")}
        elif not answers:
            yield "Let's understand your learning pace.\n"
            yield {0: _interact(call_id="pace", variable="pace", prompt="Your pace?")}
        elif factories[-1] == 0:
            yield "Your goal is clear.\n"
            yield _finish()
        else:
            yield "Your pace is clear.\n"
            yield _finish()

    _app, runtime, factories = _runtime(script)
    view = _start(
        runtime,
        "?[%{{goal}}...Your goal?]\n\n---\n\n?[%{{pace}}...Your pace?]",
    )
    rendered = _run(runtime, view)
    intro = next(event for event in rendered if event["event_type"] == "content")
    goal = next(event for event in rendered if event["event_type"] == "interaction")
    assert intro["generated_block_bid"] != goal["generated_block_bid"]
    assert goal["interaction_id"] == "goal"

    first = _run(
        runtime,
        view,
        values={"goal": ["Practical skills"]},
        request_id="goal",
        expected_interaction_id="goal",
    )
    goal_feedback = next(event for event in first if event["event_type"] == "content")
    assert _terminal(first)["next_block_index"] == 1
    next_question = _run(runtime, view, index=1, request_id="render-pace")
    pace = next(
        event for event in next_question if event["event_type"] == "interaction"
    )
    assert pace["interaction_id"] == "pace"
    assert pace["generated_block_bid"] != goal["generated_block_bid"]
    assert goal_feedback["generated_block_bid"] != pace["generated_block_bid"]

    second = _run(
        runtime,
        view,
        values={"pace": ["Slow"]},
        index=1,
        request_id="pace",
        expected_interaction_id="pace",
    )
    pace_feedback = next(event for event in second if event["event_type"] == "content")
    assert pace_feedback["generated_block_bid"] != goal_feedback["generated_block_bid"]
    assert _terminal(second)["next_block_index"] == 2


@pytest.mark.usefixtures("app")
@pytest.mark.parametrize(
    ("prompt", "expected"),
    [("", "?[继续//continue]"), ("我准备好了", "?[我准备好了//continue]")],
)
def test_confirm_uses_the_localized_default_or_the_models_short_label(
    prompt: str, expected: str
) -> None:
    from flaskr.i18n import clear_language, set_language

    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield "请确认上面的学习安排。\n"
        yield {0: _interact(variable=None, kind="confirm", prompt=prompt)}

    _app, runtime, _factories = _runtime(script)
    view = runtime.start_session(
        user_bid="v2-learner",
        document="?[继续]",
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=12,
        output_language="zh-CN",
    )
    set_language("zh-CN")
    try:
        events = _run(runtime, view)
    finally:
        clear_language()

    interaction = next(
        event for event in events if event["event_type"] == "interaction"
    )
    assert interaction["content"] == expected


def test_manual_nickname_alone_does_not_become_profile_evidence_on_assistant_import() -> (
    None
):
    summary_evidence: list[dict[str, Any]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif factories[-1] == 1:
            summary_evidence.append(_evidence(messages))
            yield "The model invented a profession without personal evidence."
        elif _tool_returns(messages):
            yield _finish()
        else:
            yield {
                0: _interact(
                    variable="sys_user_nickname", prompt="How should we address you?"
                )
            }

    app, runtime, factories = _runtime(script)
    view = runtime.start_session(
        user_bid="v2-learner",
        document="?[%{{sys_user_nickname}}...How should we address you?]",
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=12,
        output_language="en-US",
        assistant_prompt="Share what you know about this learner.",
    )
    _run(runtime, view)
    _run(
        runtime,
        view,
        values={"sys_user_nickname": ["River"]},
        request_id="nickname",
    )
    runtime._provider_factory = lambda *_args: SimpleNamespace(
        complete=lambda **_kwargs: '{"answers":"","nickname":""}'
    )
    with app.app_context():
        events = list(
            runtime.stream_assistant_answers(
                user_bid="v2-learner",
                session_id=view["session_id"],
                raw_text="No additional personal information",
                expected_block_index=1,
                request_id="delegate",
            )
        )

    summary = _terminal(events)
    assert summary["done"] is True
    assert summary["nickname"] == "River"
    assert summary["profile_draft"] == ""
    assert summary_evidence[0]["accepted_interaction_answers"] == []
    assert not any(
        message["role"] == "user" and message["content"] == "River"
        for message in summary_evidence[0]["conversation"]
    )
    stored = runtime.store.load(view["session_id"])
    assert stored.variables["sys_user_nickname"] == "River"
    assert stored.profile_draft == ""
