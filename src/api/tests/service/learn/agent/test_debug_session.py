"""Editor debug sessions resume safely without touching lesson sessions."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.service.common.models import AppError
from flaskr.service.learn import routes
from flaskr.service.learn.agent import debug_session
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    PlaygroundPreviewRequest,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)
from markdownflow.engine.script import ScriptBundle
from markdownflow.engine.session import Session

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


class _Cache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl


def _request_messages(
    app: object, factory: Callable[[], Iterator[RunElementSSEMessageDTO]]
) -> list[SimpleNamespace]:
    # HTTP completion belongs to the request boundary, not the lesson generator.
    with app.test_request_context("/"):
        response = routes._stream_sse_response(
            app,
            message_iter_factory=factory,
            close_log="closed",
            error_log="failed",
            terminal_event_factory=lambda: RunElementSSEMessageDTO(
                type="done", event_type="done", content="", is_terminal=True
            ),
        )
        try:
            return [
                SimpleNamespace(**json.loads(chunk.removeprefix("data: ")))
                for chunk in response.response
            ]
        finally:
            response.close()


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
    messages = _request_messages(
        app,
        lambda: debug_session.stream_debug_preview(
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
        ),
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


def test_question_closes_editor_response_without_ending_the_lesson(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.learn.agent import lesson_entry

    def lesson_events(_app: object, **_kwargs: object) -> object:
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="question",
            type=GeneratedType.INTERACTION,
            content="Which option?",
        )
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="question",
            type=GeneratedType.BREAK,
            content="",
        )

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", lesson_events)
    messages = _request_messages(
        app,
        lambda: debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Current draft", block_index=0
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="question-run",
        ),
    )

    done_messages = [message for message in messages if message.type == "done"]
    assert [message.is_terminal for message in done_messages] == [False, True]


def test_finished_debug_reopening_closes_the_empty_response(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.learn.agent import lesson_entry

    # Finished lessons deliberately produce no new block or model request.
    monkeypatch.setattr(lesson_entry, "agent_lesson_events", lambda *_a, **_k: iter(()))
    messages = _request_messages(
        app,
        lambda: debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Current draft", block_index=0
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="finished-run",
        ),
    )

    assert [message.type for message in messages] == ["preview_engine", "done"]
    assert messages[-1].is_terminal is True
    assert not getattr(messages[-1], "generated_block_bid", None)
