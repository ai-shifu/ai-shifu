"""Verify identifier safety and row counting in migration tasks."""

import asyncio
import logging

import pytest
from flaskr.command.unified_migration_task import (
    MigrationConfig,
    UnifiedMigrationTask,
    _quote_identifier,
)


class _FakeResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar(self):
        return self._value

    def fetchone(self):
        return self._value


class _FakeSession:
    """Session double that records the statements a migration step issues."""

    def __init__(self, value=1) -> None:
        self._value = value
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return _FakeResult(self._value)

    def close(self):
        pass


def _task_with_session(session):
    task = UnifiedMigrationTask.__new__(UnifiedMigrationTask)
    task.SessionClass = lambda: session
    return task


@pytest.mark.parametrize("name", ["learn_progress_records", "_bid", "Col1"])
def test_quote_identifier_quotes_valid_names(name):
    assert _quote_identifier(name) == f"`{name}`"


@pytest.mark.parametrize(
    "name", ["", "1table", "users; drop table users", "user`s", "learn progress"]
)
def test_quote_identifier_rejects_unsafe_names(name):
    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        _quote_identifier(name)


def test_get_table_count_quotes_the_table_name():
    session = _FakeSession(value=7)
    task = _task_with_session(session)

    assert (
        task._get_table_count("learn_progress_records", where_clause="deleted = 0") == 7
    )

    statement, _ = session.calls[0]
    assert "FROM `learn_progress_records`" in statement
    assert statement.endswith("WHERE deleted = 0")


@pytest.mark.parametrize(
    "table_name", ["learn_progress_records; drop table users", "learn progress"]
)
def test_get_table_count_rejects_unsafe_table_names(table_name):
    session = _FakeSession()
    task = _task_with_session(session)

    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        task._get_table_count(table_name)
    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        task._get_table_count_with_session(session, table_name)
    assert session.calls == []


def test_table_exists_binds_the_table_name():
    session = _FakeSession(value=("learn_progress_records",))
    task = _task_with_session(session)

    assert task._table_exists("learn_progress_records") is True

    statement, params = session.calls[0]
    assert statement == "SHOW TABLES LIKE :table_name"
    assert params == {"table_name": "learn_progress_records"}


def test_check_column_exists_binds_table_and_column():
    session = _FakeSession(value=1)
    task = _task_with_session(session)

    assert (
        task._check_column_exists_with_session(
            session, "learn_progress_records", "user_bid"
        )
        is True
    )

    statement, params = session.calls[0]
    assert "INFORMATION_SCHEMA.COLUMNS" in statement
    assert "learn_progress_records" not in statement
    assert params == {
        "table_name": "learn_progress_records",
        "column_name": "user_bid",
    }


def test_migrate_table_logs_formatted_batch_progress(caplog):
    task = UnifiedMigrationTask.__new__(UnifiedMigrationTask)
    task.config = MigrationConfig(batch_size=10)

    async def table_exists(_table_name):
        return True

    async def table_count(_table_name):
        return 20

    async def process_batch(*_args: object):
        return {"synced": 5, "errors": 0, "error_messages": []}

    task._table_exists_async = table_exists
    task._get_table_count_async = table_count
    task._process_batch_async = process_batch
    caplog.set_level(logging.INFO, logger="flaskr.command.unified_migration_task")

    result = asyncio.run(
        task._migrate_table_async(
            "source_table",
            {
                "target": "target_table",
                "mapping": object(),
                "key_field": "source_id",
                "target_key": "target_id",
            },
        )
    )

    assert result.synced_records == 10
    assert caplog.messages == [
        "Starting migration for table: source_table",
        "Total records to migrate from source_table: 20",
        "Migration progress for source_table: 50.0% (5/20) - Batch 1",
        "Migration progress for source_table: 100.0% (10/20) - Batch 2",
        "Migration completed for source_table: 10/20 records, 0 errors",
    ]
