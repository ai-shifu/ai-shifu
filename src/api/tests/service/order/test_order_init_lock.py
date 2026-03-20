import flaskr.service.order.funs as order_funs


class DummyLock:
    def __init__(self):
        self.acquired = 0
        self.released = 0

    def acquire(self, blocking=True):
        self.acquired += 1
        return True

    def release(self):
        self.released += 1


class DummyRedis:
    def __init__(self):
        self.last_key = None
        self.last_timeout = None
        self.last_blocking_timeout = None
        self.lock_instance = DummyLock()

    def lock(self, key, timeout=None, blocking_timeout=None):
        self.last_key = key
        self.last_timeout = timeout
        self.last_blocking_timeout = blocking_timeout
        return self.lock_instance


class DummyApp:
    def __init__(self, prefix="ai-shifu"):
        self.config = {"REDIS_KEY_PREFIX": prefix}


def test_order_init_lock_uses_prefixed_key(monkeypatch):
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


def test_order_init_lock_skips_when_cache_provider_errors(monkeypatch):
    class _BrokenCacheProvider:
        def lock(self, *args, **kwargs):
            raise RuntimeError("lock unavailable")

    monkeypatch.setattr(order_funs, "cache_provider", _BrokenCacheProvider())
    app = DummyApp(prefix="unit-test")

    with order_funs._order_init_lock(app, "user-1", "course-1"):
        pass
