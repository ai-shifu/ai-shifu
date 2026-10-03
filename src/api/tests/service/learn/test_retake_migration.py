"""Exercise the additive migration without connecting to a deployed database."""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_migration_roundtrip_leaves_existing_learning_data_untouched() -> None:
    migration_path = (
        Path(__file__).resolve().parents[3]
        / "migrations/versions/0a3b9866d338_add_deployment_scoped_lesson_retake_.py"
    )
    spec = importlib.util.spec_from_file_location("retake_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    recovery_spec = importlib.util.spec_from_file_location(
        "retake_recovery_migration",
        migration_path.with_name(
            "48efe7c245af_record_retake_recovery_and_producer_.py"
        ),
    )
    recovery = importlib.util.module_from_spec(recovery_spec)
    recovery_spec.loader.exec_module(recovery)
    assert recovery.down_revision == migration.revision
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE existing_learning (id INTEGER PRIMARY KEY)")
        )
        connection.execute(text("INSERT INTO existing_learning VALUES (7)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert {"course_retake_policies", "lesson_retake_attempts"} <= set(
                inspect(connection).get_table_names()
            )
            recovery.upgrade()
            columns = {
                item["name"]
                for item in inspect(connection).get_columns("lesson_retake_attempts")
            }
            assert {"producer_finished_at", "recovery_data"} <= columns
            recovery.downgrade()
            migration.downgrade()
            assert inspect(connection).get_table_names() == ["existing_learning"]
            migration.upgrade()
        assert (
            connection.execute(text("SELECT id FROM existing_learning")).scalar_one()
            == 7
        )
    engine.dispose()
