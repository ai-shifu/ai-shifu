"""Exercise the bridge's gevent branch in a fresh interpreter.

`monkey.patch_all()` rewrites the standard library for the whole process, so this cannot run inside
the test session; `test_bridge_gevent.py` runs it as a subprocess instead. Failures raise, and the
exit code is what the test asserts on.
"""

import gevent.monkey

gevent.monkey.patch_all()

import asyncio  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402

import gevent  # noqa: E402

sys.path.insert(0, ".")
from flaskr.service.learn.agent import bridge  # noqa: E402


def check_detection() -> None:
    if not bridge._gevent_patched():
        msg = "the bridge did not detect gevent, so it would take the plain-thread path"
        raise AssertionError(msg)


def check_concurrent_turns() -> None:
    """Run many turns at once, which is where a request greenlet running a loop would fail."""

    def one(n: int) -> list[str]:
        async def events() -> AsyncIterator[str]:
            for i in range(4):
                await asyncio.sleep(0.005)
                yield f"g{n}-{i}"

        return list(bridge.iter_turn(events))

    jobs = [gevent.spawn(one, n) for n in range(24)]
    gevent.joinall(jobs, timeout=60)
    failed = [j.exception for j in jobs if not j.successful()]
    if failed:
        msg = f"{len(failed)} of 24 concurrent turns failed: {failed[0]!r}"
        raise AssertionError(msg)
    for n, job in enumerate(jobs):
        expected = [f"g{n}-{i}" for i in range(4)]
        if job.value != expected:
            msg = f"crosstalk between turns: {n} produced {job.value}"
            raise AssertionError(msg)


def check_native_handoff_does_not_block_polling() -> None:
    """Contention with a native producer must not park a nonblocking queue read."""
    original_interval = sys.getswitchinterval()
    # Make the short native producer critical sections contend with the consumer
    # without relying on unrelated machine load to expose the handoff race.
    sys.setswitchinterval(0.000001)
    try:
        for batch in range(4):

            def one(n: int) -> list[tuple[int, int]]:
                async def events() -> AsyncIterator[tuple[int, int]]:
                    for index in range(bridge.BUFFER_LIMIT * 3):
                        yield n, index
                        await asyncio.sleep(0)

                return list(bridge.iter_turn(events))

            jobs = [gevent.spawn(one, n) for n in range(24)]
            gevent.joinall(jobs, timeout=5)
            try:
                for n, job in enumerate(jobs):
                    expected = [(n, index) for index in range(bridge.BUFFER_LIMIT * 3)]
                    if not job.successful() or job.value != expected:
                        msg = f"native handoff stalled or lost events in batch {batch}, turn {n}"
                        raise AssertionError(msg)
                if bridge._InFlight.count != 0:
                    msg_0 = "completed turns retained admission slots"
                    raise AssertionError(msg_0)
            finally:
                gevent.killall([job for job in jobs if not job.ready()], timeout=3)
    finally:
        sys.setswitchinterval(original_interval)


def check_uses_the_pool() -> None:
    pool = bridge._GeventPool.instance
    if pool is None or type(pool).__module__ != "gevent.threadpool":
        msg = f"expected a gevent thread pool, got {pool!r}"
        raise AssertionError(msg)


def check_backpressure_can_resume() -> None:
    """Bound a paused producer and deliver every event when reading resumes."""
    state = {"produced": 0}

    async def events() -> AsyncIterator[int]:
        for index in range(bridge.BUFFER_LIMIT * 4):
            state["produced"] += 1
            yield index

    stream = bridge.iter_turn(events)
    try:
        first = next(stream)
        gevent.sleep(0.05)
        if state["produced"] > bridge.BUFFER_LIMIT + 2:
            msg = "a paused reader did not bound the native producer"
            raise AssertionError(msg)
        if [first, *stream] != list(range(bridge.BUFFER_LIMIT * 4)):
            msg = "resuming a paused reader lost or reordered events"
            raise AssertionError(msg)
    finally:
        stream.close()


def check_waiting_turn_cancels_and_releases_capacity() -> None:
    """Free a quiet turn's slot on disconnect and preserve immediate refusal."""
    state = {"closed": False}

    async def waiting() -> AsyncIterator[str]:
        try:
            yield "started"
            await asyncio.sleep(30)
        finally:
            state["closed"] = True

    limit = bridge.MAX_TURNS_IN_FLIGHT
    bridge.MAX_TURNS_IN_FLIGHT = 1
    stream = bridge.iter_turn(waiting)
    try:
        if next(stream) != "started":
            msg = "the waiting turn never started"
            raise AssertionError(msg)
        try:
            refused = bridge.iter_turn(waiting)
        except bridge.TurnCapacityError:
            pass
        else:
            refused.close()
            msg = "a full worker did not refuse the second turn"
            raise AssertionError(msg)
    finally:
        stream.close()
        bridge.MAX_TURNS_IN_FLIGHT = limit
    if not state["closed"] or bridge._InFlight.count != 0:
        msg = "a cancelled quiet turn retained its generator or slot"
        raise AssertionError(msg)


def check_error_releases_capacity() -> None:
    """Propagate producer errors and leave the worker able to admit turns."""

    async def events() -> AsyncIterator[str]:
        yield "before-error"
        msg = "isolated bridge failure"
        raise ValueError(msg)

    stream = bridge.iter_turn(events)
    if next(stream) != "before-error":
        msg = "the producer lost its event before failing"
        raise AssertionError(msg)
    try:
        next(stream)
    except ValueError as error:
        if str(error) != "isolated bridge failure":
            raise
    else:
        msg = "the producer error was not propagated"
        raise AssertionError(msg)
    if bridge._InFlight.count != 0:
        msg = "a failed producer retained its admission slot"
        raise AssertionError(msg)


def check_contended_admission_release() -> None:
    """Finish on a native producer while the request briefly owns the counter lock."""
    for _ in range(8):
        state = {"finish": False, "exiting": False}

        async def events(probe: dict[str, bool] = state) -> AsyncIterator[str]:
            yield "started"
            while not probe["finish"]:  # noqa: ASYNC110 -- Coordinate native-thread lock contention.
                await asyncio.sleep(0.001)
            probe["exiting"] = True

        stream = bridge.iter_turn(events)
        try:
            if next(stream) != "started":
                msg = "the contention probe never started"
                raise AssertionError(msg)
            with bridge._InFlight.lock:
                state["finish"] = True
                deadline = time.monotonic() + 2
                while not state["exiting"] and time.monotonic() < deadline:
                    gevent.sleep(0.001)
                if not state["exiting"]:
                    msg = "the contention probe never reached producer cleanup"
                    raise AssertionError(msg)
                gevent.sleep(0.01)
            reader = gevent.spawn(list, stream)
            reader.join(timeout=3)
            try:
                if not reader.successful() or reader.value != []:
                    msg = "producer cleanup stalled after admission lock contention"
                    raise AssertionError(msg)
            finally:
                reader.kill()
        finally:
            stream.close()
        if bridge._InFlight.count != 0:
            msg = "contended cleanup retained its admission slot"
            raise AssertionError(msg)


def check_close_does_not_freeze_the_hub() -> None:
    """Walk away mid-turn: joining a real thread from a greenlet would block this worker."""
    state = {"closed": False}

    async def endless() -> AsyncIterator[str]:
        try:
            while True:
                yield "x"
                await asyncio.sleep(0.01)
        finally:
            state["closed"] = True

    stream = bridge.iter_turn(endless)
    next(stream)
    started = time.monotonic()
    stream.close()
    elapsed = time.monotonic() - started
    # The point is that close() returns promptly rather than sitting out the exit timeout, which
    # is what blocking the hub would look like. The margin is deliberately wide: this runs on a
    # shared CI machine alongside the rest of the suite, and a test that goes red under load
    # teaches people to ignore red.
    if elapsed >= bridge.PRODUCER_EXIT_TIMEOUT:
        msg = f"close() took {elapsed:.3f}s, which suggests it blocked the hub"
        raise AssertionError(msg)
    deadline = time.monotonic() + 3
    while not state["closed"] and time.monotonic() < deadline:
        gevent.sleep(0.01)
    if not state["closed"]:
        msg = "the generator was never closed after the consumer walked away"
        raise AssertionError(msg)


def check_events_are_not_paced_by_the_heartbeat() -> None:
    async def ticks() -> AsyncIterator[str]:
        for _ in range(5):
            await asyncio.sleep(0.05)
            yield "tick"

    started = time.monotonic()
    out = list(bridge.iter_turn(ticks, heartbeat_interval=0.5, heartbeat=lambda: None))
    elapsed = time.monotonic() - started
    if out != ["tick"] * 5:
        msg = f"unexpected events: {out}"
        raise AssertionError(msg)
    # Five 50ms gaps, so ~0.25s of real work. Polling at the 0.5s heartbeat instead would make
    # this at least 2.5s. The threshold sits between the two rather than close to the floor: what
    # is being detected is a tenfold regression, and a tight bound would only make this flaky when
    # the machine is busy.
    if elapsed >= 2.0:
        msg = f"five 50ms events took {elapsed:.3f}s, so the heartbeat is pacing them"
        raise AssertionError(msg)


for check in (
    check_detection,
    check_concurrent_turns,
    check_native_handoff_does_not_block_polling,
    check_uses_the_pool,
    check_backpressure_can_resume,
    check_waiting_turn_cancels_and_releases_capacity,
    check_error_releases_capacity,
    check_contended_admission_release,
    check_close_does_not_freeze_the_hub,
    check_events_are_not_paced_by_the_heartbeat,
):
    check()
    print(f"ok: {check.__name__}")

print("gevent branch ok")
