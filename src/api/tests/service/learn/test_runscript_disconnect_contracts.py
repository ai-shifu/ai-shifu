"""Close SSE producers and release ownership after transport cancellation."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import has_app_context
from flaskr.service.learn import runscript_v2 as runtime
from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO

from . import test_runscript_v2_lock as existing


@pytest.fixture
def stream_runtime(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    app = existing._make_test_app()
    app.config["SSE_HEARTBEAT_INTERVAL"] = 0.001
    lock = existing.FakeLock([True])
    cache = existing.FakeCacheProvider(lock)
    monkeypatch.setattr(runtime, "cache_provider", cache)
    monkeypatch.setattr(
        runtime, "ListenElementRunAdapter", existing.FakeListenElementAdapter
    )
    monkeypatch.setattr(runtime, "_teaches_with_agent", lambda **_kwargs: False)
    remove, discard, release = Mock(), Mock(), Mock()
    monkeypatch.setattr(runtime, "_remove_db_session_safely", remove)
    monkeypatch.setattr(runtime, "_discard_session_connection", discard)
    monkeypatch.setattr(runtime, "_ask_sem_acquire", Mock(return_value=True))
    monkeypatch.setattr(runtime, "_ask_sem_release", release)
    return SimpleNamespace(
        app=app, cache=cache, lock=lock, remove=remove, discard=discard, release=release
    )


@pytest.mark.parametrize("phase", ["heartbeat", "data"])
@pytest.mark.parametrize("termination", ["close", "broken-pipe", "socket-error"])
def test_transport_disconnect_stops_producer_and_releases_course_lock(
    stream_runtime: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    termination: str,
) -> None:
    closed = []
    observation = {}

    def produce(**kwargs: object) -> object:
        stop = kwargs["stop_event"]
        observation["stop"] = stop
        observation["app_context"] = has_app_context()
        try:
            if phase == "data":
                yield RunMarkdownFlowDTO(
                    outline_bid="lesson",
                    generated_block_bid="block",
                    type=GeneratedType.CONTENT,
                    content="Visible content",
                )
            assert stop.wait(2), "The SSE consumer must stop its producer"
            message = "provider observed cancellation"
            raise RuntimeError(message)
        finally:
            closed.append(True)

    monkeypatch.setattr(runtime, "_lesson_events", produce)
    stream = runtime.run_script(stream_runtime.app, "course", "lesson", "learner")
    first = existing._parse_sse_events([next(stream)])[0]
    while phase == "data" and first["type"] == "heartbeat":
        first = existing._parse_sse_events([next(stream)])[0]
    assert first["type"] == ("heartbeat" if phase == "heartbeat" else "element")
    assert stream_runtime.cache.values
    if termination == "close":
        stream.close()
    else:
        error = (
            BrokenPipeError("closed")
            if termination == "broken-pipe"
            else OSError("closed")
        )
        with pytest.raises(StopIteration):
            stream.throw(error)
    assert observation["app_context"] is True
    assert observation["stop"].is_set()
    assert closed == [True]
    assert stream_runtime.lock.release_calls == 1
    assert stream_runtime.cache.values == {}
    stream_runtime.discard.assert_called_once_with(source="run_script producer abort")
    stream_runtime.remove.assert_called_once_with(
        stream_runtime.app, source="run_script producer"
    )
    stream_runtime.release.assert_not_called()
    assert list(stream) == []


def test_canceled_ask_releases_only_its_semaphore_and_keeps_lesson_status(
    stream_runtime: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lesson_key = runtime._get_run_script_status_key(
        stream_runtime.app, "learner", "lesson"
    )
    stream_runtime.cache.setex(lesson_key, 60, "active-lesson")
    stopped = []

    def produce(**kwargs: object) -> object:
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="block",
            type=GeneratedType.CONTENT,
            content="Answer",
        )
        assert kwargs["stop_event"].wait(2)
        stopped.append(True)
        # A provider may return a final chunk after cancellation; never send it.
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="block",
            type=GeneratedType.CONTENT,
            content="Discarded answer",
        )

    monkeypatch.setattr(runtime, "_lesson_events", produce)
    stream = runtime.run_script(
        stream_runtime.app, "course", "lesson", "learner", input_type="ask"
    )
    first = existing._parse_sse_events([next(stream)])[0]
    while first["type"] == "heartbeat":
        first = existing._parse_sse_events([next(stream)])[0]
    assert first["content"] == "Answer"
    stream.close()
    assert stopped == [True]
    assert list(stream) == []
    assert stream_runtime.cache.get(lesson_key) == b"active-lesson"
    assert stream_runtime.lock.acquire_calls == stream_runtime.lock.release_calls == 0
    stream_runtime.release.assert_called_once_with(
        stream_runtime.app, "learner", "lesson"
    )
    stream_runtime.discard.assert_called_once_with(source="run_script producer abort")
