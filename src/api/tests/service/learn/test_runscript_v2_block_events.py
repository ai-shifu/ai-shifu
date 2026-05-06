"""Tests for block-commit event signalling used to align ask commits with main blocks."""

from __future__ import annotations

import threading

import pytest
from flask import Flask

from flaskr.common.cache_provider import InMemoryCacheProvider
from flaskr.service.learn import runscript_v2
from flaskr.service.learn.runscript_v2 import (
    ANCHOR_WAIT_TIMEOUT_SECONDS,
    BLOCK_EVENT_ABORTED,
    BLOCK_EVENT_COMMITTED,
    BLOCK_EVENT_KEY_TTL_SECONDS,
    _get_block_event_channel,
    _publish_block_event,
    _wait_block_event,
)


@pytest.fixture
def app() -> Flask:
    flask_app = Flask(__name__)
    flask_app.config["REDIS_KEY_PREFIX"] = "test"
    return flask_app


@pytest.fixture
def cache(monkeypatch: pytest.MonkeyPatch) -> InMemoryCacheProvider:
    cache = InMemoryCacheProvider()
    monkeypatch.setattr(runscript_v2, "cache_provider", cache)
    return cache


def test_publish_sets_cache_key_and_publishes(
    app: Flask, cache: InMemoryCacheProvider
) -> None:
    bid = "block-1"
    channel = _get_block_event_channel(app, bid)

    pubsub = cache.pubsub()
    try:
        pubsub.subscribe(channel)
        _publish_block_event(app, bid, BLOCK_EVENT_COMMITTED)
        # Fast-path key written.
        assert cache.get(channel) == BLOCK_EVENT_COMMITTED.encode("utf-8")
        # And subscriber received the event.
        assert pubsub.get_message(timeout=0.5) == b"committed"
    finally:
        pubsub.close()


def test_wait_returns_committed_via_fast_path(
    app: Flask, cache: InMemoryCacheProvider
) -> None:
    bid = "block-fast"
    cache.setex(
        _get_block_event_channel(app, bid),
        BLOCK_EVENT_KEY_TTL_SECONDS,
        BLOCK_EVENT_COMMITTED,
    )
    outcome = _wait_block_event(app, bid, timeout_seconds=0.05)
    assert outcome == BLOCK_EVENT_COMMITTED


def test_wait_returns_aborted_via_fast_path(
    app: Flask, cache: InMemoryCacheProvider
) -> None:
    bid = "block-aborted"
    cache.setex(
        _get_block_event_channel(app, bid),
        BLOCK_EVENT_KEY_TTL_SECONDS,
        BLOCK_EVENT_ABORTED,
    )
    outcome = _wait_block_event(app, bid, timeout_seconds=0.05)
    assert outcome == BLOCK_EVENT_ABORTED


def test_wait_returns_timeout_when_no_signal(
    app: Flask, cache: InMemoryCacheProvider
) -> None:
    outcome = _wait_block_event(app, "block-quiet", timeout_seconds=0.05)
    assert outcome == "timeout"


def test_wait_unblocks_when_publish_arrives(
    app: Flask, cache: InMemoryCacheProvider
) -> None:
    bid = "block-async"
    outcomes: list[str] = []
    waiter_started = threading.Event()

    def waiter() -> None:
        waiter_started.set()
        outcomes.append(_wait_block_event(app, bid, timeout_seconds=2.0))

    thread = threading.Thread(target=waiter)
    thread.start()
    waiter_started.wait(timeout=1.0)
    threading.Event().wait(0.05)  # let waiter enter pubsub.get_message
    _publish_block_event(app, bid, BLOCK_EVENT_COMMITTED)
    thread.join(timeout=2.0)
    assert outcomes == [BLOCK_EVENT_COMMITTED]


def test_wait_with_empty_bid_returns_committed(
    app: Flask, cache: InMemoryCacheProvider
) -> None:
    # A missing anchor bid is treated as "no waiter" — the ask may proceed.
    assert _wait_block_event(app, "", timeout_seconds=0.05) == BLOCK_EVENT_COMMITTED


def test_publish_with_empty_bid_is_noop(
    app: Flask, cache: InMemoryCacheProvider
) -> None:
    _publish_block_event(app, "", BLOCK_EVENT_COMMITTED)
    # Nothing was written to the cache; nothing to assert beyond no exception.


def test_anchor_wait_timeout_is_within_run_budget() -> None:
    # Ensure the ask wait window stays well below the main run timeout so
    # ask requests cannot hold their semaphore slot for an entire run.
    assert ANCHOR_WAIT_TIMEOUT_SECONDS < runscript_v2.RUN_SCRIPT_TIMEOUT_SECONDS
