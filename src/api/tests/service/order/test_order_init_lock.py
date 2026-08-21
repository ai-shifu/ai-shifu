"""Verify order init lock behavior."""

from typing import Never

import flaskr.service.order.funs as order_funs


class DummyLock:
    """Simulate lock behavior for tests."""

    def __init__(self) -> None:
        """Initialize the dummy lock test double."""
        self.acquired = 0
        self.released = 0

    def acquire(self, blocking=True) -> bool:
        _ = blocking
        self.acquired += 1
        return True

    def release(self) -> None:
        self.released += 1


class DummyRedis:
    """Simulate Redis behavior for tests."""

    def __init__(self) -> None:
        """Initialize the dummy Redis test double."""
        self.last_key = None
        self.last_timeout = None
        self.last_blocking_timeout = None
        self.lock_instance = DummyLock()

    def lock(self, key, timeout=None, blocking_timeout=None) -> object:
        self.last_key = key
        self.last_timeout = timeout
        self.last_blocking_timeout = blocking_timeout
        return self.lock_instance


class DummyApp:
    """Simulate app behavior for tests."""

    def __init__(self, prefix="ai-shifu") -> None:
        """Initialize the dummy app test double."""
        self.config = {"REDIS_KEY_PREFIX": prefix}


def test_order_init_lock_uses_prefixed_key(monkeypatch) -> None:
    dummy_redis = DummyRedis()
    monkeypatch.setattr(order_funs, "cache_provider", dummy_redis)
    app = DummyApp(prefix="unit-test")

    with order_funs._order_init_lock(app, "user-1", "course-1"):
        pass

    assert dummy_redis.last_key == "unit-test:order:init:user-1:course-1"
    assert dummy_redis.last_timeout == 10
    assert dummy_redis.last_blocking_timeout == 10
    assert dummy_redis.lock_instance.acquired == 1
    assert dummy_redis.lock_instance.released == 1


def test_order_init_lock_skips_when_cache_provider_errors(monkeypatch) -> None:
    class _BrokenCacheProvider:
        def lock(self, *args: object, **kwargs: object) -> Never:
            _ = (args, kwargs)
            message = "lock unavailable"
            raise RuntimeError(message)

    monkeypatch.setattr(order_funs, "cache_provider", _BrokenCacheProvider())
    app = DummyApp(prefix="unit-test")

    with order_funs._order_init_lock(app, "user-1", "course-1"):
        pass
