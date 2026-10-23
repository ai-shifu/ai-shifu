"""Replace an uncommitted rendered question without keeping stale controls."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from flaskr.service.profile_research.runtime import (
    PROFILE_ONBOARDING_PURPOSE,
    ProfileResearchValidationError,
)

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
    from flaskr.service.profile_research.session import _ProfileResearchSession
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


@pytest.mark.parametrize("interruption", ["save_failure", "disconnect"])
def test_failed_render_is_replaced_by_the_same_element_with_a_fresh_token(
    monkeypatch: pytest.MonkeyPatch, interruption: str
) -> None:
    rendered_questions = 0

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal rendered_questions
        if _finished(messages):
            yield " "
        elif answers := _tool_returns(messages):
            assert "Practical skills" in str(answers[0].content)
            yield _finish()
        else:
            rendered_questions += 1
            yield {0: _interact(call_id=f"question-{rendered_questions}")}

    _app, runtime, factories = _runtime(script)
    view = _start(runtime, "?[%{{learning_goal}}...What do you want to learn?]")
    original = runtime.store.load(view["session_id"]).to_cache_payload()
    original_save = runtime.store.save
    save_calls = 0

    def fail_first_save(session: _ProfileResearchSession) -> None:
        nonlocal save_calls
        save_calls += 1
        if save_calls == 1:
            message = "cache unavailable before write"
            raise RuntimeError(message)
        original_save(session)

    if interruption == "save_failure":
        monkeypatch.setattr(runtime.store, "save", fail_first_save)
    first_events: list[dict[str, Any]] = []
    first_stream = runtime.stream_session(
        user_bid="v2-learner",
        session_id=view["session_id"],
        user_input=None,
        expected_purpose=PROFILE_ONBOARDING_PURPOSE,
        expected_block_index=0,
        request_id="render",
    )

    if interruption == "save_failure":
        with pytest.raises(RuntimeError, match="cache unavailable before write"):
            first_events.extend(first_stream)
    else:
        first_events.append(next(first_stream))
        first_stream.close()

    first_question = next(
        event for event in first_events if event["event_type"] == "interaction"
    )
    assert first_question["interaction_id"] == "question-1"
    assert not any(event.get("is_terminal") for event in first_events)
    assert runtime.store.load(view["session_id"]).to_cache_payload() == original

    retried = _run(runtime, view)
    replacement = next(
        event for event in retried if event["event_type"] == "interaction"
    )

    assert replacement["interaction_id"] == "question-2"
    assert replacement["generated_block_bid"] == first_question["generated_block_bid"]
    assert _terminal(retried)["awaiting_input"] is True
    stored = runtime.store.load(view["session_id"])
    assert stored.block_index == 0
    assert stored.engine_session["pending"][0]["tool_call_id"] == "question-2"
    assert stored.variables == {}
    assert stored.accepted_answers == []
    assert _run(runtime, view) == retried
    assert rendered_questions == 2

    before_stale = runtime.store.load(view["session_id"]).to_cache_payload()
    before_factory_count = len(factories)
    with pytest.raises(ProfileResearchValidationError, match="pending question"):
        _run(
            runtime,
            view,
            values={"learning_goal": ["Practical skills"]},
            request_id="stale-answer",
            expected_interaction_id="question-1",
        )

    assert runtime.store.load(view["session_id"]).to_cache_payload() == before_stale
    assert len(factories) == before_factory_count
    answered = _run(
        runtime,
        view,
        values={"learning_goal": ["Practical skills"]},
        request_id="answer",
        expected_interaction_id="question-2",
    )

    assert _terminal(answered)["next_block_index"] == 1
    assert _terminal(answered)["awaiting_input"] is False
    assert not any(event["event_type"] == "interaction" for event in answered)
    stored = runtime.store.load(view["session_id"])
    assert stored.variables == {"learning_goal": "Practical skills"}
    assert stored.accepted_answers == ["Practical skills"]
    assert rendered_questions == 2
