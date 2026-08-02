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
