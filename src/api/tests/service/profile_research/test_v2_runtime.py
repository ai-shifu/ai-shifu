"""Exercise full-document native profile sessions through the public runtime."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from flask import Flask
from flaskr.common.cache_provider import InMemoryCacheProvider
from flaskr.service.profile_research.runtime import (
    PROFILE_ONBOARDING_PURPOSE,
    ProfileResearchRuntime,
    ProfileResearchSessionNotFound,
    _ProfileResearchSessionStore,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

StreamChunks = AsyncIterator[str | dict[int, DeltaToolCall]]
ModelScript = Callable[[list[ModelMessage], AgentInfo], StreamChunks]


class _SummaryProvider:
    def __init__(self, output: str = "Private learner profile.") -> None:
        self.output = output
        self.messages: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]], **_kwargs: object) -> str:
        self.messages.append(messages)
        return self.output


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


def _interact(
    *,
    call_id: str = "question",
    question: str | None = "learning_goal",
    kind: str = "text",
    prompt: str = "What do you want to learn?",
    options: list[dict[str, str]] | None = None,
) -> DeltaToolCall:
    spec: dict[str, Any] = {"type": kind, "prompt": prompt}
    if question is not None:
        spec["question"] = question
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
            json_args='{"summary":"Questionnaire completed"}',
        )
    }


def _runtime(script: ModelScript) -> tuple[Flask, ProfileResearchRuntime, list[int]]:
    app = Flask("profile-native-tests")
    app.config.update(
        LLM_MODEL_1_ID="gpt-test",
        DEFAULT_LLM_TEMPERATURE=0.3,
        REDIS_KEY_PREFIX="native:",
    )
    factories: list[int] = []

    def model_factory(_app: object, session: object, _span: object) -> FunctionModel:
        factories.append(session.turn_index)
        return FunctionModel(stream_function=script)

    runtime = ProfileResearchRuntime(
        app,
        store=_ProfileResearchSessionStore(app, cache=InMemoryCacheProvider()),
        model_factory=model_factory,
        provider_factory=lambda *_args: _SummaryProvider(),
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
    index: int | None = None,
    request_id: str = "render",
    expected_interaction_id: str | None = None,
) -> list[dict[str, Any]]:
    if index is None:
        index = runtime.store.load(view["session_id"]).turn_index
    return list(
        runtime.stream_session(
            user_bid="v2-learner",
            session_id=view["session_id"],
            user_input=values,
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            expected_turn_index=index,
            request_id=request_id,
            expected_interaction_id=expected_interaction_id,
        )
    )


def _terminal(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next(
        event["content"] for event in reversed(events) if event.get("is_terminal")
    )


def _evidence(messages: list[dict[str, str]]) -> dict[str, Any]:
    return json.loads(messages[-1]["content"])


def test_full_script_and_native_session_survive_between_questions() -> None:
    calls: list[list[ModelMessage]] = []
    document = "?[%{{goal}}...Goal?]\n?[%{{pace}}...Pace?]"

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls.append(messages)
        answers = _tool_returns(messages)
        if _finished(messages):
            yield " "
        elif not answers:
            yield "Welcome.\n"
            yield {0: _interact(call_id="goal", question="goal", prompt="Your goal?")}
        elif len(answers) == 1:
            assert "Practical skills" in str(answers[0].content)
            yield {0: _interact(call_id="pace", question="pace", prompt="Your pace?")}
        else:
            assert "Slow" in str(answers[-1].content)
            yield _finish()

    app, runtime, _factories = _runtime(script)
    view = _start(runtime, document)
    first = _run(runtime, view)
    assert _terminal(first)["next_turn_index"] == 1
    saved = runtime.store.load(view["session_id"])
    engine_id = saved.engine_session["id"]
    assert saved.document == document
    assert saved.engine_session["script"]["script"] == document
    resumed = ProfileResearchRuntime(
        app,
        store=runtime.store,
        model_factory=runtime._model_factory,
        provider_factory=runtime._provider_factory,
    )
    second = _run(
        resumed,
        view,
        index=1,
        values={"goal": ["Practical skills"]},
        request_id="goal",
        expected_interaction_id="goal",
    )
    assert _terminal(second)["input_accepted"] is True
    assert _terminal(second)["pending_interaction_ids"] == ["pace"]
    assert resumed.store.load(view["session_id"]).engine_session["id"] == engine_id
    final = _run(
        resumed,
        view,
        index=2,
        values={"pace": ["Slow"]},
        request_id="pace",
        expected_interaction_id="pace",
    )
    assert _terminal(final)["done"] is True
    assert _terminal(final)["profile_draft"] == "Private learner profile."
    assert any(
        saved.document in part.content
        for message in calls[0]
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    )
    assert resumed.store.load(view["session_id"]).engine_session["id"] == engine_id


def test_private_summary_has_only_accepted_personal_answers_and_never_streams_text() -> (
    None
):
    summary = _SummaryProvider("Prefers practical tasks.")

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif _tool_returns(messages):
            yield _finish()
        else:
            yield {0: _interact(question=None, prompt="Your learning needs?")}

    _app, runtime, _factories = _runtime(script)
    runtime._provider_factory = lambda *_args: summary
    view = _start(runtime, "Ask about learning needs, then finish.")
    _run(runtime, view)
    final = _run(
        runtime,
        view,
        index=1,
        values={"input": ["Practical tasks"]},
        request_id="answer",
        expected_interaction_id="question",
    )
    assert not any(
        event["event_type"] == "content" and str(event["content"]).strip()
        for event in final
    )
    assert summary.output not in str(
        [event for event in final if not event.get("is_terminal")]
    )
    assert final[0]["content"] == {"phase": "summary"}
    assert _terminal(final)["profile_draft"] == summary.output
    assert "Practical tasks" in str(_evidence(summary.messages[0]))
    assert runtime.store.load(view["session_id"]).engine_session["script"][
        "script"
    ] == view.get("document", "Ask about learning needs, then finish.")


def test_private_summary_keeps_an_unnamed_placeholder_question_as_context() -> None:
    question = "How many years have you taught?"
    summary = _SummaryProvider("Has ten years of teaching experience.")

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif answers := _tool_returns(messages):
            assert answers[-1].content == "Learner wrote: 10"
            yield _finish()
        else:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="teaching-years",
                    json_args=json.dumps(
                        {"type": "text", "prompt": "", "placeholder": question}
                    ),
                )
            }

    _app, runtime, _factories = _runtime(script)
    runtime._provider_factory = lambda *_args: summary
    view = _start(runtime, "Ask about teaching experience, then finish.")
    first = _run(runtime, view)
    assert any(
        event["event_type"] == "interaction" and question in event["content"]
        for event in first
    )
    final = _run(
        runtime,
        view,
        values={"input": ["10"]},
        request_id="teaching-years-answer",
        expected_interaction_id="teaching-years",
    )
    assert _terminal(final)["input_accepted"] is True
    assert _terminal(final)["profile_draft"] == summary.output
    assert _evidence(summary.messages[0]) == {
        "accepted_answers": [
            {
                "prompt": "",
                "question": None,
                "answer": "Learner wrote: 10",
                "question_context": {
                    "is_learner_fact": False,
                    "placeholder": question,
                },
            }
        ],
        "supplemental_answers": [],
    }
    instructions = "\n".join(
        message["content"]
        for message in summary.messages[0]
        if message["role"] == "system"
    )
    assert "input placeholders" in instructions
    assert "not learner information" in instructions
    assert runtime.store.load(view["session_id"]).memory == {}
    assert final[0]["content"] == {"phase": "summary"}
    assert not any(
        event["event_type"] == "content" and str(event["content"]).strip()
        for event in final
    )
    assert summary.output not in str(
        [event for event in final if not event.get("is_terminal")]
    )


@pytest.mark.parametrize("schema", [1, 2])
def test_old_questionnaire_cache_expires_and_a_new_session_can_replace_it(
    schema: int,
) -> None:
    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield {0: _interact()}

    _app, runtime, factories = _runtime(script)
    first = _start(runtime, "Ask what the learner wants to learn.")
    payload = runtime.store.load(first["session_id"]).to_cache_payload()
    payload["schema_version"] = schema
    runtime.store._cache.setex(
        runtime.store._key(first["session_id"]), 1800, json.dumps(payload)
    )
    with pytest.raises(ProfileResearchSessionNotFound):
        _run(runtime, first)
    assert factories == []
    replacement = _start(runtime, "Ask what the learner wants to learn.")
    assert replacement["session_id"] != first["session_id"]
    assert (
        runtime.store.active_session_id(
            user_bid="v2-learner", purpose=PROFILE_ONBOARDING_PURPOSE
        )
        == replacement["session_id"]
    )


def test_native_batch_answers_persist_independently_and_exact_replay_keeps_the_same_turn() -> (
    None
):
    calls: list[list[ModelMessage]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls.append(messages)
        if _finished(messages):
            yield " "
        elif answers := _tool_returns(messages):
            assert len(answers) == 2
            assert "Practical skills" in str(answers[0].content)
            assert "Slow" in str(answers[1].content)
            yield _finish()
        else:
            yield {
                0: _interact(call_id="goal", question="goal", prompt="Your goal?"),
                1: _interact(call_id="pace", question="pace", prompt="Your pace?"),
            }

    app, runtime, factories = _runtime(script)
    view = _start(runtime, "?[%{{goal}}...Goal?]\n?[%{{pace}}...Pace?]")
    opening = _run(runtime, view)
    assert _terminal(opening)["pending_interaction_ids"] == ["goal", "pace"]
    assert [
        event["interaction_id"]
        for event in opening
        if event["event_type"] == "interaction"
    ] == ["goal"]
    engine_turn = runtime.store.load(view["session_id"]).engine_session["turn"]
    first = _run(
        runtime,
        view,
        index=1,
        values={"goal": ["Practical skills"]},
        request_id="goal",
        expected_interaction_id="goal",
    )
    assert len(calls) == 1
    assert _terminal(first)["next_turn_index"] == 2
    assert _terminal(first)["pending_interaction_ids"] == ["pace"]
    saved = runtime.store.load(view["session_id"])
    assert saved.engine_session["turn"] == engine_turn
    assert "goal" in saved.engine_session["answers"]
    resumed = ProfileResearchRuntime(
        app,
        store=runtime.store,
        model_factory=runtime._model_factory,
        provider_factory=runtime._provider_factory,
    )
    assert (
        _run(
            resumed,
            view,
            index=1,
            values={"goal": ["Practical skills"]},
            request_id="goal",
            expected_interaction_id="goal",
        )
        == first
    )
    assert len(calls) == 1
    before = resumed.store.load(view["session_id"]).to_cache_payload()
    from flaskr.service.profile_research.runtime import ProfileResearchValidationError

    with pytest.raises(ProfileResearchValidationError):
        _run(
            resumed,
            view,
            index=2,
            values={"pace": ["Slow"]},
            request_id="stale",
            expected_interaction_id="goal",
        )
    assert resumed.store.load(view["session_id"]).to_cache_payload() == before
    completed = _run(
        resumed,
        view,
        index=2,
        values={"pace": ["Slow"]},
        request_id="pace",
        expected_interaction_id="pace",
    )
    count = (len(calls), len(factories))
    assert _terminal(completed)["done"] is True
    assert (
        _run(
            resumed,
            view,
            index=2,
            values={"pace": ["Slow"]},
            request_id="pace",
            expected_interaction_id="pace",
        )
        == completed
    )
    assert (len(calls), len(factories)) == count


def test_model_memory_notes_do_not_become_private_profile_facts() -> None:
    summary = _SummaryProvider("Learns practical skills.")

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        remembered = any(
            isinstance(message, ModelRequest)
            and any(
                isinstance(part, ToolReturnPart) and part.tool_name == "remember"
                for part in message.parts
            )
            for message in messages
        )
        if _finished(messages):
            yield " "
        elif _tool_returns(messages):
            yield _finish()
        elif remembered:
            yield {0: _interact(question="goal", prompt="Your goal?")}
        else:
            yield {
                0: DeltaToolCall(
                    name="remember",
                    tool_call_id="invented",
                    json_args=json.dumps(
                        {
                            "key": "scratch",
                            "value": "Invented profession",
                            "scope": "session",
                        }
                    ),
                )
            }

    _app, runtime, _factories = _runtime(script)
    runtime._provider_factory = lambda *_args: summary
    view = _start(runtime, "?[%{{goal}}...Goal?]\n?[%{{scratch}}...Scratch?]")
    _run(runtime, view)
    final = _run(
        runtime,
        view,
        values={"goal": ["Practical skills"]},
        request_id="answer",
        expected_interaction_id="question",
    )
    assert _terminal(final)["done"] is True
    assert (
        runtime.store.load(view["session_id"]).memory["scratch"]
        == "Invented profession"
    )
    facts = _evidence(summary.messages[0])
    assert "Practical skills" in str(facts)
    assert "Invented profession" not in str(facts)


def test_private_summary_failure_keeps_the_pending_native_answer_retryable() -> None:
    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif _tool_returns(messages):
            yield _finish()
        else:
            yield {0: _interact()}

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "?[%{{learning_goal}}...What do you want to learn?]")
    _run(runtime, view)
    original = runtime.store.load(view["session_id"]).to_cache_payload()

    class UnavailableSummary:
        def complete(self, **_kwargs: object) -> str:
            message = "private summary unavailable"
            raise RuntimeError(message)

    runtime._provider_factory = lambda *_args: UnavailableSummary()
    with pytest.raises(RuntimeError, match="private summary unavailable"):
        _run(
            runtime,
            view,
            values={"learning_goal": ["Practical skills"]},
            request_id="answer",
            expected_interaction_id="question",
        )
    assert runtime.store.load(view["session_id"]).to_cache_payload() == original
    runtime._provider_factory = lambda *_args: _SummaryProvider()
    completed = _run(
        runtime,
        view,
        values={"learning_goal": ["Practical skills"]},
        request_id="answer",
        expected_interaction_id="question",
    )
    assert _terminal(completed)["done"] is True
