"""Exercise legacy migration transactions, concurrency and consistency reports."""

import asyncio
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from flaskr.command import unified_migration_task as migration
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def task(tmp_path: Path) -> Iterator[migration.UnifiedMigrationTask]:
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE legacy (id INTEGER PRIMARY KEY, bid TEXT, value TEXT)")
        )
        connection.execute(
            text(
                "CREATE TABLE current (bid TEXT PRIMARY KEY, value TEXT, deleted INTEGER DEFAULT 0)"
            )
        )
        connection.execute(
            text("INSERT INTO legacy VALUES (1, 'one', 'first'), (2, 'two', 'second')")
        )
    instance = migration.UnifiedMigrationTask.__new__(migration.UnifiedMigrationTask)
    instance.engine = engine
    instance.SessionClass = sessionmaker(bind=engine)
    instance.config = migration.MigrationConfig(batch_size=2, max_workers=1)
    instance.force_full_migration = True
    instance.table_mappings = {
        "legacy": {
            "target": "current",
            "mapping": _map_record,
            "key_field": "bid",
            "target_key": "bid",
        }
    }
    instance._get_last_synced_id_with_session = Mock(return_value=0)
    instance._update_last_synced_id_with_session = Mock()
    yield instance
    instance.close()


def _map_record(record: object) -> dict:
    return {"bid": record.bid, "value": record.value, "deleted": 0}


def _rows(task: migration.UnifiedMigrationTask) -> list:
    with task.engine.connect() as connection:
        return list(
            connection.execute(text("SELECT bid, value FROM current ORDER BY bid"))
        )


def _run_batch(
    task: migration.UnifiedMigrationTask, mapping: object = _map_record, offset: int = 0
) -> dict:
    return task._process_batch_sync("legacy", "current", mapping, "bid", "bid", offset)


def test_batch_inserts_updates_and_resumes_without_duplicate_rows(
    task: migration.UnifiedMigrationTask,
) -> None:
    assert _run_batch(task) == {"synced": 2, "errors": 0, "error_messages": []}
    assert _rows(task) == [("one", "first"), ("two", "second")]
    with task.engine.begin() as connection:
        connection.execute(text("UPDATE legacy SET value='changed' WHERE id=1"))
    assert _run_batch(task)["synced"] == 2
    assert _rows(task) == [("one", "changed"), ("two", "second")]
    assert task._update_last_synced_id_with_session.call_args.args[1:] == (
        "legacy_sync",
        2,
    )


def test_batch_honors_offset_and_empty_batch_does_not_advance_checkpoint(
    task: migration.UnifiedMigrationTask,
) -> None:
    assert _run_batch(task, offset=1)["synced"] == 1
    assert _rows(task) == [("two", "second")]
    task._update_last_synced_id_with_session.reset_mock()
    assert _run_batch(task, offset=2) == {
        "synced": 0,
        "errors": 0,
        "error_messages": [],
    }
    task._update_last_synced_id_with_session.assert_not_called()


@pytest.mark.parametrize("existing_count", [99, 100])
def test_incremental_mode_only_applies_after_target_is_populated(
    task: migration.UnifiedMigrationTask, existing_count: int
) -> None:
    task.force_full_migration = False
    task._get_last_synced_id_with_session.return_value = 1
    with task.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO current (bid,value) VALUES (:bid,'existing')"),
            [{"bid": f"existing-{index}"} for index in range(existing_count)],
        )
    result = _run_batch(task)
    expected = 1 if existing_count == 100 else 2
    assert result["synced"] == expected
    rows = dict(_rows(task))
    assert rows["two"] == "second"
    assert ("one" in rows) is (existing_count == 99)


def test_existing_key_only_mapping_does_not_overwrite_record(
    task: migration.UnifiedMigrationTask,
) -> None:
    _run_batch(task)
    result = _run_batch(task, mapping=lambda row: {"bid": row.bid})
    assert result["synced"] == 2
    assert _rows(task) == [("one", "first"), ("two", "second")]


def test_tolerated_mapping_error_is_reported_with_successful_rows(
    task: migration.UnifiedMigrationTask,
) -> None:
    def mapper(row: object) -> dict:
        if row.bid == "two":
            message = "legacy row invalid"
            raise ValueError(message)
        return _map_record(row)

    result = _run_batch(task, mapper)
    assert result == {
        "synced": 1,
        "errors": 1,
        "error_messages": ["Record migration failed for two: legacy row invalid"],
    }
    assert _rows(task) == [("one", "first")]


def test_excessive_mapping_errors_roll_back_prior_success_and_leave_checkpoint(
    task: migration.UnifiedMigrationTask,
) -> None:
    task.config.batch_size = 3
    with task.engine.begin() as connection:
        connection.execute(text("INSERT INTO legacy VALUES (3,'three','third')"))

    def mapper(row: object) -> dict:
        if row.id > 1:
            message = "invalid source row"
            raise ValueError(message)
        return _map_record(row)

    with pytest.raises(
        migration.MigrationBatchError, match="Too many errors in batch: 2"
    ):
        _run_batch(task, mapper)
    assert _rows(task) == []
    task._update_last_synced_id_with_session.assert_not_called()


def test_async_batch_uses_real_worker_and_returns_persisted_result(
    task: migration.UnifiedMigrationTask,
) -> None:
    result = asyncio.run(
        task._process_batch_async("legacy", "current", _map_record, "bid", "bid", 0)
    )
    assert result["synced"] == 2
    assert _rows(task) == [("one", "first"), ("two", "second")]
    assert asyncio.run(task._get_table_count_async("current", "deleted = 0")) == 2


@pytest.mark.parametrize("absent", ["legacy", "current"])
def test_missing_migration_table_returns_diagnostic_without_processing(
    task: migration.UnifiedMigrationTask, absent: str
) -> None:
    task._table_exists_async = AsyncMock(side_effect=lambda name: name != absent)
    task._process_batch_async = AsyncMock()
    result = asyncio.run(
        task._migrate_table_async("legacy", task.table_mappings["legacy"])
    )
    assert result.total_records == 0
    assert result.synced_records == 0
    assert result.errors == [
        f"{'Source' if absent == 'legacy' else 'Target'} table {absent} does not exist"
    ]
    task._process_batch_async.assert_not_called()


def test_table_migration_continues_after_failed_batch(
    task: migration.UnifiedMigrationTask,
) -> None:
    task._table_exists_async = AsyncMock(return_value=True)
    task._get_table_count_async = AsyncMock(return_value=4)
    task._process_batch_async = AsyncMock(
        side_effect=[
            RuntimeError("batch failed"),
            {"synced": 2, "errors": 0, "error_messages": []},
        ]
    )
    result = asyncio.run(
        task._migrate_table_async("legacy", task.table_mappings["legacy"])
    )
    assert result.total_records == 4
    assert result.synced_records == 2
    assert result.error_records == 2
    assert result.errors == ["Batch error at offset 0: batch failed"]
    assert result.success_rate == 50
    assert result.duration >= 0


def test_concurrent_migrations_preserve_success_and_failure_by_table(
    task: migration.UnifiedMigrationTask,
) -> None:
    task.table_mappings["other"] = dict(task.table_mappings["legacy"])
    success = SimpleNamespace(table_name="legacy", synced_records=2)

    async def migrate(name: str, config: dict) -> object:
        assert config["target"] == "current"
        if name == "other":
            message = "unavailable table"
            raise ValueError(message)
        return success

    task._migrate_table_async = migrate
    results = asyncio.run(task.migrate_all_tables())
    assert results["legacy"] is success
    assert results["other"].table_name == "other"
    assert results["other"].errors == ["unavailable table"]


@pytest.mark.parametrize(
    ("old", "new", "integrity", "consistent"),
    [(3, 3, True, True), (3, 2, True, False), (3, 3, False, False)],
)
def test_consistency_requires_matching_counts_and_values(
    task: migration.UnifiedMigrationTask,
    old: int,
    new: int,
    integrity: bool,
    consistent: bool,
) -> None:
    task._get_table_count_async = AsyncMock(side_effect=[old, new])
    task._verify_sample_integrity_async = AsyncMock(
        return_value=(integrity, [] if integrity else ["different value"])
    )
    result = asyncio.run(task.verify_data_consistency())["legacy"]
    assert result.is_consistent is consistent
    assert result.old_count == old
    assert result.new_count == new
    assert task._get_table_count_async.call_args.args == ("current",)
    assert task._get_table_count_async.call_args.kwargs == {
        "where_clause": "deleted = 0"
    }


def test_consistency_query_failure_is_recorded_as_failure(
    task: migration.UnifiedMigrationTask,
) -> None:
    task._get_table_count_async = AsyncMock(side_effect=RuntimeError("connection lost"))
    result = asyncio.run(task.verify_data_consistency())["legacy"]
    assert not result.is_consistent
    assert result.data_mismatches == ["Check failed: connection lost"]


@pytest.mark.parametrize("sample_size", [0, 19, 20])
def test_sample_integrity_threshold_and_missing_target(
    task: migration.UnifiedMigrationTask, sample_size: int
) -> None:
    session = Mock()
    samples = [SimpleNamespace(bid=f"row-{index}") for index in range(sample_size)]
    session.execute.side_effect = [
        Mock(fetchall=Mock(return_value=samples)),
        *[
            Mock(fetchone=Mock(return_value=None if index == 0 else SimpleNamespace()))
            for index in range(sample_size)
        ],
    ]
    task.SessionClass = lambda: session
    passed, mismatches = asyncio.run(
        task._verify_sample_integrity_async("legacy", "current", "bid", "bid")
    )
    assert passed is (sample_size != 19)
    assert mismatches == (["Missing record in target: row-0"] if sample_size else [])
    session.close.assert_called_once_with()


def test_sample_mapping_mismatch_and_database_failure_close_session(
    task: migration.UnifiedMigrationTask,
) -> None:
    session = Mock()
    sample = SimpleNamespace(bid="one", discount_code="CODE", discount_value=3)
    session.execute.side_effect = [
        Mock(fetchall=Mock(return_value=[sample])),
        Mock(fetchone=Mock(return_value=SimpleNamespace(code="WRONG", value=3))),
    ]
    task.SessionClass = lambda: session
    assert asyncio.run(
        task._verify_sample_integrity_async("discount", "current", "bid", "bid")
    ) == (False, ["Data mismatch for record: one"])
    session.close.assert_called_once_with()
    session.reset_mock()
    session.execute.side_effect = RuntimeError("query failed")
    assert asyncio.run(
        task._verify_sample_integrity_async("discount", "current", "bid", "bid")
    ) == (False, ["Integrity check error: query failed"])
    session.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("table", "source", "target", "expected"),
    [
        (
            "discount",
            {"discount_code": "CODE", "discount_value": "3"},
            {"code": "CODE", "value": 3.001},
            True,
        ),
        (
            "discount",
            {"discount_code": "CODE", "discount_value": "bad"},
            {"code": "CODE", "value": 3},
            False,
        ),
        ("ai_course_lesson_attend", {}, {"user_bid": "user"}, True),
        ("ai_course_lesson_attendscript", {}, {"user_bid": None}, False),
        ("ai_course_lesson_attendscript", {}, {}, False),
        ("discount_record", {}, {}, True),
    ],
)
def test_record_integrity_checks_critical_migrated_values(
    task: migration.UnifiedMigrationTask,
    table: str,
    source: dict,
    target: dict,
    expected: bool,
) -> None:
    assert (
        task._verify_record_mapping(
            table, SimpleNamespace(**source), SimpleNamespace(**target)
        )
        is expected
    )


def test_migration_report_includes_failures_recommendations_and_duration(
    task: migration.UnifiedMigrationTask,
) -> None:
    started = datetime(2026, 9, 20)
    result = migration.MigrationResult(
        "legacy", 10, 8, 2, started, started + timedelta(seconds=2), ["failed row"]
    )
    check = migration.ConsistencyCheckResult(
        "legacy -> current",
        10,
        8,
        sample_integrity_passed=False,
        data_mismatches=["missing row"],
    )
    report = task.generate_migration_report({"legacy": result}, {"legacy": check})
    for expected in (
        "Total Records: 10",
        "Successfully Migrated: 8",
        "Errors: 2",
        "Overall Success Rate: 80.00%",
        "Duration: 2.00s",
        "Mismatches: 1",
        "legacy: Review data mapping and re-run migration",
    ):
        assert expected in report
    empty = task.generate_migration_report({}, {})
    assert "Overall Success Rate: 0.00%" in empty
    assert "RECOMMENDATIONS" not in empty
