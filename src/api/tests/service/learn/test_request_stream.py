"""Lesson request boundaries close once without turning cancellation into output."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from flaskr.service.learn import routes, runscript_v2
from flaskr.service.learn.learn_dtos import RunElementSSEMessageDTO

from . import test_runscript_v2_lock as existing

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


@pytest.fixture(params=["formal", "preview"])
def request_boundary(
    request: pytest.FixtureRequest,
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[
    [Callable[[], Iterator[RunElementSSEMessageDTO]]], list[dict[str, object]]
]:
    def collect(
        factory: Callable[[], Iterator[RunElementSSEMessageDTO]],
    ) -> list[dict[str, object]]:
        if request.param == "formal":
            cache = existing.FakeCacheProvider(existing.FakeLock([True]))
            monkeypatch.setattr(runscript_v2, "cache_provider", cache)
            monkeypatch.setattr(
                runscript_v2,
                "ListenElementRunAdapter",
                existing.FakeListenElementAdapter,
            )
            monkeypatch.setattr(runscript_v2, "_teaches_with_agent", lambda **_k: False)
            monkeypatch.setattr(runscript_v2, "_lesson_events", lambda **_k: factory())
            monkeypatch.setattr(
                runscript_v2, "_remove_db_session_safely", lambda *_a, **_k: None
            )
            monkeypatch.setattr(
                runscript_v2, "_discard_session_connection", lambda **_k: None
            )
            app.config["SSE_HEARTBEAT_INTERVAL"] = 0
            chunks = list(runscript_v2.run_script(app, "course", "lesson", "learner"))
        else:
            with app.test_request_context("/"):
                response = routes._stream_sse_response(
                    app,
                    message_iter_factory=factory,
                    close_log="closed",
                    error_log="failed",
                    terminal_event_factory=lambda: RunElementSSEMessageDTO(
                        type="done", event_type="done", content="", is_terminal=True
                    ),
                    error_event_factory=lambda _exc: RunElementSSEMessageDTO(
                        type="error", event_type="error", content="failed"
                    ),
                )
                chunks = list(response.response)
        return [json.loads(chunk.removeprefix("data: ")) for chunk in chunks]

    return collect


@pytest.mark.parametrize("existing_terminal", [False, True])
def test_request_eof_or_existing_terminal_closes_once_after_audio_ready(
    request_boundary: Callable,
    existing_terminal: bool,
) -> None:
    def source() -> Iterator[RunElementSSEMessageDTO]:
        yield RunElementSSEMessageDTO(
            type="element", event_type="element", content="text"
        )
        yield RunElementSSEMessageDTO(
            type="done", event_type="done", content="", is_terminal=False
        )
        yield RunElementSSEMessageDTO(
            type="audio_backfill_ready",
            event_type="audio_backfill_ready",
            content="ready",
        )
        if existing_terminal:
            yield RunElementSSEMessageDTO(
                type="done", event_type="done", content="", is_terminal=True
            )
            yield RunElementSSEMessageDTO(
                type="done", event_type="done", content="", is_terminal=True
            )

    messages = request_boundary(source)
    assert sum(message.get("is_terminal") is True for message in messages) == 1
    assert [message["type"] for message in messages][-2:] == [
        "audio_backfill_ready",
        "done",
    ]
    assert messages[-1].get("generated_block_bid", "") == ""


def test_an_empty_request_still_closes_without_a_lesson_element(
    request_boundary: Callable,
) -> None:
    messages = request_boundary(lambda: iter(()))
    assert [message["type"] for message in messages] == ["done"]
    assert messages[0]["is_terminal"] is True
    assert not messages[0].get("generated_block_bid")


def test_a_request_error_is_followed_by_one_terminal(
    request_boundary: Callable,
) -> None:
    def source() -> Iterator[RunElementSSEMessageDTO]:
        yield RunElementSSEMessageDTO(
            type="element", event_type="element", content="text"
        )
        message = "provider failure"
        raise ValueError(message)

    messages = request_boundary(source)
    assert sum(message.get("is_terminal") is True for message in messages) == 1
    assert [
        message["type"] for message in messages if message["type"] in {"error", "done"}
    ] == ["error", "done"]
