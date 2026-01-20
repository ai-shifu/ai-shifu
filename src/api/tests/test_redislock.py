def test_run_with_redis_executes_once(app, monkeypatch):
    from flaskr import dao
    from tests.common.fixtures.fake_redis import FakeRedis

    fake_redis = FakeRedis()
    monkeypatch.setattr(dao, "redis_client", fake_redis, raising=False)

    def add_one(value):
        return value + 1

    result = dao.run_with_redis(app, "lock-key", 10, add_one, [1])
    assert result == 2
