"""The single additive baseline column leaves existing attempts unknown."""

from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError


def _migration() -> object:
    path = (
        Path(__file__).parents[2]
        / "migrations/versions/f569f2199973_record_lesson_content_revision_baseline.py"
    )
    spec = spec_from_file_location("lesson_content_revision_migration", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_keeps_legacy_baselines_null_and_downgrade_preserves_rows() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE learn_agent_sessions (id INTEGER PRIMARY KEY, session_data TEXT)"
            )
        )
        connection.execute(
            text("INSERT INTO learn_agent_sessions VALUES (1, 'historical-session')")
        )
        migration = _migration()
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        column = next(
            c
            for c in inspect(connection).get_columns("learn_agent_sessions")
            if c["name"] == "content_revision"
        )
        assert column["nullable"] is True
        assert (
            connection.execute(
                text("SELECT content_revision FROM learn_agent_sessions")
            ).scalar()
            is None
        )
        connection.execute(
            text("UPDATE learn_agent_sessions SET content_revision = 42")
        )
        assert (
            connection.execute(
                text("SELECT content_revision FROM learn_agent_sessions")
            ).scalar()
            == 42
        )
        migration.downgrade()
        assert [
            c["name"] for c in inspect(connection).get_columns("learn_agent_sessions")
        ] == ["id", "session_data"]
        assert (
            connection.execute(
                text("SELECT session_data FROM learn_agent_sessions")
            ).scalar()
            == "historical-session"
        )
    engine.dispose()


def _mysql_migration(execute: Mock) -> object:
    migration = _migration()
    migration.op = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="mysql")),
        execute=execute,
    )
    return migration


def _mysql_error(errno: int) -> OperationalError:
    return OperationalError("ALTER TABLE", {}, Exception(errno, "DDL failure"))


def test_mysql_upgrade_uses_instant_once_and_does_not_backfill() -> None:
    execute = Mock()
    migration = _mysql_migration(execute)
    migration.upgrade()
    execute.assert_called_once()
    statement = execute.call_args.args[0]
    assert "ADD COLUMN `content_revision` BIGINT NULL" in statement
    assert statement.endswith("ALGORITHM=INSTANT")
    assert "LOCK=" not in statement
    assert "UPDATE" not in statement


@pytest.mark.parametrize("errno", [1845, 1846])
def test_mysql_unsupported_instant_falls_back_once_to_online_inplace(
    errno: int,
) -> None:
    execute = Mock(side_effect=[_mysql_error(errno), None])
    _mysql_migration(execute).upgrade()
    assert execute.call_count == 2
    instant, fallback = [call.args[0] for call in execute.call_args_list]
    assert instant.endswith("ALGORITHM=INSTANT")
    assert fallback == instant.replace(
        "ALGORITHM=INSTANT", "ALGORITHM=INPLACE, LOCK=NONE"
    )


@pytest.mark.parametrize("errno", [1142, 1060, 1205, 1213, 2013])
def test_mysql_other_failures_propagate_without_retry(errno: int) -> None:
    failure = _mysql_error(errno)
    execute = Mock(side_effect=failure)
    with pytest.raises(OperationalError) as raised:
        _mysql_migration(execute).upgrade()
    assert raised.value is failure
    execute.assert_called_once()


def test_mysql_unknown_error_code_does_not_retry() -> None:
    failure = OperationalError("ALTER TABLE", {}, Exception())
    execute = Mock(side_effect=failure)
    with pytest.raises(OperationalError) as raised:
        _mysql_migration(execute).upgrade()
    assert raised.value is failure
    execute.assert_called_once()


def test_mysql_inplace_failure_propagates_without_another_fallback() -> None:
    failure = _mysql_error(1846)
    execute = Mock(side_effect=[_mysql_error(1845), failure])
    with pytest.raises(OperationalError) as raised:
        _mysql_migration(execute).upgrade()
    assert raised.value is failure
    assert execute.call_count == 2


def test_offline_mysql_outputs_only_instant_for_operator_review() -> None:
    output = StringIO()
    migration = _migration()
    migration.op = Operations(
        MigrationContext.configure(
            dialect_name="mysql", opts={"as_sql": True, "output_buffer": output}
        )
    )
    migration.upgrade()
    statement = output.getvalue()
    assert statement.count("ALTER TABLE") == 1
    assert "ALGORITHM=INSTANT" in statement
    assert "INPLACE" not in statement
    assert "COPY" not in statement
    assert "LOCK=" not in statement
