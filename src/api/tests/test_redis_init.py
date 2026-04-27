from flask import Flask


def test_init_redis_sets_socket_timeouts(monkeypatch):
    from flaskr import dao

    captured = {}

    class DummyRedis:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(dao, "Redis", DummyRedis)

    app = Flask(__name__)
    app.config.update(
        REDIS_HOST="redis.example.com",
        REDIS_PORT=6380,
        REDIS_DB=2,
        REDIS_PASSWORD="secret",
        REDIS_USER="worker",
        REDIS_SOCKET_CONNECT_TIMEOUT=0.75,
        REDIS_SOCKET_TIMEOUT=1.25,
    )

    dao.init_redis(app)

    assert captured == {
        "host": "redis.example.com",
        "port": 6380,
        "db": 2,
        "password": "secret",
        "username": "worker",
        "socket_connect_timeout": 0.75,
        "socket_timeout": 1.25,
    }


def test_init_redis_uses_default_socket_timeouts(monkeypatch):
    from flaskr import dao

    captured = {}

    class DummyRedis:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(dao, "Redis", DummyRedis)

    app = Flask(__name__)
    app.config.update(
        REDIS_HOST="redis.example.com",
        REDIS_PORT=6379,
        REDIS_DB=0,
        REDIS_PASSWORD="",
        REDIS_USER="",
    )
    app.config.pop("REDIS_SOCKET_CONNECT_TIMEOUT", None)
    app.config.pop("REDIS_SOCKET_TIMEOUT", None)

    dao.init_redis(app)

    assert captured["socket_connect_timeout"] == 1.0
    assert captured["socket_timeout"] == 1.0
