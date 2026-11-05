"""A running turn marks its block until it ends, and only Redis can vouch for it."""

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
def test_the_mark_lasts_exactly_as_long_as_the_turn(app: object) -> None:
    assert turn_liveness.turn_is_live(app, "B1") is False
    with turn_liveness.hold_turn_liveness(app, "B1"):
        assert turn_liveness.turn_is_live(app, "B1") is True
        assert turn_liveness.turn_is_live(app, "B2") is False
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
    # The refresher stops with the turn: nothing puts the key back afterwards.
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
