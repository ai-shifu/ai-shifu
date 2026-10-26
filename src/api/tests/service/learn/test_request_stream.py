"""Lesson request boundaries close once without turning cancellation into output."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from flaskr.service.learn import routes, runscript_v2
from flaskr.service.learn.learn_dtos import RunElementSSEMessageDTO
from flaskr.service.learn.request_stream import stream_request

from . import test_runscript_v2_lock as existing

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


def _done() -> dict[str, object]:
    return {"type": "done", "is_terminal": True}


def test_source_failure_and_transport_failure_have_different_outcomes() -> None:
    closed = []
    errors = []

    def source() -> Iterator[dict[str, object]]:
        try:
            yield {"type": "element"}
            message = "provider disconnected"
            raise OSError(message)
        finally:
            closed.append(True)

    def error_messages(exc: Exception) -> Iterator[dict[str, object]]:
        errors.append(type(exc))
        yield {"type": "error"}

    completed = stream_request(
        source,
        render=lambda message: message,
        terminal_event_factory=_done,
        error_messages_factory=error_messages,
    )
    assert [message["type"] for message in completed] == ["element", "error", "done"]
    assert errors == [OSError]

    cancelled = stream_request(
        source,
        render=lambda message: message,
        terminal_event_factory=_done,
        error_messages_factory=error_messages,
    )
    next(cancelled)
    with pytest.raises(StopIteration):
        cancelled.throw(OSError("client disconnected"))
    assert errors == [OSError]
    assert closed == [True, True]
    assert list(cancelled) == []


@pytest.mark.parametrize("termination", ["close", "base-exception"])
def test_cancel_closes_the_source_without_emitting_a_terminal(termination: str) -> None:
    class Cancelled(BaseException):
        pass

    closed = []

    def source() -> Iterator[dict[str, object]]:
        try:
            yield {"type": "element"}
            pytest.fail("Cancelled requests must not advance the producer")
        finally:
            closed.append(True)

    stream = stream_request(
        source, render=lambda message: message, terminal_event_factory=_done
    )
    next(stream)
    if termination == "close":
        stream.close()
    else:
        with pytest.raises(Cancelled):
            stream.throw(Cancelled())
    assert closed == [True]
    assert list(stream) == []


@pytest.mark.parametrize("pending_output", [False, True])
def test_an_internally_cancelled_source_does_not_become_successful_eof(
    pending_output: bool,
) -> None:
    stopped = []

    def source() -> Iterator[dict[str, object]]:
        yield {"type": "element"}
        stopped.append(True)
        if pending_output:
            yield {"type": "element", "content": "arrived after cancellation"}

    stream = stream_request(
        source,
        render=lambda message: message,
        terminal_event_factory=_done,
        cancelled=lambda: bool(stopped),
    )
    assert list(stream) == [{"type": "element"}]


def test_a_terminal_closes_the_source_before_later_output() -> None:
    closed = []

    def source() -> Iterator[dict[str, object]]:
        try:
            yield _done()
            pytest.fail("A terminal response must not be followed by more output")
        finally:
            closed.append(True)

    stream = stream_request(
        source,
        render=lambda message: message,
        terminal_event_factory=lambda: pytest.fail("Already terminal"),
    )
    assert list(stream) == [_done()]
    assert closed == [True]


def test_serialization_failure_is_mapped_but_a_consumer_exception_is_not() -> None:
    errors = []

    def error_messages(exc: Exception) -> Iterator[dict[str, object]]:
        errors.append(type(exc))
        yield {"type": "error"}

    failed = stream_request(
        lambda: iter([{"type": "element", "content": object()}]),
        render=json.dumps,
        terminal_event_factory=_done,
        error_messages_factory=error_messages,
    )
    assert [json.loads(chunk)["type"] for chunk in failed] == ["error", "done"]
    assert errors == [TypeError]

    disconnected = stream_request(
        lambda: iter([{"type": "element"}]),
        render=json.dumps,
        terminal_event_factory=_done,
        error_messages_factory=error_messages,
    )
    next(disconnected)
    with pytest.raises(TypeError, match="consumer failure"):
        disconnected.throw(TypeError("consumer failure"))
    assert errors == [TypeError]
    assert list(disconnected) == []


def test_error_serialization_failure_is_not_retried_forever() -> None:
    errors = []

    def error_messages(exc: Exception) -> Iterator[dict[str, object]]:
        errors.append(type(exc))
        yield {"type": "error", "content": object()}

    failed = stream_request(
        lambda: iter([{"type": "element", "content": object()}]),
        render=json.dumps,
        terminal_event_factory=_done,
        error_messages_factory=error_messages,
    )
    with pytest.raises(TypeError):
        list(failed)
    assert errors == [TypeError]


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
