"""Forward queued events immediately and time heartbeats from the last chunk.

The consumer's clock and queue are replaced so every timing state is set up
explicitly: a queue read only times out while the producer is parked on a gate,
and a timeout advances the fake clock by exactly the requested wait.
"""

import queue
import threading
import time
from types import SimpleNamespace

import pytest
from flaskr.service.learn.host import run as host_run
from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO

from . import test_runscript_v2_lock as existing


class FakeTime:
    """Stand-in for the ``time`` module whose monotonic clock the test moves."""

    def __init__(self) -> None:
        """Start the monotonic clock at zero."""
        self.now = 0.0
        self.time = time.time

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        message = f"the consumer loop must not sleep ({seconds}s)"
        raise AssertionError(message)


class GatedProducer:
    """Yields chunks, parking on a gate between them until the test opens it."""

    def __init__(self, *texts: str) -> None:
        """Create one gate between each pair of consecutive chunks."""
        self.texts = texts
        self.gates = [threading.Event() for _ in texts[1:]]
        # Set only while every yielded chunk is queued and the producer waits.
        self.parked = threading.Event()

    def release(self, index: int) -> None:
        self.parked.clear()
        self.gates[index].set()

    def __call__(self, **_kwargs: object) -> object:
        for index, text in enumerate(self.texts):
            if index:
                # Code after a yield runs only once the host has queued that item.
                self.parked.set()
                assert self.gates[index - 1].wait(5)
            yield RunMarkdownFlowDTO(
                outline_bid="lesson",
                generated_block_bid="block",
                type=GeneratedType.CONTENT,
                content=text,
            )


class ControlledQueue(queue.SimpleQueue):
    """Queue whose blocking reads time out only while the producer is parked."""

    def __init__(self, clock: FakeTime, producer: GatedProducer) -> None:
        """Bind the fake clock and the producer whose parking state is checked."""
        self.clock = clock
        self.producer = producer
        self.simulated_waits: list[float] = []
        self.woken_waits: list[float] = []
        self.on_wait = None
        self.on_timeout = None

    def get(self, block: bool = True, timeout: float | None = None) -> object:
        try:
            return super().get(block=False)
        except queue.Empty:
            if not block:
                raise
        if self.on_wait is not None:
            on_wait, self.on_wait = self.on_wait, None
            on_wait()
        while True:
            try:
                item = super().get(timeout=0.01)
            except queue.Empty:
                if self.producer.parked.is_set() and self.empty():
                    self.simulated_waits.append(timeout)
                    self.clock.now += timeout
                    if self.on_timeout is not None:
                        self.on_timeout()
                    raise
                continue
            self.woken_waits.append(timeout)
            return item


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> object:
    app = existing._make_test_app()
    lock = existing.FakeLock([True])
    monkeypatch.setattr(host_run, "cache_provider", existing.FakeCacheProvider(lock))
    monkeypatch.setattr(
        host_run, "ListenElementRunAdapter", existing.FakeListenElementAdapter
    )
    monkeypatch.setattr(host_run, "_teaches_with_agent", lambda **_kwargs: False)
    clock = FakeTime()
    monkeypatch.setattr(host_run, "time", clock)

    def start(producer: GatedProducer, heartbeat_interval: float) -> object:
        app.config["SSE_HEARTBEAT_INTERVAL"] = heartbeat_interval
        state = SimpleNamespace(clock=clock, queue=None)

        def make_queue() -> ControlledQueue:
            state.queue = ControlledQueue(clock, producer)
            return state.queue

        monkeypatch.setattr(
            host_run,
            "queue",
            SimpleNamespace(SimpleQueue=make_queue, Empty=queue.Empty),
        )
        monkeypatch.setattr(host_run, "_lesson_events", producer)
        state.stream = host_run.run_script(app, "course", "lesson", "learner")
        return state

    return start


def _next_event(stream: object) -> dict:
    return existing._parse_sse_events([next(stream)])[0]


def _event_kinds(chunks: list) -> list[str]:
    return [event["type"] for event in existing._parse_sse_events(chunks)]


def test_event_wakes_the_waiting_consumer_without_a_heartbeat_sleep(
    harness: object,
) -> None:
    producer = GatedProducer("first", "second")
    run = harness(producer, heartbeat_interval=10)

    assert _next_event(run.stream)["type"] == "element"
    # Open the gate only once the consumer is blocked on an empty queue.
    run.queue.on_wait = lambda: producer.release(0)

    assert _next_event(run.stream)["type"] == "element"
    assert run.queue.woken_waits == [10]
    assert run.queue.simulated_waits == []
    assert _event_kinds(list(run.stream)) == ["done"]


def test_heartbeat_deadline_restarts_after_each_chunk(harness: object) -> None:
    producer = GatedProducer("first", "second", "third")
    run = harness(producer, heartbeat_interval=10)

    assert _next_event(run.stream)["type"] == "element"
    run.clock.now = 4.0
    # Sent at t=4, so the next heartbeat is due at t=14, not at t=10.
    assert _next_event(run.stream)["type"] == "heartbeat"
    assert run.queue.simulated_waits == [10.0]
    assert run.clock.now == 14.0
    assert _next_event(run.stream)["type"] == "heartbeat"
    assert run.queue.simulated_waits == [10.0, 10.0]

    producer.release(0)
    assert _next_event(run.stream)["type"] == "element"
    run.clock.now = 30.0
    assert _next_event(run.stream)["type"] == "heartbeat"
    assert run.queue.simulated_waits[-1] == 10.0

    producer.release(1)
    assert _event_kinds(list(run.stream)) == ["element", "done"]


def test_disabled_heartbeat_waits_in_bounded_reads_without_heartbeats(
    harness: object,
) -> None:
    producer = GatedProducer("first", "second")
    run = harness(producer, heartbeat_interval=0)

    assert _next_event(run.stream)["type"] == "element"
    waits = run.queue.simulated_waits

    def release_after_three_waits() -> None:
        if len(waits) == 3:
            producer.release(0)

    run.queue.on_timeout = release_after_three_waits
    assert _event_kinds(list(run.stream)) == ["element", "done"]
    assert waits == [host_run.RUN_SCRIPT_IDLE_WAIT_SECONDS] * 3
