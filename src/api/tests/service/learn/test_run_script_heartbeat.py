"""Forward queued events immediately and time heartbeats from the last chunk."""

import itertools
import threading
import time

import pytest
from flaskr.service.learn.host import run as host_run
from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO

from . import test_runscript_v2_lock as existing


@pytest.fixture
def stream_app(monkeypatch: pytest.MonkeyPatch) -> object:
    app = existing._make_test_app()
    lock = existing.FakeLock([True])
    monkeypatch.setattr(host_run, "cache_provider", existing.FakeCacheProvider(lock))
    monkeypatch.setattr(
        host_run, "ListenElementRunAdapter", existing.FakeListenElementAdapter
    )
    monkeypatch.setattr(host_run, "_teaches_with_agent", lambda **_kwargs: False)
    return app


def _content(text: str) -> RunMarkdownFlowDTO:
    return RunMarkdownFlowDTO(
        outline_bid="lesson",
        generated_block_bid="block",
        type=GeneratedType.CONTENT,
        content=text,
    )


def _timed_events(stream: object) -> list[tuple[float, dict]]:
    started = time.monotonic()
    timed = []
    for chunk in stream:
        received_at = time.monotonic() - started
        timed.extend(
            (received_at, event) for event in existing._parse_sse_events([chunk])
        )
    return timed


def test_events_are_forwarded_without_waiting_for_the_heartbeat_interval(
    stream_app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream_app.config["SSE_HEARTBEAT_INTERVAL"] = 0.5
    released = threading.Event()

    def produce(**_kwargs: object) -> object:
        yield _content("first")
        # Let the consumer find the queue empty and start waiting first.
        assert released.wait(2)
        yield _content("second")

    monkeypatch.setattr(host_run, "_lesson_events", produce)
    stream = host_run.run_script(stream_app, "course", "lesson", "learner")

    first = existing._parse_sse_events([next(stream)])[0]
    assert first["type"] == "element"
    timer = threading.Timer(0.05, released.set)
    timer.start()
    started = time.monotonic()
    second = existing._parse_sse_events([next(stream)])[0]
    elapsed = time.monotonic() - started
    timer.join()
    rest = existing._parse_sse_events(list(stream))

    assert second["type"] == "element"
    # The old loop slept a whole heartbeat interval (0.5s) before re-reading.
    assert elapsed < 0.3
    assert [event["type"] for event in rest] == ["done"]


def test_heartbeats_fire_only_after_an_idle_interval(
    stream_app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    interval = 0.1
    stream_app.config["SSE_HEARTBEAT_INTERVAL"] = interval

    def produce(**_kwargs: object) -> object:
        # Steady output faster than the interval never needs a heartbeat.
        for index in range(5):
            yield _content(f"chunk-{index}")
            time.sleep(interval / 4)
        # A quiet stretch of a few intervals is covered by heartbeats.
        time.sleep(interval * 3.5)
        yield _content("after-idle")

    monkeypatch.setattr(host_run, "_lesson_events", produce)
    timed = _timed_events(
        host_run.run_script(stream_app, "course", "lesson", "learner")
    )
    types = [event["type"] for _, event in timed]

    first_heartbeat = types.index("heartbeat")
    assert types[:first_heartbeat] == ["element"] * 5
    heartbeat_times = [at for at, event in timed if event["type"] == "heartbeat"]
    assert 2 <= len(heartbeat_times) <= 4
    last_chunk_at = timed[first_heartbeat - 1][0]
    assert heartbeat_times[0] - last_chunk_at >= interval * 0.9
    gaps = [later - earlier for earlier, later in itertools.pairwise(heartbeat_times)]
    assert all(gap >= interval * 0.9 for gap in gaps)
    assert types[-2:] == ["element", "done"]


def test_disabled_heartbeat_still_streams_without_heartbeat_events(
    stream_app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    def produce(**_kwargs: object) -> object:
        yield _content("first")
        time.sleep(0.05)
        yield _content("second")

    monkeypatch.setattr(host_run, "_lesson_events", produce)
    timed = _timed_events(
        host_run.run_script(stream_app, "course", "lesson", "learner")
    )

    assert [event["type"] for _, event in timed] == ["element", "element", "done"]
    assert timed[-1][0] < 0.5
