"""Native rejected responses remain private while successful tool-step text survives."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from flaskr.service.profile_research.runtime import (
    PROFILE_ONBOARDING_PURPOSE,
    ProfileResearchError,
)
from pydantic_ai.models.function import DeltaToolCall

from tests.service.profile_research.test_v2_runtime import (
    StreamChunks,
    _interact,
    _run,
    _runtime,
    _start,
)

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


def _public_content(events: list[dict[str, Any]]) -> str:
    parts: dict[str, str] = {}
    for event in events:
        if event["event_type"] == "content":
            parts[event["generated_block_bid"]] = event["content"]
    return "".join(parts.values())


def test_welcome_card_uses_sandbox_and_replays_with_stable_ids() -> None:
    card = '<div class="card">Welcome, learner!</div>\n'
    style = "<style>.card { color: blue; }</style>\n"

    async def script(_messages: list[ModelMessage], info: AgentInfo) -> StreamChunks:
        assert "# Screens (HTML visuals)" in (info.instructions or "")
        assert "The stage preloads Tailwind CSS" in (info.instructions or "")
        yield card + "---\nYour goal?\n" + style
        yield {0: _interact(call_id="goal", variable="goal")}

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "Draw a welcome card, then ask about learning needs.")
    events = _run(runtime, view)
    final = [event for event in events if event.get("is_final")]
    assert [event["element_type"] for event in final] == ["html", "text", "interaction"]
    assert final[0]["content"] == card + style
    assert final[1]["content"] == "---\nYour goal?\n"
    assert final[2]["interaction_id"] == "goal"
    assert all(event["is_terminal"] is False for event in final)
    html_updates = [event for event in events if event.get("element_type") == "html"]
    assert html_updates[0]["content"] == card
    assert html_updates[0]["is_final"] is False
    assert {event["generated_block_bid"] for event in html_updates} == {
        final[0]["generated_block_bid"]
    }
    assert _run(runtime, view, index=0) == events


def test_malformed_question_retry_releases_only_the_corrected_response() -> None:
    attempts = 0

    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            yield "Rejected preface.\n"
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="invalid",
                    json_args='{"type":"single","prompt":"No options"}',
                )
            }
        else:
            yield "Corrected preface.\n"
            yield {0: _interact(variable=None)}

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "Ask about learning needs.")
    events = _run(runtime, view)
    assert attempts == 2
    assert _public_content(events) == "Corrected preface.\n"
    assert len([event for event in events if event["event_type"] == "interaction"]) == 1


def test_uncorrected_tool_failure_publishes_nothing_and_keeps_native_state() -> None:
    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield "Rejected text.\n<div>Rejected visual</div>\nRejected ending.\n"
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="invalid",
                json_args='{"type":"single","prompt":"No options"}',
            )
        }

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "Ask about learning needs.")
    original = runtime.store.load(view["session_id"]).to_cache_payload()
    events = []
    with pytest.raises(ProfileResearchError):
        events.extend(
            runtime.stream_session(
                user_bid="v2-learner",
                session_id=view["session_id"],
                user_input=None,
                expected_purpose=PROFILE_ONBOARDING_PURPOSE,
                expected_turn_index=0,
                request_id="invalid",
            )
        )
    assert events == []
    assert runtime.store.load(view["session_id"]).to_cache_payload() == original
