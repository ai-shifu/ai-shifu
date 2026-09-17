"""Tests for running an async engine turn from a synchronous request handler.

These use plain async generators rather than the engine: what is under test is the bridge's own
behaviour -- ordering, latency, cleanup on early exit, and error propagation -- not the engine's.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import pytest
from flaskr.service.learn.agent import bridge

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def test_events_arrive_in_order() -> None:
    async def events() -> AsyncIterator[int]:
        for i in range(5):
            yield i

    assert list(bridge.iter_turn(events)) == [0, 1, 2, 3, 4]


def test_an_event_is_not_held_for_a_whole_heartbeat() -> None:
    """The regression this bridge exists for: polling must not be tied to the heartbeat interval.

    Copying the 1.0 consumer loop, which sleeps a full heartbeat on an empty queue, added up to that
    much latency to every event.
    """

    async def events() -> AsyncIterator[str]:
        for _ in range(3):
            await asyncio.sleep(0.05)
            yield "tick"

    started = time.monotonic()
    out = list(bridge.iter_turn(events, heartbeat_interval=0.5, heartbeat=lambda: None))
    elapsed = time.monotonic() - started

    assert out == ["tick", "tick", "tick"]
    # Three 50ms gaps. A heartbeat-paced poll would make this at least 1.5s.
    assert elapsed < 0.8, elapsed


def test_a_heartbeat_is_emitted_while_the_model_is_quiet() -> None:
    async def events() -> AsyncIterator[str]:
        await asyncio.sleep(0.25)
        yield "late"

    out = list(
        bridge.iter_turn(events, heartbeat_interval=0.05, heartbeat=lambda: "beat")
    )
    assert "late" in out
    assert out.count("beat") >= 2
    assert out[-1] == "late"


def test_no_heartbeat_when_the_host_does_not_want_one() -> None:
    async def events() -> AsyncIterator[str]:
        await asyncio.sleep(0.15)
        yield "only"

    assert list(bridge.iter_turn(events, heartbeat_interval=0.01)) == ["only"]


def test_an_error_in_the_turn_reaches_the_caller() -> None:
    async def events() -> AsyncIterator[int]:
        yield 1
        msg = "model exploded"
        raise RuntimeError(msg)

    received: list[int] = []

    def drain() -> None:
        received.extend(bridge.iter_turn(events))

    with pytest.raises(RuntimeError, match="model exploded"):
        drain()
    assert received == [1]


# -- cleanup -----------------------------------------------------------------------------


def test_abandoning_the_stream_unwinds_the_turn() -> None:
    """A learner closing the page: the producer must stop and the generator must be closed.

    Without this the engine keeps running, and the provider connection under it stays open.
    """
    state = {"closed": False, "produced": 0}

    async def events() -> AsyncIterator[int]:
        try:
            while True:
                state["produced"] += 1
                yield state["produced"]
                await asyncio.sleep(0.01)
        finally:
            state["closed"] = True

    stream = bridge.iter_turn(events)
    assert next(stream) == 1
    stream.close()  # the consumer walks away

    deadline = time.monotonic() + 3
    while not state["closed"] and time.monotonic() < deadline:
        time.sleep(0.01)
    assert state["closed"] is True
    produced_at_stop = state["produced"]

    time.sleep(0.2)
    assert state["produced"] == produced_at_stop  # and it really stopped


def test_a_turn_that_ends_on_its_own_closes_its_generator_too() -> None:
    state = {"closed": False}

    async def events() -> AsyncIterator[int]:
        try:
            yield 1
        finally:
            state["closed"] = True

    assert list(bridge.iter_turn(events)) == [1]
    deadline = time.monotonic() + 3
    while not state["closed"] and time.monotonic() < deadline:
        time.sleep(0.01)
    assert state["closed"] is True


def test_the_consumer_does_not_wait_forever_on_a_wedged_producer() -> None:
    """A producer that ignores the stop request must not hold the request thread open."""

    async def events() -> AsyncIterator[int]:
        yield 1
        await asyncio.sleep(30)  # never checks back in
        yield 2

    stream = bridge.iter_turn(events)
    assert next(stream) == 1
    started = time.monotonic()
    stream.close()
    elapsed = time.monotonic() - started
    assert elapsed < bridge.PRODUCER_EXIT_TIMEOUT + 1, elapsed


# -- concurrency -------------------------------------------------------------------------


def test_many_turns_run_at_once_without_crosstalk() -> None:
    """Each turn owns its loop and queue; nothing is shared but the thread pool."""
    import threading

    results: dict[int, list[str]] = {}

    def run(n: int) -> None:
        async def events() -> AsyncIterator[str]:
            for i in range(4):
                await asyncio.sleep(0.005)
                yield f"turn{n}-{i}"

        results[n] = list(bridge.iter_turn(events))

    threads = [threading.Thread(target=run, args=(n,)) for n in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == 12
    for n, out in results.items():
        assert out == [f"turn{n}-{i}" for i in range(4)], (n, out)


# -- with the real engine ----------------------------------------------------------------


def test_a_real_engine_turn_runs_through_the_bridge() -> None:
    """The whole point: an asyncio engine turn consumed from synchronous code.

    Everything the engine touches -- the session, the agent run, the async generator -- is created
    on the producer thread, because that is the only thread with a loop to run them on.
    """
    import json

    from flaskr.service.learn.agent.engine import (
        ContentDelta,
        Engine,
        InteractionRequest,
        TurnDone,
    )
    from pydantic_ai.models.function import DeltaToolCall, FunctionModel

    spec = {
        "type": "single",
        "prompt": "How do you feel?",
        "options": [{"display": "Good", "value": "good"}],
        "variable": "feeling",
    }

    async def model(
        _messages: object, _info: object
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        yield "Hello learner.\n"
        yield {
            0: DeltaToolCall(
                name="interact", tool_call_id="q1", json_args=json.dumps(spec)
            )
        }

    def make_events() -> AsyncIterator[object]:
        engine = Engine(FunctionModel(stream_function=model))
        session = engine.run_turn  # bound below, after the session exists

        async def run() -> AsyncIterator[object]:
            s = await engine.new_session("Ask the learner how they feel.")
            async for event in session(s):
                yield event

        return run()

    events = list(bridge.iter_turn(make_events))
    kinds = [type(e).__name__ for e in events]
    assert "ContentDelta" in kinds
    assert any(isinstance(e, ContentDelta) and "Hello" in e.text for e in events)
    request = next(e for e in events if isinstance(e, InteractionRequest))
    assert request.spec.variable == "feeling"
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "interaction"
