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


def check_uses_the_pool() -> None:
    pool = bridge._GeventPool.instance
    if pool is None or type(pool).__module__ != "gevent.threadpool":
        msg = f"expected a gevent thread pool, got {pool!r}"
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
    check_uses_the_pool,
    check_close_does_not_freeze_the_hub,
    check_events_are_not_paced_by_the_heartbeat,
):
    check()
    print(f"ok: {check.__name__}")

print("gevent branch ok")
