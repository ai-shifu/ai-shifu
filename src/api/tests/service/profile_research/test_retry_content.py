"""Only accepted model responses may contribute public content or a private draft."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from flaskr.service.profile_research.runtime import (
    PROFILE_ONBOARDING_PURPOSE,
    ProfileResearchError,
)
from pydantic_ai.messages import ModelRequest, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall

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


def _public_content(events: list[dict[str, Any]]) -> str:
    segments: dict[str, str] = {}
    for event in events:
        if event["event_type"] == "content":
            segments[event["generated_block_bid"]] = event["content"]
    return "".join(segments.values())


def test_content_retry_discards_text_from_a_response_with_a_forbidden_control() -> None:
    attempts = 0
    rejected = "Rejected greeting from an invalid response.\n"
    corrected = "Corrected greeting for the learner.\n"

    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            yield rejected
            yield {0: _interact(variable=None, prompt="An unauthorized question?")}
        else:
            yield corrected

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "Greet the learner.\n\n---\n\n?[Continue]")
    events = _run(runtime, view)

    assert attempts == 2
    assert _public_content(events) == corrected
    assert not any(event["event_type"] == "interaction" for event in events)
    assert _terminal(events)["next_block_index"] == 1
    assert rejected.strip() not in str(runtime.store.load(view["session_id"]).context)


def test_summary_retry_discards_the_rejected_draft_and_never_streams_it() -> None:
    attempts = 0
    rejected = "Rejected draft with an invented personal fact."
    corrected = "Learns practical skills."

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal attempts
        if factories[-1] == 1:
            attempts += 1
            if attempts == 1:
                yield rejected
                yield {0: _interact(variable=None, prompt="An unauthorized follow-up?")}
            else:
                yield corrected
        elif _finished(messages):
            yield " "
        elif _tool_returns(messages):
            yield _finish()
        else:
            yield {0: _interact()}

    _app, runtime, factories = _runtime(script)
    view = _start(runtime, "?[%{{learning_goal}}...What do you want to learn?]")
    _run(runtime, view)
    _run(
        runtime,
        view,
        values={"learning_goal": ["Practical skills"]},
        request_id="answer",
        expected_interaction_id="question",
    )
    events = _run(runtime, view, index=1, request_id="summary")

    assert attempts == 2
    assert [event["event_type"] for event in events] == ["done"]
    assert _terminal(events)["profile_draft"] == corrected
    stored = runtime.store.load(view["session_id"])
    assert stored.profile_draft == corrected
    assert rejected not in str(stored.context)


@pytest.mark.parametrize("invalid_tool", ["duplicate", "malformed"])
def test_failed_static_question_does_not_publish_partial_text_visuals_or_controls(
    invalid_tool: str,
) -> None:
    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield "Rejected question preface.\n"
        yield "<div>Rejected visual</div>\n"
        yield "Rejected trailing content.\n"
        if invalid_tool == "duplicate":
            yield {0: _interact(call_id="first"), 1: _interact(call_id="second")}
        else:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="malformed",
                    json_args='{"type":"single","prompt":"Missing options","variable":"learning_goal"}',
                )
            }

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "?[%{{learning_goal}}...What do you want to learn?]")
    original = runtime.store.load(view["session_id"]).to_cache_payload()
    events: list[dict[str, Any]] = []
    with pytest.raises(ProfileResearchError):
        events.extend(
            runtime.stream_session(
                user_bid="v2-learner",
                session_id=view["session_id"],
                user_input=None,
                expected_purpose=PROFILE_ONBOARDING_PURPOSE,
                expected_block_index=0,
                request_id="invalid-question",
            )
        )

    assert events == []
    assert runtime.store.load(view["session_id"]).to_cache_payload() == original


def test_successful_tool_steps_keep_content_before_and_after_the_tool() -> None:
    first = "Start with a short overview.\n"
    second = "Continue with a practical example.\n"

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        remembered = any(
            isinstance(message, ModelRequest)
            and any(
                isinstance(part, ToolReturnPart) and part.tool_name == "remember"
                for part in message.parts
            )
            for message in messages
        )
        if remembered:
            yield second
        else:
            yield first
            yield {
                0: DeltaToolCall(
                    name="remember",
                    tool_call_id="note",
                    json_args=json.dumps(
                        {"key": "pace", "value": "short", "scope": "session"}
                    ),
                )
            }

    _app, runtime, _factories = _runtime(script)
    view = _start(
        runtime, "Explain short sessions and record %{{pace}}.\n\n---\n\n?[Continue]"
    )
    events = _run(runtime, view)

    assert _public_content(events) == first + second
    assert _terminal(events)["next_block_index"] == 1
    assert runtime.store.load(view["session_id"]).variables["pace"] == "short"
