"""Commit native state before publishing a question, then replay its exact identity."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

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


def test_failed_cache_write_publishes_no_question_and_retry_can_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def script(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal attempts
        attempts += 1
        yield {0: _interact(call_id=f"question-{attempts}")}

    _app, runtime, _factories = _runtime(script)
    view = _start(runtime, "Ask about learning needs.")
    original = runtime.store.load(view["session_id"]).to_cache_payload()
    save = runtime.store.save

    def fail(_session: object) -> None:
        message = "cache write failed"
        raise RuntimeError(message)

    monkeypatch.setattr(runtime.store, "save", fail)
    with pytest.raises(RuntimeError, match="cache write failed"):
        _run(runtime, view)
    assert runtime.store.load(view["session_id"]).to_cache_payload() == original
    monkeypatch.setattr(runtime.store, "save", save)
    events = _run(runtime, view)
    assert (
        next(event for event in events if event["event_type"] == "interaction")[
            "interaction_id"
        ]
        == "question-2"
    )
    assert _run(runtime, view, index=0) == events
    assert attempts == 2
