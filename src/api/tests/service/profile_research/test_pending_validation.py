"""Refuse unsafe cached controls before replaying or accepting a profile answer."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any

import pytest
from flaskr.service.learn.agent.api import Session
from flaskr.service.profile_research.runtime import (
    PROFILE_RESEARCH_SESSION_TTL_SECONDS,
    ProfileResearchError,
)

from tests.service.profile_research.test_v2_runtime import (
    StreamChunks,
    _finish,
    _finished,
    _interact,
    _run,
    _runtime,
    _start,
    _tool_returns,
)

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


@pytest.mark.parametrize(
    "cached_control",
    [
        "unrenderable_display",
        "changed_stored_value",
        "duplicate_pending",
        "content_block",
    ],
)
@pytest.mark.parametrize("submit_answer", [True, False], ids=["answer", "redisplay"])
def test_invalid_cached_pending_cannot_accept_or_redisplay_a_question(
    cached_control: str, submit_answer: bool
) -> None:
    model_calls: list[list[ModelMessage]] = []
    content = "Introduce the learner's role."

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        model_calls.append(messages)
        if factories[-1] == 0:
            yield "Let us understand your role."
        elif _finished(messages):
            yield " "
        elif _tool_returns(messages):
            yield _finish()
        else:
            yield {
                0: _interact(
                    call_id="role",
                    variable="role",
                    kind="single",
                    prompt="Choose your role",
                    options=[
                        {"display": "Teacher", "value": "teacher"},
                        {"display": "Engineer", "value": "engineer"},
                    ],
                )
            }

    _app, runtime, factories = _runtime(script)
    view = _start(
        runtime,
        f"{content}\n\n---\n\n?[%{{{{role}}}} Teacher//teacher | Engineer//engineer]",
    )
    _run(runtime, view)
    _run(runtime, view, index=1, request_id="render-role")
    cached = runtime.store.load(view["session_id"]).to_cache_payload()
    pending = cached["engine_session"]["pending"][0]
    submitted_value = "teacher"
    if cached_control == "unrenderable_display":
        pending["spec"]["options"][0]["display"] = "Teacher\nInjected label"
    elif cached_control == "changed_stored_value":
        pending["spec"]["options"][0]["value"] = "parent"
        submitted_value = "parent"
    elif cached_control == "duplicate_pending":
        duplicate = deepcopy(pending)
        duplicate["tool_call_id"] = "duplicate-role"
        cached["engine_session"]["pending"].append(duplicate)
    else:
        cached["block_index"] = 0
        cached["engine_block_index"] = 0
        cached["engine_session"]["script"]["script"] = content

    # These remain valid typed sessions; the host must reject their control
    # contract rather than relying on malformed JSON or a Pydantic failure.
    restored = Session.from_dict(cached["engine_session"])
    assert restored.pending
    cache_key = runtime.store._key(view["session_id"])
    runtime.store._cache.setex(
        cache_key,
        PROFILE_RESEARCH_SESSION_TTL_SECONDS,
        json.dumps(cached),
    )
    original_cache = runtime.store._cache.get(cache_key)
    original_state = runtime.store.load(view["session_id"]).to_cache_payload()
    call_count = len(model_calls)

    with pytest.raises(
        ProfileResearchError, match="cannot resume the saved profile question"
    ):
        _run(
            runtime,
            view,
            index=cached["block_index"],
            values={"role": [submitted_value]} if submit_answer else None,
            request_id="answer-invalid" if submit_answer else "redisplay-invalid",
            expected_interaction_id="role" if submit_answer else None,
        )

    assert len(model_calls) == call_count
    assert runtime.store._cache.get(cache_key) == original_cache
    unchanged: dict[str, Any] = runtime.store.load(
        view["session_id"]
    ).to_cache_payload()
    assert unchanged == original_state
    assert unchanged["accepted_answers"] == []
    assert unchanged["variables"] == {}
    assert unchanged["block_index"] == cached["block_index"]
