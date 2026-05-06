"""Tests for the in-memory PubSub additions in flaskr.common.cache_provider."""

from __future__ import annotations

import threading

import pytest

from flaskr.common.cache_provider import InMemoryCacheProvider


@pytest.fixture
def provider() -> InMemoryCacheProvider:
    return InMemoryCacheProvider()


def test_subscribe_then_publish_delivers_message(
    provider: InMemoryCacheProvider,
) -> None:
    pubsub = provider.pubsub()
    try:
        pubsub.subscribe("ch")
        delivered_count = provider.publish("ch", "hello")
        assert delivered_count == 1
        msg = pubsub.get_message(timeout=0.5)
        assert msg == b"hello"
    finally:
        pubsub.close()


def test_publish_before_subscribe_is_dropped(provider: InMemoryCacheProvider) -> None:
    # PubSub is not durable; messages published before subscribe are lost.
    delivered_count = provider.publish("ch", "early")
    assert delivered_count == 0
    pubsub = provider.pubsub()
    try:
        pubsub.subscribe("ch")
        msg = pubsub.get_message(timeout=0.05)
        assert msg is None
    finally:
        pubsub.close()


def test_multiple_subscribers_each_receive_the_message(
    provider: InMemoryCacheProvider,
) -> None:
    a = provider.pubsub()
    b = provider.pubsub()
    try:
        a.subscribe("ch")
        b.subscribe("ch")
        delivered_count = provider.publish("ch", "fanout")
        assert delivered_count == 2
        assert a.get_message(timeout=0.5) == b"fanout"
        assert b.get_message(timeout=0.5) == b"fanout"
    finally:
        a.close()
        b.close()


def test_close_unsubscribes(provider: InMemoryCacheProvider) -> None:
    pubsub = provider.pubsub()
    pubsub.subscribe("ch")
    pubsub.close()
    delivered_count = provider.publish("ch", "after-close")
    assert delivered_count == 0


def test_get_message_returns_none_on_timeout(
    provider: InMemoryCacheProvider,
) -> None:
    pubsub = provider.pubsub()
    try:
        pubsub.subscribe("ch")
        msg = pubsub.get_message(timeout=0.05)
        assert msg is None
    finally:
        pubsub.close()


def test_publish_wakes_blocked_subscriber(
    provider: InMemoryCacheProvider,
) -> None:
    pubsub = provider.pubsub()
    pubsub.subscribe("ch")
    received: list[bytes | None] = []
    ready = threading.Event()

    def waiter() -> None:
        ready.set()
        received.append(pubsub.get_message(timeout=2.0))

    thread = threading.Thread(target=waiter)
    thread.start()
    ready.wait(timeout=1.0)
    # Give the waiter a moment to actually enter cond.wait().
    threading.Event().wait(0.05)
    provider.publish("ch", "wake")
    thread.join(timeout=2.0)
    pubsub.close()
    assert received == [b"wake"]


def test_publish_uses_encode_for_non_string(
    provider: InMemoryCacheProvider,
) -> None:
    pubsub = provider.pubsub()
    try:
        pubsub.subscribe("ch")
        provider.publish("ch", 42)
        assert pubsub.get_message(timeout=0.5) == b"42"
    finally:
        pubsub.close()
