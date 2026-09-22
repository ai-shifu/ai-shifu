"""Verify deferred speech finalization preserves events and worker cleanup."""

import queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask, has_app_context
from flaskr.service.learn import stream_tts_finalize as finalize


class _ControlledThread:
    """Run the worker explicitly so interruption and queue ordering are deterministic."""

    def __init__(self, *, target: object, name: str, daemon: bool) -> None:
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
        self.joins: list[float] = []

    def start(self) -> None:
        self.started = True

    def join(self, timeout: float) -> None:
        self.joins.append(timeout)


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    app = Flask("tts-finalizer-contract")
    context = SimpleNamespace(app=app, _element_index_cursor=3)
    monkeypatch.setattr(finalize.threading, "Thread", _ControlledThread)
    monkeypatch.setattr(finalize, "get_current_language", lambda: "fr-FR")
    monkeypatch.setattr(
        finalize, "get_shifu_context_snapshot", lambda: {"course": "course-id"}
    )
    language = Mock()
    snapshot = Mock()
    cleanup = Mock()
    invalidate = Mock()
    monkeypatch.setattr(finalize, "set_language", language)
    monkeypatch.setattr(finalize, "apply_shifu_context_snapshot", snapshot)
    monkeypatch.setattr(finalize, "cleanup_session_after", cleanup)
    monkeypatch.setattr(finalize, "invalidate_session", invalidate)
    return SimpleNamespace(
        drainer=finalize.StreamTTSFinalizeDrainer(context, log_prefix="test finalize"),
        context=context,
        language=language,
        snapshot=snapshot,
        cleanup=cleanup,
        invalidate=invalidate,
    )


def test_worker_restores_context_and_emits_audio_before_advancing_cursor(
    harness: SimpleNamespace,
) -> None:
    def produce(*, commit: bool) -> object:
        assert commit is True
        assert has_app_context()
        yield "segment"
        yield "complete"

    processor = SimpleNamespace(finalize=produce, next_element_index=9)
    harness.drainer.submit(processor)
    job = harness.drainer._jobs[0]
    assert job.thread.started
    assert job.thread.daemon
    assert list(harness.drainer.drain()) == []
    assert harness.context._element_index_cursor == 3
    job.thread.target()
    harness.language.assert_called_once_with("fr-FR")
    harness.snapshot.assert_called_once_with({"course": "course-id"})
    stream = harness.drainer.drain(wait=True)
    assert next(stream) == "segment"
    assert harness.context._element_index_cursor == 3
    assert next(stream) == "complete"
    assert list(stream) == []
    assert harness.context._element_index_cursor == 9
    assert harness.drainer._jobs == []
    assert job.thread.joins == [0]
    harness.cleanup.assert_not_called()
    harness.invalidate.assert_not_called()


def test_empty_processor_submission_and_close_are_noops(
    harness: SimpleNamespace,
) -> None:
    harness.drainer.submit(None)
    harness.drainer.close()
    assert list(harness.drainer.drain(wait=True)) == []


def test_failed_worker_keeps_already_produced_events_and_reports_error(
    harness: SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    error = RuntimeError("finalize failed")

    def produce(*, commit: bool) -> object:
        assert commit is True
        yield "segment"
        raise error

    harness.drainer.submit(SimpleNamespace(finalize=produce, next_element_index=2))
    job = harness.drainer._jobs[0]
    job.thread.target()
    harness.cleanup.assert_called_once_with(error, source="stream tts finalize worker")
    assert list(harness.drainer.drain(wait=True)) == ["segment"]
    assert "test finalize: finalize failed" in caplog.text
    assert harness.context._element_index_cursor == 3
    assert harness.drainer._jobs == []
    harness.invalidate.assert_not_called()


def test_interrupted_worker_invalidates_connection_and_always_enqueues_completion(
    harness: SimpleNamespace,
) -> None:
    def produce(*, commit: bool) -> object:
        assert commit is True
        raise KeyboardInterrupt

    harness.drainer.submit(SimpleNamespace(finalize=produce, next_element_index=5))
    with pytest.raises(KeyboardInterrupt):
        harness.drainer._jobs[0].thread.target()
    harness.invalidate.assert_called_once_with(source="stream tts finalize interrupt")
    harness.cleanup.assert_not_called()
    assert list(harness.drainer.drain()) == []
    assert harness.context._element_index_cursor == 5


def test_close_joins_active_workers_without_discarding_pending_events(
    harness: SimpleNamespace,
) -> None:
    processor = SimpleNamespace(
        finalize=Mock(return_value=iter(["event"])), next_element_index=7
    )
    harness.drainer.submit(processor)
    job = harness.drainer._jobs[0]
    harness.drainer.close()
    assert job.thread.joins == [0.1]
    assert harness.drainer._jobs == [job]
    job.thread.target()
    assert list(harness.drainer.drain()) == ["event"]
    processor.finalize.assert_called_once_with(commit=True)


def test_waiting_drain_retries_after_an_empty_poll(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.drainer.submit(SimpleNamespace(finalize=Mock()))
    job = harness.drainer._jobs[0]
    blocking_get = Mock(
        side_effect=[queue.Empty, ("event", "ready"), ("done", 4), queue.Empty]
    )
    monkeypatch.setattr(job.event_queue, "get", blocking_get)
    # get_nowait delegates to get(block=False), so each outer wait still retries.
    assert list(harness.drainer.drain(wait=True)) == ["ready"]
    assert job.done is True
    assert harness.context._element_index_cursor == 4
