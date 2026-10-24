"""Unsafe cached native sessions cannot publish controls or consume learner input."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from flaskr.service.profile_research.runtime import ProfileResearchError

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


@pytest.mark.parametrize("corruption", ["unrenderable", "user", "script"])
@pytest.mark.parametrize("answer", [True, False])
def test_invalid_cached_native_state_is_rejected_without_provider_or_cache_mutation(
    corruption: str, answer: bool
) -> None:
    calls: list[list[ModelMessage]] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls.append(messages)
        yield {
            0: _interact(
                variable="role",
                kind="single",
                prompt="Your role?",
                options=[{"display": "Teacher", "value": "teacher"}],
            )
        }

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "Collect %{{role}}.")
    _run(runtime, view)
    payload = runtime.store.load(view["session_id"]).to_cache_payload()
    if corruption == "unrenderable":
        payload["engine_session"]["pending"][0]["spec"]["options"][0]["display"] = (
            "Teacher\nInjected"
        )
    elif corruption == "user":
        payload["engine_session"]["user_id"] = "another-user"
    else:
        payload["engine_session"]["script"]["script"] = "A different questionnaire"
    key = runtime.store._key(view["session_id"])
    runtime.store._cache.setex(key, 1800, json.dumps(payload))
    original = runtime.store._cache.get(key)
    count = len(calls)
    with pytest.raises(ProfileResearchError):
        _run(
            runtime,
            view,
            values={"role": ["teacher"]} if answer else None,
            request_id="invalid",
            expected_interaction_id="question" if answer else None,
        )
    assert len(calls) == count
    assert runtime.store._cache.get(key) == original
