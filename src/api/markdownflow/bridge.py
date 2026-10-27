"""Run the agent engine's async turns from a synchronous request handler.

The engine is asyncio throughout and this project serves requests synchronously on gunicorn
`gthread` workers, so a turn runs on a producer thread that owns its own event loop while the
request thread reads the events it puts on a thread-safe queue. Keeping the loop off the request
thread means the request never has to run, share or tear down an event loop itself, and closing the
stream early can ask the producer to unwind on its own loop.

The consumer only polls the queue with nonblocking reads, so between events it can emit heartbeats
and notice that the producer has finished.

The polling interval is deliberately not the heartbeat interval. Sleeping a whole heartbeat when the
queue is empty adds up to that much latency to every event: measured against a model emitting an
event every 50ms, the gap between events at p95 was 0.503s with a 0.5s heartbeat and 0.060s once
polling was decoupled from it.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
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
# How many events may sit unread before the producer waits. A streaming client that reads slowly
# pauses the consumer between events, and without a ceiling a fast turn would keep queueing into
# memory for as long as it runs.
BUFFER_LIMIT = 64
# How many turns one worker process may have in flight. Beyond this a turn is refused rather than
# queued: a request parked waiting for a slot has not started its stream, so the learner would see
# a connection that simply hangs, with no content and no error.
MAX_TURNS_IN_FLIGHT = 64
# How long to wait for the producer to notice a stop request before giving up on it.
PRODUCER_EXIT_TIMEOUT = 2.0


class _InFlight:
    """Counts the turns this worker process is running, so admission can be refused."""

    # Only short counter updates run while held; never wait for a turn or do I/O.
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
    """Start `fn` on a daemon thread and return a callable reporting whether it still runs."""
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
    """A plain mutable flag the consumer sets and the producer reads between events.

    Assigning a boolean is atomic, so nothing heavier than this is needed.
    """

    requested: bool = False


_turn_stop: contextvars.ContextVar[_Stop | None] = contextvars.ContextVar(
    "mdf2_turn_stop", default=None
)


def turn_stop_requested() -> bool:
    """Let the synchronous gateway wait notice a disconnected turn."""
    stop = _turn_stop.get()
    return bool(stop is not None and stop.requested)


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
        stop_token = _turn_stop.set(stream.stop)
        try:
            asyncio.set_event_loop(loop)
            agen = make_events()

            async def pump() -> None:
                try:
                    async for event in agen:
                        # Back off while the consumer is behind. `asyncio.sleep` runs on this
                        # producer's own loop and gives the turn somewhere to notice a stop
                        # request. The queue size waited for here changes on the consumer's OS
                        # thread, and an `asyncio.Event` is not safe to set from one.
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
            _turn_stop.reset(stop_token)
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
    """Let the producer notice the stop request and unwind, without waiting on it indefinitely.

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
