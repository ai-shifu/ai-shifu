"""Verify Redis-guarded work runs only with a configured client."""


def test_run_with_redis_executes_once(app, monkeypatch):
    from flaskr import dao

    from tests.common.fixtures.fake_redis import FakeRedis

    fake_redis = FakeRedis()
    monkeypatch.setattr(dao._redis_state, "client", fake_redis)

    def add_one(value):
        return value + 1

    result = dao.run_with_redis(app, "lock-key", 10, add_one, [1])
    assert result == 2


def test_run_with_redis_skips_when_client_is_unconfigured(app, monkeypatch):
    from flaskr import dao

    monkeypatch.setattr(dao._redis_state, "client", None)

    assert dao.run_with_redis(app, "lock-key", 10, lambda: "unused", []) is None
