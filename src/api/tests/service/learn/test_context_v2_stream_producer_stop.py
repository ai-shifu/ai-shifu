"""Verify context v2 stream producer stop behavior."""

import threading
import time
import types

from flaskr.service.learn.context_v2 import RunScriptContextV2

_PRODUCER_THREAD_NAME = "mdflow_stream_result_producer"


def _make_context_stub(app):
    stub = types.SimpleNamespace(app=app)
    stub._stop_requested = lambda: False
    stub._stop_if_requested = lambda: None
    return stub


def test_stream_producer_stops_when_consumer_exits_early(app):
    stop_streaming = threading.Event()

    def endless_stream():
        index = 0
        while not stop_streaming.is_set():
            yield index
            index += 1
            time.sleep(0.01)

    stub = _make_context_stub(app)
    iterator = RunScriptContextV2._iter_stream_result_with_idle_callback(
        stub,
        endless_stream(),
        idle_callback=None,
    )

    try:
        assert next(iterator) == ("item", 0)
    finally:
        # Close the consumer mid-stream: the finally block must signal the
        # producer thread to stop instead of letting it stream forever.
        iterator.close()
        stop_streaming.set()

    assert not any(
        thread.name == _PRODUCER_THREAD_NAME and thread.is_alive()
        for thread in threading.enumerate()
    )


def test_early_consumer_exit_invalidates_producer_session(app, monkeypatch):
    from flaskr.service.learn import context_v2

    invalidations = []
    monkeypatch.setattr(
        context_v2,
        "invalidate_session",
        lambda *, source, session=None: invalidations.append(source) or True,
    )

    stop_streaming = threading.Event()

    def endless_stream():
        index = 0
        while not stop_streaming.is_set():
            yield index
            index += 1
            time.sleep(0.01)

    stub = _make_context_stub(app)
    iterator = RunScriptContextV2._iter_stream_result_with_idle_callback(
        stub,
        endless_stream(),
        idle_callback=None,
    )
    try:
        assert next(iterator) == ("item", 0)
    finally:
        iterator.close()
        stop_streaming.set()

    assert invalidations == ["mdflow stream producer abort"]


def test_natural_exhaustion_does_not_invalidate_producer_session(app, monkeypatch):
    from flaskr.service.learn import context_v2

    invalidations = []
    monkeypatch.setattr(
        context_v2,
        "invalidate_session",
        lambda *, source, session=None: invalidations.append(source) or True,
    )

    def short_stream():
        yield "a"
        yield "b"

    stub = _make_context_stub(app)
    items = [
        payload
        for kind, payload in RunScriptContextV2._iter_stream_result_with_idle_callback(
            stub,
            short_stream(),
            idle_callback=None,
        )
        if kind == "item"
    ]

    assert items == ["a", "b"]
    assert invalidations == []


def test_tts_finalize_failure_runs_classified_cleanup(app, monkeypatch):
    """A DB failure swallowed by the TTS finalize wrapper must still run the classified cleanup so an interrupted exchange discards the connection."""
    import types

    from flaskr.service.learn import context_v2
    from sqlalchemy.exc import ResourceClosedError

    outcomes = []
    monkeypatch.setattr(
        context_v2,
        "cleanup_session_after",
        lambda exc, *, source, session=None: (
            outcomes.append((type(exc).__name__, source)) or "invalidated"
        ),
    )

    class _FailingProcessor:
        next_element_index = 0

        def finalize(self, *, commit):
            message = "desynced during finalize"
            raise ResourceClosedError(message)
            yield  # pragma: no cover - generator marker

    stub = types.SimpleNamespace(app=app)
    list(
        RunScriptContextV2._finalize_stream_tts_processor(
            stub, _FailingProcessor(), log_prefix="finalize failed"
        )
    )

    assert outcomes == [("ResourceClosedError", "finalize stream tts processor")]
