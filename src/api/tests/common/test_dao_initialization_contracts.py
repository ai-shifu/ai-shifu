"""Verify database startup options and best-effort cleanup boundaries."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr import dao
from sqlalchemy import text


@pytest.mark.parametrize(
    "options",
    [
        None,
        {},
        {"pool_size": 7, "pool_pre_ping": True, "connect_args": {"charset": "utf8mb4"}},
    ],
)
def test_mysql_startup_normalizes_pool_settings_and_preserves_explicit_overrides(
    monkeypatch: object, options: object
) -> None:
    app = Flask("mysql-options-contract")
    app.config.update(
        SQLALCHEMY_DATABASE_URI="mysql+pymysql://localhost/test",
        SQLALCHEMY_ENGINE_OPTIONS=options,
        SQLALCHEMY_POOL_SIZE="invalid",
        SQLALCHEMY_MAX_OVERFLOW="9",
        SQLALCHEMY_POOL_TIMEOUT={},
        SQLALCHEMY_POOL_RECYCLE="",
    )
    extension = Mock()
    monkeypatch.setattr(dao, "db", extension)
    dao.init_db(app)
    result = app.config["SQLALCHEMY_ENGINE_OPTIONS"]
    assert result["pool_size"] == (7 if options else 20)
    assert result["max_overflow"] == 9
    assert result["pool_timeout"] == 30
    assert result["pool_recycle"] == 3600
    assert result["pool_pre_ping"] is bool(options)
    assert result["connect_args"]["init_command"] == "SET time_zone = '+00:00'"
    if options:
        assert result["connect_args"]["charset"] == "utf8mb4"
        assert "init_command" not in options["connect_args"]
    extension.init_app.assert_called_once_with(app)


def test_existing_connection_initialization_is_not_overwritten(
    monkeypatch: object,
) -> None:
    app = Flask("mysql-custom-initialization")
    app.config.update(
        SQLALCHEMY_DATABASE_URI="mysql+pymysql://localhost/test",
        SQLALCHEMY_ENGINE_OPTIONS={
            "connect_args": {
                "init_command": "SET time_zone = '+00:00', sql_mode = 'STRICT_ALL_TABLES'"
            }
        },
    )
    monkeypatch.setattr(dao, "db", Mock())
    dao.init_db(app)
    assert (
        app.config["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"]["init_command"]
        == "SET time_zone = '+00:00', sql_mode = 'STRICT_ALL_TABLES'"
    )


def test_sqlite_debug_startup_logs_queries_and_keeps_queue_pool_options_out(
    tmp_path: object, caplog: object
) -> None:
    app = Flask("sqlite-debug-contract")
    app.config.update(
        DEBUG=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'test.db'}",
        SQLALCHEMY_ENGINE_OPTIONS={},
        SQLALCHEMY_POOL_SIZE=100,
    )
    engine_logger = logging.getLogger("sqlalchemy.engine")
    original_level = engine_logger.level
    try:
        dao.init_db(app)
        with app.app_context(), caplog.at_level(logging.INFO, logger=app.name):
            assert dao.db.session.execute(text("SELECT 5")).scalar_one() == 5
            assert (
                dao.db.session.execute(text("SELECT :value"), {"value": 7}).scalar_one()
                == 7
            )
            dao.db.session.remove()
            dao.db.engine.dispose()
        assert "pool_size" not in app.config["SQLALCHEMY_ENGINE_OPTIONS"]
        assert "connect_args" not in app.config["SQLALCHEMY_ENGINE_OPTIONS"]
        assert "SELECT 5" in caplog.text
        assert "Parameters: (7,)" in caplog.text
        assert "Location: File:" in caplog.text
    finally:
        engine_logger.setLevel(original_level)


def test_cleanup_before_database_initialization_is_safe(monkeypatch: object) -> None:
    monkeypatch.setattr(dao, "db", None)
    assert dao.invalidate_session(source="startup") is False
    assert dao.cleanup_session_after(None, source="startup") == "noop"
    assert dao._rollback_quietly() is True


def test_session_removal_failure_does_not_replace_a_propagating_error(
    monkeypatch: object,
) -> None:
    session = Mock()
    session.remove.side_effect = RuntimeError("cleanup failed")
    monkeypatch.setattr(dao, "db", SimpleNamespace(session=session))
    failure = ValueError("original application failure")

    def fail_with_cleanup() -> None:
        try:
            raise failure
        finally:
            dao.release_session_classified(source="request")

    with pytest.raises(ValueError, match="original application failure"):
        fail_with_cleanup()
    session.remove.assert_called_once()
    session.invalidate.assert_not_called()


def test_redis_initialization_without_password_does_not_pass_empty_credentials(
    monkeypatch: object,
) -> None:
    app = Flask("redis-no-password")
    app.config.update(
        REDIS_HOST="localhost", REDIS_PORT=6379, REDIS_DB=3, REDIS_PASSWORD=""
    )
    client = Mock()
    constructor = Mock(return_value=client)
    monkeypatch.setattr(dao, "Redis", constructor)
    monkeypatch.setattr(dao._redis_state, "client", None)
    dao.init_redis(app)
    constructor.assert_called_once_with(host="localhost", port=6379, db=3)
    assert dao.get_redis_client() is client


def test_redis_lock_contention_skips_work_without_releasing_someone_elses_lock(
    monkeypatch: object,
) -> None:
    app = Flask("redis-lock-contention")
    lock = Mock(acquire=Mock(return_value=False))
    client = Mock(lock=Mock(return_value=lock))
    monkeypatch.setattr(dao._redis_state, "client", client)
    work = Mock()
    assert dao.run_with_redis(app, "work", 15, work, ("argument",)) is None
    client.lock.assert_called_once_with("work", timeout=15, blocking_timeout=15)
    work.assert_not_called()
    lock.release.assert_not_called()


def test_missing_driver_connection_does_not_interfere_with_statement_execution() -> (
    None
):
    dao._intercept_desync_before_execute(
        SimpleNamespace(connection=SimpleNamespace()),
        None,
        "SELECT 1",
        None,
        None,
        executemany=False,
    )
