"""A running turn marks its block live, then ended; a missing mark proves nothing."""

from __future__ import annotations

import threading

import pytest
from flaskr.common.cache_provider import CacheUnavailableError, InMemoryCacheProvider
from flaskr.service.learn.agent import turn_liveness


@pytest.fixture(name="shared_cache")
def fixture_shared_cache(monkeypatch: pytest.MonkeyPatch) -> InMemoryCacheProvider:
    cache = InMemoryCacheProvider()
    monkeypatch.setattr(turn_liveness, "redis_cache", cache)
    return cache


@pytest.mark.usefixtures("shared_cache")
def test_the_block_is_live_while_the_turn_runs_and_ended_after(app: object) -> None:
    assert turn_liveness.turn_is_live(app, "B1") is None
    with turn_liveness.hold_turn_liveness(app, "B1"):
        assert turn_liveness.turn_is_live(app, "B1") is True
        assert turn_liveness.turn_is_live(app, "B2") is None
    assert turn_liveness.turn_is_live(app, "B1") is False


@pytest.mark.usefixtures("shared_cache")
def test_a_turn_that_raises_still_clears_its_mark(app: object) -> None:
    with (
        pytest.raises(GeneratorExit),
        turn_liveness.hold_turn_liveness(app, "B1"),
    ):
        raise GeneratorExit
    assert turn_liveness.turn_is_live(app, "B1") is False


def test_the_mark_is_refreshed_while_the_turn_runs(
    app: object, shared_cache: InMemoryCacheProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(turn_liveness, "TURN_LIVENESS_REFRESH_SECONDS", 0.01)
    refreshed = threading.Event()
    real_setex = shared_cache.setex
    calls = 0

    def counting_setex(key: str, ttl: int, value: object) -> object:
        nonlocal calls
        calls += 1
        if calls >= 3:
            refreshed.set()
        return real_setex(key, ttl, value)

    monkeypatch.setattr(shared_cache, "setex", counting_setex)
    with turn_liveness.hold_turn_liveness(app, "B1"):
        assert refreshed.wait(2)
    settled = calls
    # The refresher stops with the turn: nothing marks the block live again.
    assert not refreshed.wait(0.05) or calls == settled
    assert turn_liveness.turn_is_live(app, "B1") is False


class _NoRedis:
    def setex(self, *_args: object) -> object:
        raise CacheUnavailableError

    def get(self, *_args: object) -> object:
        raise CacheUnavailableError

    def delete(self, *_args: object) -> int:
        raise CacheUnavailableError


def test_without_redis_the_turn_runs_and_liveness_is_unknown(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(turn_liveness, "redis_cache", _NoRedis())
    monkeypatch.setattr(turn_liveness, "TURN_LIVENESS_REFRESH_SECONDS", 0.01)
    warnings: list[str] = []
    monkeypatch.setattr(
        app.logger, "warning", lambda msg, *args: warnings.append(msg % args)
    )
    with turn_liveness.hold_turn_liveness(app, "B1"):
        threading.Event().wait(0.05)
        assert turn_liveness.turn_is_live(app, "B1") is None
    # Every refresh fails the same way; it is reported once per turn.
    assert len(warnings) == 1
    assert "B1" in warnings[0]


def test_a_lost_first_mark_reads_as_unknown_not_ended(
    app: object, shared_cache: InMemoryCacheProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redis back after a failed write must not make a running turn look ended."""
    # No refresh lands during the turn: only the first write and the final one happen.
    monkeypatch.setattr(turn_liveness, "TURN_LIVENESS_REFRESH_SECONDS", 3600)
    real_setex = shared_cache.setex
    calls = 0

    def flaky_setex(key: str, ttl: int, value: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise CacheUnavailableError
        return real_setex(key, ttl, value)

    monkeypatch.setattr(shared_cache, "setex", flaky_setex)
    with turn_liveness.hold_turn_liveness(app, "B1"):
        # The first write failed and Redis reads again: no word, not "ended".
        assert turn_liveness.turn_is_live(app, "B1") is None
    assert turn_liveness.turn_is_live(app, "B1") is False
