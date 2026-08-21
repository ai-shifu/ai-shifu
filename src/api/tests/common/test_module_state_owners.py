"""Protect shared extension and client instance ownership."""

from flask import Flask
from flaskr import dao
from flaskr.framework.plugin import plugin_manager as plugin_manager_module


def test_database_extension_keeps_one_shared_identity() -> None:
    app = Flask("stable-database-extension")
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    shared_db = dao.db

    dao.init_db(app)

    assert dao.db is shared_db
    assert app.extensions["sqlalchemy"] is shared_db


def test_redis_initialization_updates_the_owned_client(monkeypatch) -> None:
    app = Flask("owned-redis-client")
    app.config.update(
        REDIS_HOST="redis.internal",
        REDIS_PORT=6380,
        REDIS_DB=4,
        REDIS_PASSWORD="secret",
        REDIS_USER="worker",
    )
    sentinel = object()
    captured: dict[str, object] = {}

    def fake_redis(**kwargs: object):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(dao, "Redis", fake_redis)
    dao.set_redis_client(None)

    dao.init_redis(app)

    assert dao.get_redis_client() is sentinel
    assert captured == {
        "host": "redis.internal",
        "port": 6380,
        "db": 4,
        "password": "secret",
        "username": "worker",
    }


def test_plugin_manager_registry_replaces_one_owned_instance(monkeypatch) -> None:
    first_app = Flask("first-plugin-manager")
    second_app = Flask("second-plugin-manager")
    monkeypatch.setattr(plugin_manager_module._plugin_manager_state, "manager", None)

    plugin_manager_module.enable_plugin_manager(first_app)
    first_manager = plugin_manager_module.get_plugin_manager()
    plugin_manager_module.enable_plugin_manager(second_app)
    second_manager = plugin_manager_module.get_plugin_manager()

    assert first_manager is not None
    assert second_manager is not None
    assert first_manager is not second_manager
    assert first_manager.app is first_app
    assert second_manager.app is second_app
