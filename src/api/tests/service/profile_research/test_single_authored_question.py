"""Keep each authored profile interaction to its single published pause."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from flaskr.service.profile_research.runtime import (
    PROFILE_ONBOARDING_PURPOSE,
    PROFILE_RESEARCH_SESSION_TTL_SECONDS,
    ProfileResearchError,
)
from pydantic_ai.messages import ModelRequest, RetryPromptPart

from tests.service.profile_research.test_v2_runtime import (
    StreamChunks,
    _finish,
    _finished,
    _interact,
    _run,
    _runtime,
    _start,
    _terminal,
    _tool_returns,
)

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


@pytest.mark.parametrize("legacy_pending", [False, True])
def test_duplicate_calls_for_one_authored_question_publish_nothing(
    legacy_pending: bool,
) -> None:
    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield {
            0: _interact(call_id="first-copy"),
            1: _interact(call_id="second-copy"),
        }

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "?[%{{learning_goal}}...What do you want to learn?]")
    if legacy_pending:
        legacy = runtime.store.load(view["session_id"]).to_cache_payload()
        legacy["schema_version"] = 1
        legacy["awaiting_input"] = True
        legacy.pop("engine_session", None)
        legacy.pop("engine_block_index", None)
        runtime.store._cache.setex(
            runtime.store._key(view["session_id"]),
            PROFILE_RESEARCH_SESSION_TTL_SECONDS,
            json.dumps(legacy),
        )
    original = runtime.store.load(view["session_id"]).to_cache_payload()
    events: list[dict[str, Any]] = []
    stream = runtime.stream_session(
        user_bid="v2-learner",
        session_id=view["session_id"],
        user_input={"learning_goal": ["Practical skills"]} if legacy_pending else None,
        expected_purpose=PROFILE_ONBOARDING_PURPOSE,
        expected_block_index=0,
        request_id="duplicate-question",
    )

    with pytest.raises(ProfileResearchError):
        events.extend(stream)

    assert events == []
    assert runtime.store.load(view["session_id"]).to_cache_payload() == original


def test_answered_question_cannot_be_asked_again_before_finishing_the_step() -> None:
    answer_attempts = 0
    retry_messages: list[RetryPromptPart] = []
    accepted_results: list[str] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal answer_attempts
        if _finished(messages):
            yield " "
        elif answers := _tool_returns(messages):
            answer_attempts += 1
            accepted_results.append(str(answers[0].content))
            retry_messages.extend(
                part
                for message in messages
                if isinstance(message, ModelRequest)
                for part in message.parts
                if isinstance(part, RetryPromptPart)
            )
            if answer_attempts == 1:
                yield {0: _interact(call_id="repeated-question")}
            else:
                yield _finish()
        else:
            yield {0: _interact(call_id="authored-question")}

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "?[%{{learning_goal}}...What do you want to learn?]")
    _run(runtime, view)
    answered = _run(
        runtime,
        view,
        values={"learning_goal": ["Practical skills"]},
        request_id="answer",
        expected_interaction_id="authored-question",
    )

    assert answer_attempts == 2
    assert retry_messages
    assert all("Practical skills" in result for result in accepted_results)
    assert not any(event["event_type"] == "interaction" for event in answered)
    assert _terminal(answered)["next_block_index"] == 1
    assert _terminal(answered)["awaiting_input"] is False
    stored = runtime.store.load(view["session_id"])
    assert stored.variables == {"learning_goal": "Practical skills"}
    assert stored.accepted_answers == ["Practical skills"]
    assert stored.engine_session["pending"] == []
    assert stored.engine_session["finished"] is True
    assert (
        _run(
            runtime,
            view,
            values={"learning_goal": ["Practical skills"]},
            request_id="answer",
            expected_interaction_id="authored-question",
        )
        == answered
    )
    assert answer_attempts == 2


def test_uncorrected_repeat_keeps_the_original_question_and_evidence() -> None:
    repeats = 0

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal repeats
        if _tool_returns(messages):
            repeats += 1
            yield {0: _interact(call_id=f"repeated-{repeats}")}
        else:
            yield {0: _interact(call_id="authored-question")}

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "?[%{{learning_goal}}...What do you want to learn?]")
    _run(runtime, view)
    original = runtime.store.load(view["session_id"]).to_cache_payload()
    events: list[dict[str, Any]] = []
    stream = runtime.stream_session(
        user_bid="v2-learner",
        session_id=view["session_id"],
        user_input={"learning_goal": ["Practical skills"]},
        expected_purpose=PROFILE_ONBOARDING_PURPOSE,
        expected_block_index=0,
        request_id="uncorrected-answer",
        expected_interaction_id="authored-question",
    )

    with pytest.raises(ProfileResearchError):
        events.extend(stream)

    assert repeats > 1
    assert events == []
    assert runtime.store.load(view["session_id"]).to_cache_payload() == original
