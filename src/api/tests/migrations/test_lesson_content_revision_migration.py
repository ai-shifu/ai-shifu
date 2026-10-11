"""The single additive baseline column leaves existing attempts unknown."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


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


def test_mysql_upgrade_requires_online_ddl_and_does_not_backfill() -> None:
    migration = _migration()
    statements = []
    migration.op = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="mysql")),
        execute=statements.append,
    )
    migration.upgrade()
    assert len(statements) == 1
    assert "ADD COLUMN `content_revision` BIGINT NULL" in statements[0]
    assert "ALGORITHM=INPLACE, LOCK=NONE" in statements[0]
    assert "UPDATE" not in statements[0]
