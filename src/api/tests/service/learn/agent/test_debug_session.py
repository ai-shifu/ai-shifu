"""Editor debug sessions resume safely without touching lesson sessions."""

from __future__ import annotations

import pytest
from flaskr.service.common.models import AppError
from flaskr.service.learn.agent import debug_session
from flaskr.service.learn.agent.engine.script import ScriptBundle
from flaskr.service.learn.agent.engine.session import Session
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    PlaygroundPreviewRequest,
    RunMarkdownFlowDTO,
)


class _Cache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl


def test_debug_session_resumes_only_the_same_run_and_script(
    app: object, monkeypatch: object
) -> None:
    cache = _Cache()
    monkeypatch.setattr(debug_session, "cache", cache)
    first = debug_session.DebugSessionStore(
        app, user_bid="teacher", shifu_bid="course", outline_bid="lesson", run_bid="one"
    )
    other = debug_session.DebugSessionStore(
        app, user_bid="teacher", shifu_bid="course", outline_bid="lesson", run_bid="two"
    )
    session = Session(script=ScriptBundle(script="Current draft"))
    session.memory["answer"] = "yes"

    first.save(session)

    assert first.load(script="Current draft").memory["answer"] == "yes"
    assert first.load(script="Edited draft") is None
    assert other.load(script="Current draft") is None
    assert list(cache.ttls.values()) == [30 * 60]
    cache.values[first._key] = "invalid history"
    assert first.load(script="Current draft") is None


def test_editor_debug_uses_the_existing_lesson_and_element_pipeline(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.learn.agent import lesson_entry

    calls: list[dict[str, object]] = []

    def lesson_events(_app: object, **kwargs: object) -> object:
        calls.append(kwargs)
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="turn",
            type=GeneratedType.CONTENT,
            content="Taught by the agent",
        )
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="turn",
            type=GeneratedType.DONE,
            content="",
        )

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", lesson_events)
    messages = list(
        debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Current editor draft",
                block_index=0,
                variables={"goal": "learn"},
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="run-one",
        )
    )

    assert messages[0].type == "preview_engine"
    assert messages[0].content == "2.0"
    assert any(message.type == "element" for message in messages)
    assert messages[-1].type == "done"
    assert calls[0]["script_override"] == "Current editor draft"
    assert calls[0]["preview_mode"] is True
    assert isinstance(calls[0]["debug_store"], debug_session.DebugSessionStore)


def test_expired_debug_answer_does_not_start_a_new_lesson(
    app: object, monkeypatch: object
) -> None:
    monkeypatch.setattr(debug_session, "cache", _Cache())
    stream = debug_session.stream_debug_preview(
        app,
        preview_request=PlaygroundPreviewRequest(
            content="Current draft",
            block_index=0,
            user_input={"answer": ["yes"]},
        ),
        shifu_bid="course",
        outline_bid="lesson",
        user_bid="teacher",
        run_bid="expired-run",
    )

    with pytest.raises(AppError) as exc_info:
        next(stream)
    assert exc_info.value.code == 4019
