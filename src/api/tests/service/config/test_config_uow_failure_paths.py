"""Unit-of-work behavior for config writes (B1 migration).

Pre-migration ``add_config`` / ``update_config`` committed and then wrote the
Redis cache; a failure between the two left the database and the cache out of
sync. The cache write now runs as a post-commit callback.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flaskr import dao
from flaskr.service.config import funcs as config_funcs
from flaskr.service.config.models import Config


def _committed_config_count(app: object, key: str) -> int:
    with app.app_context(), dao.db.engine.connect() as connection:
        rows = connection.execute(
            Config.__table__.select().where(Config.key == key, Config.deleted == 0)
        ).fetchall()
    return len(rows)


@pytest.fixture
def fake_redis(monkeypatch: object) -> MagicMock:
    client = MagicMock()
    monkeypatch.setattr(config_funcs, "redis", client)
    monkeypatch.setattr(config_funcs, "has_explicit_env_override", lambda _key: False)
    return client


def test_add_config_failure_after_the_write_persists_nothing(
    app: object, monkeypatch: object, fake_redis: MagicMock
) -> None:
    key = "uow_config_key_fail"

    def failing_cache_key(_app: object, _key: str) -> str:
        message = "cache key boom"
        raise RuntimeError(message)

    monkeypatch.setattr(config_funcs, "_get_config_cache_key", failing_cache_key)

    with app.app_context(), pytest.raises(RuntimeError, match="cache key boom"):
        config_funcs.add_config(app, key, "value-1")

    assert _committed_config_count(app, key) == 0
    fake_redis.set.assert_not_called()


def test_add_config_writes_the_cache_only_after_commit(
    app: object, fake_redis: MagicMock
) -> None:
    key = "uow_config_key_ok"
    seen: list[int] = []
    fake_redis.set.side_effect = lambda *_a, **_k: seen.append(
        _committed_config_count(app, key)
    )

    with app.app_context():
        assert config_funcs.add_config(app, key, "value-1") is True

    assert seen == [1]


def test_update_config_failure_after_the_write_persists_nothing(
    app: object, monkeypatch: object, fake_redis: MagicMock
) -> None:
    key = "uow_config_key_update"
    with app.app_context():
        assert config_funcs.add_config(app, key, "before") is True
    fake_redis.set.reset_mock()

    def failing_cache_key(_app: object, _key: str) -> str:
        message = "cache key boom"
        raise RuntimeError(message)

    monkeypatch.setattr(config_funcs, "_get_config_cache_key", failing_cache_key)

    with app.app_context(), pytest.raises(RuntimeError, match="cache key boom"):
        config_funcs.update_config(app, key, "after")

    with app.app_context(), dao.db.engine.connect() as connection:
        row = connection.execute(
            Config.__table__.select().where(Config.key == key, Config.deleted == 0)
        ).first()
    assert row.value == "before"
    fake_redis.set.assert_not_called()


def test_failed_cache_refresh_drops_the_stale_entry(
    app: object, fake_redis: MagicMock
) -> None:
    """A refresh failure after the commit must not leave an old value cached."""
    key = "uow_config_key_cache_fail"
    fake_redis.set.side_effect = RuntimeError("redis down")

    with app.app_context():
        # The row commits; the callback failure is logged, not raised.
        assert config_funcs.add_config(app, key, "value-1") is True

    assert _committed_config_count(app, key) == 1
    fake_redis.delete.assert_called_once()
    assert fake_redis.delete.call_args.args[0].endswith(key)
