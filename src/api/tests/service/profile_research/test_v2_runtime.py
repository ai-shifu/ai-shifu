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
    ProfileResearchValidationError,
    _ProfileResearchSessionStore,
)
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
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
    rewind: bool = False,
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
            rewind=rewind,
        )
    )


@pytest.mark.parametrize(
    ("question", "display_question"),
    [
        ("Your goal?", "Your goal?"),
        ("Compare *literal* and <tag>?", r"Compare \*literal\* and \<tag\>?"),
    ],
)
def test_pending_reload_restores_question_before_the_same_controls(
    question: str, display_question: str
) -> None:
    calls = 0

    async def script(_messages: list[ModelMessage], info: AgentInfo) -> StreamChunks:
        nonlocal calls
        calls += 1
        assert "ask the question in visible Markdown prose" in (info.instructions or "")
        yield display_question
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="goal",
                json_args=json.dumps({"type": "text", "question": question}),
            )
        }

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "Ask about learning goals.")
    opening = _run(runtime, view)
    (interaction,) = [
        event for event in opening if event["event_type"] == "interaction"
    ]
    assert interaction["interaction_id"] == "goal"
    assert interaction["content"].startswith("?[")
    assert any(
        event["event_type"] == "content" and event["content"] == display_question
        for event in opening
    )
    assert _run(runtime, view, index=0) == opening
    assert calls == 1
    reloaded = _run(runtime, view, request_id="reload")
    (pending,) = [event for event in reloaded if event["event_type"] == "interaction"]
    (restored_question,) = [
        event
        for event in reloaded
        if event["event_type"] == "content" and event["is_final"]
    ]
    assert restored_question["content"] == display_question
    assert reloaded.index(restored_question) < reloaded.index(pending)
    assert pending["interaction_id"] == "goal"
    assert pending["content"] == interaction["content"]
    assert _run(runtime, view, index=1, request_id="reload") == reloaded
    assert calls == 1


def _terminal(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next(
        event["content"] for event in reversed(events) if event.get("is_terminal")
    )


def _evidence(messages: list[dict[str, str]]) -> dict[str, Any]:
    return json.loads(messages[-1]["content"])


def test_full_script_and_native_session_survive_between_questions() -> None:
    calls: list[list[ModelMessage]] = []
    document = "Collect %{{goal}} and %{{pace}} in two questions, then finish."

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls.append(messages)
        answers = _tool_returns(messages)
        if _finished(messages):
            yield " "
        elif not answers:
            yield "Welcome.\n"
            yield {0: _interact(call_id="goal", variable="goal", prompt="Your goal?")}
        elif len(answers) == 1:
            assert "Practical skills" in str(answers[0].content)
            yield {0: _interact(call_id="pace", variable="pace", prompt="Your pace?")}
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
    assert saved.document in str(calls[0])
    assert resumed.store.load(view["session_id"]).engine_session["id"] == engine_id


def test_two_browser_sessions_keep_answers_revisions_and_replays_independent() -> None:
    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif _tool_returns(messages):
            yield _finish()
        else:
            yield {0: _interact()}

    _app, runtime, _factories = _runtime(script)
    first = _start(runtime, "Collect %{{learning_goal}} and finish.")
    second = _start(runtime, "Collect %{{learning_goal}} and finish.")
    _run(runtime, first)
    _run(runtime, second)
    before_second = runtime.store.load(second["session_id"]).to_cache_payload()
    first_result = _run(
        runtime,
        first,
        values={"learning_goal": ["First browser answer"]},
        request_id="answer",
        expected_interaction_id="question",
    )
    assert _terminal(first_result)["done"] is True
    assert runtime.store.load(second["session_id"]).to_cache_payload() == before_second
    second_result = _run(
        runtime,
        second,
        values={"learning_goal": ["Second browser answer"]},
        request_id="answer",
        expected_interaction_id="question",
    )
    assert _terminal(second_result)["done"] is True
    assert runtime.store.load(first["session_id"]).variables == {
        "learning_goal": "First browser answer"
    }
    assert runtime.store.load(second["session_id"]).variables == {
        "learning_goal": "Second browser answer"
    }
    for view, answer, expected in (
        (first, "First browser answer", first_result),
        (second, "Second browser answer", second_result),
    ):
        assert (
            _run(
                runtime,
                view,
                values={"learning_goal": [answer]},
                index=1,
                request_id="answer",
                expected_interaction_id="question",
            )
            == expected
        )


def test_rewind_replaces_a_completed_answer_branch_and_replays_the_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        answers = _tool_returns(messages)
        if _finished(messages):
            yield " "
        elif not answers:
            yield {0: _interact(call_id="goal", variable="goal")}
        elif len(answers) == 1:
            if "Revised goal" in str(answers[0].content):
                yield "New guidance.\n"
            yield {0: _interact(call_id="pace", variable="pace")}
        else:
            yield _finish()

    _app, runtime, factories = _runtime(script)
    view = _start(runtime, "Collect %{{goal}} and %{{pace}}, then finish.")
    _run(runtime, view)
    _run(
        runtime,
        view,
        values={"goal": ["Original goal"]},
        request_id="goal",
        expected_interaction_id="goal",
    )
    completed = _run(
        runtime,
        view,
        values={"pace": ["Old pace"]},
        request_id="pace",
        expected_interaction_id="pace",
    )
    assert _terminal(completed)["rewindable_interaction_ids"] == ["goal", "pace"]
    assert _terminal(completed)["done"] is True

    save = runtime.store.save

    def save_then_fail(session: object) -> None:
        save(session)
        message = "write acknowledgement failed after session write"
        raise RuntimeError(message)

    monkeypatch.setattr(runtime.store, "save", save_then_fail)
    request = {
        "values": {"goal": ["Revised goal"]},
        "index": 3,
        "request_id": "revise-goal",
        "expected_interaction_id": "goal",
        "rewind": True,
    }
    updated = _run(runtime, view, **request)
    assert updated[0]["type"] == "rewind"
    assert updated[0]["content"] == {"interaction_id": "goal"}
    assert any("New guidance" in event["content"] for event in updated[1:-1])
    terminal = _terminal(updated)
    assert terminal["next_turn_index"] == 4
    assert terminal["input_accepted"] is True
    assert terminal["pending_interaction_ids"] == ["pace"]
    assert terminal["rewindable_interaction_ids"] == ["goal"]
    assert terminal["profile_draft"] is None

    saved = runtime.store.load(view["session_id"])
    assert saved.variables == {"goal": "Revised goal"}
    assert saved.profile_draft == ""
    assert "Old pace" not in str(saved.engine_session["messages"])
    assert "Original goal" not in str(saved.engine_session["messages"])
    calls = len(factories)
    assert _run(runtime, view, **request) == updated
    with pytest.raises(ProfileResearchValidationError, match="reused"):
        _run(runtime, view, **{**request, "rewind": False})
    with pytest.raises(ProfileResearchValidationError, match="request revision"):
        _run(runtime, view, **{**request, "request_id": "stale-edit"})
    assert len(factories) == calls


def test_rejected_rewind_preserves_the_finished_profile_and_request_revision() -> None:
    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif _tool_returns(messages):
            yield _finish()
        else:
            yield {0: _interact()}

    _app, runtime, factories = _runtime(script)
    view = _start(runtime, "Collect %{{learning_goal}} and finish.")
    _run(runtime, view)
    _run(
        runtime,
        view,
        values={"learning_goal": ["Original answer"]},
        request_id="answer",
        expected_interaction_id="question",
    )
    previous = runtime.store.load(view["session_id"])
    request = {
        "values": {"wrong_variable": ["Rejected answer"]},
        "index": 2,
        "request_id": "rejected-edit",
        "expected_interaction_id": "question",
        "rewind": True,
    }
    rejected = _run(runtime, view, **request)
    assert [event["type"] for event in rejected] == ["done"]
    terminal = _terminal(rejected)
    assert terminal["input_accepted"] is False
    assert terminal["next_turn_index"] == 2
    assert terminal["done"] is True
    assert terminal["profile_draft"] == previous.profile_draft
    saved = runtime.store.load(view["session_id"])
    assert saved.engine_session == previous.engine_session
    assert saved.variables == previous.variables
    assert saved.answer_checkpoints == previous.answer_checkpoints
    calls = len(factories)
    assert _run(runtime, view, **request) == rejected
    assert len(factories) == calls


def test_rewind_summary_failure_keeps_the_previous_draft_and_evidence() -> None:
    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _finished(messages):
            yield " "
        elif _tool_returns(messages):
            yield _finish()
        else:
            yield {0: _interact()}

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "Collect %{{learning_goal}} and finish.")
    _run(runtime, view)
    _run(
        runtime,
        view,
        values={"learning_goal": ["Original answer"]},
        request_id="answer",
        expected_interaction_id="question",
    )
    previous = runtime.store.load(view["session_id"]).to_cache_payload()
    request = {
        "values": {"learning_goal": ["Revised answer"]},
        "index": 2,
        "request_id": "revise-answer",
        "expected_interaction_id": "question",
        "rewind": True,
    }

    class UnavailableSummary:
        def complete(self, **_kwargs: object) -> str:
            message = "private summary unavailable"
            raise RuntimeError(message)

    runtime._provider_factory = lambda *_args: UnavailableSummary()
    with pytest.raises(RuntimeError, match="private summary unavailable"):
        _run(runtime, view, **request)
    assert runtime.store.load(view["session_id"]).to_cache_payload() == previous

    summary = _SummaryProvider("Revised private draft.")
    runtime._provider_factory = lambda *_args: summary
    updated = _run(runtime, view, **request)
    assert [event["type"] for event in updated] == ["phase", "rewind", "done"]
    assert _terminal(updated)["profile_draft"] == "Revised private draft."
    assert "Revised answer" in str(_evidence(summary.messages[0]))
    assert "Original answer" not in str(_evidence(summary.messages[0]))


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
            yield {0: _interact(variable=None, prompt="Your learning needs?")}

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
                "variable": None,
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
    assert runtime.store.load(view["session_id"]).variables == {}
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
    assert runtime.store.load(replacement["session_id"]).turn_index == 0


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
                0: _interact(call_id="goal", variable="goal", prompt="Your goal?"),
                1: _interact(call_id="pace", variable="pace", prompt="Your pace?"),
            }

    app, runtime, factories = _runtime(script)
    view = _start(runtime, "Collect %{{goal}} and %{{pace}}, then finish.")
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
            yield {0: _interact(variable="goal", prompt="Your goal?")}
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
    view = _start(runtime, "Collect %{{goal}} and allow a working note %{{scratch}}.")
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
        runtime.store.load(view["session_id"]).variables["scratch"]
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
    view = _start(runtime, "Collect %{{learning_goal}} and finish.")
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
