"""Exercise migration checkpoint recovery and standalone operator commands."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from flaskr.command import unified_migration_task as migration
from flaskr.common import config as config_module


@pytest.fixture
def task() -> migration.UnifiedMigrationTask:
    instance = migration.UnifiedMigrationTask.__new__(migration.UnifiedMigrationTask)
    instance.engine = Mock()
    instance.SessionClass = Mock(return_value=Mock())
    instance.config = migration.MigrationConfig()
    return instance


@pytest.mark.parametrize(
    "url", [None, "mysql://localhost/example", "sqlite:///example.db"]
)
def test_constructor_resolves_default_and_normalizes_only_mysql(
    monkeypatch: pytest.MonkeyPatch, url: str | None
) -> None:
    engine = Mock()
    create = Mock(return_value=engine)
    session_factory = Mock()
    monkeypatch.setattr(migration, "create_engine", create)
    monkeypatch.setattr(migration, "sessionmaker", session_factory)
    monkeypatch.setattr(
        config_module, "get_config", Mock(return_value="mysql://localhost/default")
    )
    instance = migration.UnifiedMigrationTask(url)
    expected_url = (url or "mysql://localhost/default").replace(
        "mysql://", "mysql+pymysql://"
    )
    assert create.call_args.args == (expected_url,)
    assert create.call_args.kwargs["pool_pre_ping"] is True
    session_factory.assert_called_once_with(bind=engine)
    assert set(instance.table_mappings) == {
        "ai_course_lesson_attend",
        "ai_course_lesson_attendscript",
        "discount",
        "discount_record",
    }
    assert instance.config.batch_size == 1000
    assert not instance.force_full_migration
    instance.close()
    engine.dispose.assert_called_once_with()


@pytest.mark.parametrize("operation", ["_table_exists", "_get_table_count"])
def test_failed_read_helpers_close_sessions_and_return_safe_defaults(
    task: migration.UnifiedMigrationTask, operation: str
) -> None:
    session = task.SessionClass.return_value
    session.execute.side_effect = RuntimeError("database unavailable")
    result = getattr(task, operation)("source")
    assert result == (False if operation == "_table_exists" else 0)
    session.close.assert_called_once_with()


def test_async_table_existence_delegates_database_probe(
    task: migration.UnifiedMigrationTask,
) -> None:
    session = task.SessionClass.return_value
    session.execute.return_value.fetchone.return_value = ("source",)
    assert asyncio.run(task._table_exists_async("source"))
    assert session.execute.call_args.args[1] == {"table_name": "source"}
    session.close.assert_called_once_with()


@pytest.mark.parametrize("value", [0, None, RuntimeError("database unavailable")])
def test_optional_schema_probes_handle_empty_and_failed_queries(
    task: migration.UnifiedMigrationTask, value: object
) -> None:
    session = task.SessionClass.return_value
    if isinstance(value, Exception):
        session.execute.side_effect = value
    else:
        session.execute.return_value.scalar.return_value = value
    assert task._get_table_count_with_session(session, "source") == 0
    assert not task._check_column_exists_with_session(session, "source", "field")


@pytest.mark.parametrize("value", [None, (None,), (7,), RuntimeError("log absent")])
def test_checkpoint_id_defaults_to_zero_when_no_usable_log(
    task: migration.UnifiedMigrationTask, value: object
) -> None:
    task._ensure_sync_log_table_with_session = Mock()
    session = task.SessionClass.return_value
    if isinstance(value, Exception):
        session.execute.side_effect = value
    else:
        session.execute.return_value.fetchone.return_value = value
    result = task._get_last_synced_id_with_session(session, "source_sync")
    assert result == (7 if value == (7,) else 0)
    assert session.execute.call_args.args[1] == {"type": "source_sync"}


@pytest.mark.parametrize(
    "value", [None, (datetime(2026, 9, 20),), RuntimeError("log absent")]
)
def test_checkpoint_time_falls_back_and_closes_owned_session(
    task: migration.UnifiedMigrationTask, value: object
) -> None:
    task._ensure_sync_log_table_with_session = Mock()
    session = task.SessionClass.return_value
    if isinstance(value, Exception):
        session.execute.side_effect = value
    else:
        session.execute.return_value.fetchone.return_value = value
    assert task._get_last_sync_time("source_sync") == (
        value[0] if isinstance(value, tuple) else datetime(2020, 1, 1)
    )
    session.close.assert_called_once_with()


@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.parametrize("operation", ["time", "id"])
def test_checkpoint_writes_bind_values_and_tolerate_log_failure(
    task: migration.UnifiedMigrationTask, operation: str, fails: bool
) -> None:
    task._ensure_sync_log_table_with_session = Mock()
    session = task.SessionClass.return_value
    if fails:
        session.execute.side_effect = RuntimeError("checkpoint unavailable")
    if operation == "time":
        timestamp = datetime(2026, 9, 20)
        task._update_sync_time("source_sync", timestamp)
        assert session.execute.call_args.args[1] == {
            "type": "source_sync",
            "time": timestamp,
        }
        session.close.assert_called_once_with()
    else:
        task._update_last_synced_id_with_session(session, "source_sync", 12)
        assert session.execute.call_args.args[1] == {
            "type": "source_sync",
            "last_id": 12,
        }
    assert session.commit.call_count == int(not fails)


@pytest.mark.parametrize("column_count", [0, 1, RuntimeError("metadata unavailable")])
def test_sync_log_creation_repairs_only_missing_checkpoint_column(
    task: migration.UnifiedMigrationTask, column_count: object
) -> None:
    session = task.SessionClass.return_value
    result = Mock()
    if isinstance(column_count, Exception):
        result.scalar.side_effect = column_count
    else:
        result.scalar.return_value = column_count
    session.execute.return_value = result
    task._ensure_sync_log_table()
    statements = [str(call.args[0]) for call in session.execute.call_args_list]
    assert "CREATE TABLE IF NOT EXISTS migration_sync_log" in statements[0]
    assert any("ALTER TABLE" in sql for sql in statements) is (column_count == 0)
    session.commit.assert_called_once_with()
    session.close.assert_called_once_with()


def test_sync_log_creation_failure_closes_session_without_commit(
    task: migration.UnifiedMigrationTask,
) -> None:
    session = task.SessionClass.return_value
    session.execute.side_effect = RuntimeError("DDL failed")
    task._ensure_sync_log_table()
    session.commit.assert_not_called()
    session.close.assert_called_once_with()


@pytest.mark.parametrize("action", ["migrate", "verify", "report"])
@pytest.mark.parametrize("output_file", [False, True])
def test_standalone_cli_runs_requested_action_and_closes_resources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    action: str,
    output_file: bool,
) -> None:
    task = Mock()
    task.migrate_all_tables = AsyncMock(return_value={"source": "migrated"})
    task.verify_data_consistency = AsyncMock(
        return_value={
            "source": SimpleNamespace(is_consistent=True, table_pair="source -> target")
        }
    )
    task.generate_migration_report.return_value = "report body"
    factory = Mock(return_value=task)
    monkeypatch.setattr(migration, "UnifiedMigrationTask", factory)
    arguments = [
        "migration",
        action,
        "--database-url",
        "sqlite://",
        "--batch-size",
        "4",
        "--max-workers",
        "2",
        "--force-full",
    ]
    target = tmp_path / "report.txt"
    if output_file:
        arguments.extend(["--output-file", str(target)])
    monkeypatch.setattr(sys, "argv", arguments)
    asyncio.run(migration.main())
    database_url, config = factory.call_args.args
    assert database_url == "sqlite://"
    assert config.batch_size == 4
    assert config.max_workers == 2
    assert task.force_full_migration
    assert task.migrate_all_tables.await_count == int(action == "migrate")
    task.verify_data_consistency.assert_awaited_once()
    if action == "migrate" and output_file:
        assert target.read_text(encoding="utf-8") == "report body"
    elif action == "verify":
        assert "PASSED: source -> target" in capsys.readouterr().out
    else:
        assert "report body" in capsys.readouterr().out
    if action == "report":
        assert task.generate_migration_report.call_args.args[0] == {}
    task.close.assert_called_once_with()


def test_standalone_verify_exits_nonzero_on_inconsistency_and_closes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    task = Mock()
    task.verify_data_consistency = AsyncMock(
        return_value={
            "source": SimpleNamespace(
                is_consistent=False, table_pair="source -> target"
            )
        }
    )
    monkeypatch.setattr(migration, "UnifiedMigrationTask", Mock(return_value=task))
    monkeypatch.setattr(sys, "argv", ["migration", "verify"])
    with pytest.raises(SystemExit) as error:
        asyncio.run(migration.main())
    assert error.value.code == 1
    assert "FAILED: source -> target" in capsys.readouterr().out
    task.close.assert_called_once_with()
