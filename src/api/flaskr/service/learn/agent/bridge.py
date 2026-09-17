"""Run the agent engine's async turns from a synchronous request handler.

The engine is asyncio throughout and this project serves requests synchronously, so a turn runs on
a producer thread that owns its own event loop while the request thread reads the events it puts on
a queue.

Three things about this are not obvious, and each one was measured rather than reasoned about:

* **Under gevent, the request thread must never run an event loop.** `monkey.patch_all()` makes
  every request in a worker a greenlet on one OS thread, and asyncio tracks the running loop per OS
  thread, so the second greenlet to start one fails with "Cannot run the event loop while another
  loop is running". Twenty-four concurrent requests produced four successes and twenty 500s. Under
  gthread each request already has its own OS thread and the problem does not arise.
* **`monkey.get_original("threading", "Thread")` is not the way out.** The thread it returns still
  bootstraps through the patched `threading` module: the thread body finishes but `is_alive()`
  never goes false, so anything waiting on it waits forever. Joining a real thread from a greenlet
  also blocks the whole hub and freezes every request in that worker. `gevent.threadpool.ThreadPool`
  runs on real OS threads and yields the hub while waiting, which is what this uses instead.
* **The queue can only be polled.** `SimpleQueue.get(timeout=...)` waits in C, where gevent cannot
  patch it, so it parks the hub. Polling with the patched `time.sleep` is the only safe wait.

The polling interval is deliberately not the heartbeat interval. Sleeping a whole heartbeat when the
queue is empty adds up to that much latency to every event: measured against a model emitting an
event every 50ms, the gap between events at p95 was 0.503s with a 0.5s heartbeat and 0.060s once
polling was decoupled from it.
"""

from __future__ import annotations

import asyncio
import contextlib
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

# How often the consumer looks at the queue. Small enough that it does not add meaningfully to the
# latency of an event, large enough not to spin.
POLL_INTERVAL = 0.01
# One pool per worker process, sized to the number of engine turns that worker may run at once.
GEVENT_POOL_SIZE = 64
# How long to wait for the producer to notice a stop request before giving up on it.
PRODUCER_EXIT_TIMEOUT = 2.0


class _GeventPool:
    """Holds the one pool this worker process uses, so `_spawn` needs no global statement."""

    lock = threading.Lock()
    instance: Any = None


def _gevent_patched() -> bool:
    """Whether this process is running under gevent's monkey patching."""
    try:
        from gevent import monkey
    except ImportError:
        return False
    return bool(monkey.is_module_patched("threading"))


def _spawn(fn: Callable[[], None]) -> Callable[[], bool]:
    """Start `fn` on a real OS thread and return a callable reporting whether it is still running.

    Under gevent this has to go through `gevent.threadpool`; see the module docstring for why a
    plain thread, patched or unpatched, is not an option there.
    """
    if _gevent_patched():
        with _GeventPool.lock:
            if _GeventPool.instance is None:
                from gevent.threadpool import ThreadPool

                _GeventPool.instance = ThreadPool(GEVENT_POOL_SIZE)
        handle = _GeventPool.instance.spawn(fn)
        return lambda: not handle.ready()

    thread = threading.Thread(target=fn, daemon=True, name="mdf2-engine-turn")
    thread.start()
    return thread.is_alive


@dataclass
class _Stop:
    """A plain mutable flag rather than `threading.Event`.

    Under gevent `threading.Event` is the greenlet version, whose behaviour across a real pool
    thread would need verifying; a bare boolean needs no such argument.
    """

    requested: bool = False


@dataclass
class TurnStream:
    """One engine turn, consumed as a synchronous iterator.

    `heartbeat` is what the host emits while the model is quiet; returning `None` from it suppresses
    the heartbeat entirely.
    """

    events: queue.SimpleQueue = field(default_factory=queue.SimpleQueue)
    stop: _Stop = field(default_factory=_Stop)
    is_running: Callable[[], bool] | None = None
    error: BaseException | None = None


_DONE = object()


def iter_turn(
    make_events: Callable[[], AsyncIterator[Any]],
    *,
    heartbeat_interval: float = 0.5,
    heartbeat: Callable[[], Any] | None = None,
) -> Iterator[Any]:
    """Run one engine turn on a producer thread and yield its events as they arrive.

    `make_events` is called on the producer thread and must return the async iterator for the turn,
    so that the engine, its session and the generator are all created on the loop that will drive
    them. Closing this iterator early -- a learner leaving the page -- asks the producer to stop and
    waits briefly for it to unwind rather than abandoning it.
    """
    stream = TurnStream()

    def produce() -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            agen = make_events()

            async def pump() -> None:
                try:
                    async for event in agen:
                        stream.events.put(event)
                        if stream.stop.requested:
                            break
                finally:
                    # Unwind the engine and whatever it holds open -- the gateway's stream, and the
                    # provider connection under that -- before the loop goes away.
                    aclose = getattr(agen, "aclose", None)
                    if aclose is not None:
                        await aclose()

            loop.run_until_complete(pump())
        except (
            BaseException
        ) as exc:  # reported to the consumer, which decides what to do
            stream.error = exc
        finally:
            # Nothing useful to do if teardown itself fails; the loop is closed either way.
            with contextlib.suppress(Exception):
                loop.run_until_complete(loop.shutdown_asyncgens())
            asyncio.set_event_loop(None)
            loop.close()
            stream.events.put(_DONE)

    stream.is_running = _spawn(produce)
    last_heartbeat = time.monotonic()
    try:
        while True:
            try:
                event = stream.events.get_nowait()
            except queue.Empty:
                if not stream.is_running() and stream.events.empty():
                    break
                # Poll far more often than the heartbeat: sleeping a whole heartbeat here would add
                # up to that much latency to every event the model produces.
                time.sleep(POLL_INTERVAL)
                now = time.monotonic()
                if heartbeat is not None and now - last_heartbeat >= heartbeat_interval:
                    last_heartbeat = now
                    beat = heartbeat()
                    if beat is not None:
                        yield beat
                continue
            if event is _DONE:
                break
            last_heartbeat = time.monotonic()
            yield event
    finally:
        stream.stop.requested = True
        _drain_until_stopped(stream)
    if stream.error is not None:
        raise stream.error


def _drain_until_stopped(stream: TurnStream) -> None:
    """Let the producer notice the stop request and unwind, without blocking the hub.

    The queue is drained while waiting: a producer parked on `put` into a full queue would never
    reach its own cleanup. Waiting is bounded -- a wedged producer must not hold the request open.
    """
    if stream.is_running is None:
        return
    deadline = time.monotonic() + PRODUCER_EXIT_TIMEOUT
    while stream.is_running() and time.monotonic() < deadline:
        try:
            while True:
                stream.events.get_nowait()
        except queue.Empty:
            pass
        time.sleep(POLL_INTERVAL)
