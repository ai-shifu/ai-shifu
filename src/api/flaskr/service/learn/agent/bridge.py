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
# How many events may sit unread before the producer waits. A streaming client that reads slowly
# pauses the consumer between events, and without a ceiling a fast turn would keep queueing into
# memory for as long as it runs.
BUFFER_LIMIT = 64
# How many turns one worker process may have in flight. Beyond this a turn is refused rather than
# queued: `ThreadPool.spawn` waits for a slot -- its own docstring says so, and a pool of two
# running two-second tasks makes every third spawn wait the full two seconds -- and a request
# parked inside `spawn` has not started its stream, so the learner sees a connection that simply
# hangs, with no content and no error.
MAX_TURNS_IN_FLIGHT = GEVENT_POOL_SIZE
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


class _InFlight:
    """Counts the turns this worker process is running, so admission can be refused."""

    lock = threading.Lock()
    count = 0

    @classmethod
    def admit(cls) -> None:
        """Take a slot, or refuse when the worker is already full."""
        with cls.lock:
            if cls.count >= MAX_TURNS_IN_FLIGHT:
                msg = f"this worker is already running {cls.count} agent turns"
                raise TurnCapacityError(msg)
            cls.count += 1

    @classmethod
    def release(cls) -> None:
        """Give the slot back."""
        with cls.lock:
            cls.count = max(0, cls.count - 1)


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


class TurnCapacityError(RuntimeError):
    """Raised when this worker is already running as many turns as it can.

    The host should tell the learner the system is busy and let them retry, rather than holding the
    request open behind a slot that may not free for minutes.
    """


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
    # Set once the producer's loop and task exist, so the consumer can interrupt a turn that is
    # waiting on the model rather than only asking it to stop at its next event.
    cancel: Callable[[], None] | None = None


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

    Raises `TurnCapacityError` straight away when the worker is full. This function is deliberately
    not a generator: a generator body does not run until the first `next()`, and by then the caller
    has usually committed to a streaming response and can no longer turn a refusal into one.
    """
    _InFlight.admit()
    try:
        return _iter_turn(
            make_events, heartbeat_interval=heartbeat_interval, heartbeat=heartbeat
        )
    except BaseException:
        _InFlight.release()
        raise


def _iter_turn(
    make_events: Callable[[], AsyncIterator[Any]],
    *,
    heartbeat_interval: float,
    heartbeat: Callable[[], Any] | None,
) -> Iterator[Any]:
    """Drive one turn whose slot the caller has already taken."""
    stream = TurnStream()

    def produce() -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            agen = make_events()

            async def pump() -> None:
                try:
                    async for event in agen:
                        # Back off while the consumer is behind. `asyncio.sleep` runs on this
                        # producer's own loop, so the wait needs none of gevent's primitives, and
                        # it gives the turn somewhere to notice a stop request.

                        # waited for here changes on the consumer's OS thread, and an
                        # `asyncio.Event` is not safe to set from one.
                        while (  # noqa: ASYNC110
                            stream.events.qsize() >= BUFFER_LIMIT
                            and not stream.stop.requested
                        ):
                            await asyncio.sleep(POLL_INTERVAL)
                        if stream.stop.requested:
                            break
                        stream.events.put(event)
                finally:
                    # Unwind the engine and whatever it holds open -- the gateway's stream, and the
                    # provider connection under that -- before the loop goes away.
                    aclose = getattr(agen, "aclose", None)
                    if aclose is not None:
                        await aclose()

            task = loop.create_task(pump())
            # Cancelling through the loop is what reaches a turn parked on the model. Asking it to
            # stop is not enough by itself: `async for` only comes back around when the next event
            # arrives, so a turn awaiting a provider that never answers would hold its thread.
            stream.cancel = lambda: loop.call_soon_threadsafe(task.cancel)
            if stream.stop.requested:
                task.cancel()
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass  # the consumer walked away; the generator was closed on the way out
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
            _InFlight.release()
            stream.events.put(_DONE)

    try:
        stream.is_running = _spawn(produce)
    except BaseException:
        _InFlight.release()
        raise
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
        _request_cancel(stream)
        _drain_until_stopped(stream)
    if stream.error is not None:
        raise stream.error


def _request_cancel(stream: TurnStream) -> None:
    """Interrupt a turn still waiting on the model, if there is one left to interrupt.

    A turn that finished on its own has already closed its loop, and scheduling onto a closed loop
    raises; there is nothing to cancel in that case anyway.
    """
    if stream.cancel is None or stream.is_running is None or not stream.is_running():
        return
    with contextlib.suppress(RuntimeError):
        stream.cancel()


def _drain_until_stopped(stream: TurnStream) -> None:
    """Let the producer notice the stop request and unwind, without blocking the hub.

    The queue is drained while waiting, so a producer backing off on a full buffer sees room and can
    reach its own cleanup. Waiting is bounded: a turn blocked inside a synchronous provider read
    cannot be interrupted until that read returns, and must not hold the request open meanwhile.
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
