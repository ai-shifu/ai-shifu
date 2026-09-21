"""Exercise operator command output, failure exit codes and resource cleanup."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from flask import Flask
from flaskr import command as commands
from flaskr.common import config as config_module


@pytest.fixture
def console_app(monkeypatch: pytest.MonkeyPatch) -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    monkeypatch.setattr(commands, "register_billing_commands", Mock())
    monkeypatch.setattr(commands, "register_shifu_commands", Mock())
    monkeypatch.setattr(commands, "setup_migration_logging", Mock())
    monkeypatch.setattr(
        config_module,
        "get_config",
        lambda: SimpleNamespace(SQLALCHEMY_DATABASE_URI="sqlite://"),
    )
    commands.enable_commands(app)
    return app


@pytest.fixture
def migration(monkeypatch: pytest.MonkeyPatch) -> Mock:
    task = Mock()
    task.table_mappings = {"legacy": {"target": "current"}}
    task.migrate_all_tables = AsyncMock(
        return_value={
            "legacy": SimpleNamespace(
                success_rate=100.0, synced_records=10, total_records=10
            )
        }
    )
    task.verify_data_consistency = AsyncMock(
        return_value={
            "legacy": SimpleNamespace(
                is_consistent=True,
                table_pair="legacy -> current",
                old_count=10,
                new_count=10,
                data_mismatches=[],
            )
        }
    )
    task.generate_migration_report.return_value = "Migration report body"
    monkeypatch.setattr(commands, "UnifiedMigrationTask", Mock(return_value=task))
    return task


def test_migrate_dry_run_lists_configuration_without_writing(
    console_app: Flask, migration: Mock
) -> None:
    result = console_app.test_cli_runner().invoke(
        args=[
            "console",
            "migrate",
            "--dry-run",
            "--force-full",
            "--batch-size",
            "12",
            "--max-workers",
            "2",
        ]
    )
    assert result.exit_code == 0, result.output
    assert "DRY RUN MODE" in result.output
    assert "legacy -> current" in result.output
    assert "Batch size: 12" in result.output
    assert "Max workers: 2" in result.output
    assert "Force full: True" in result.output
    assert migration.force_full_migration
    migration.migrate_all_tables.assert_not_called()
    migration.verify_data_consistency.assert_not_called()
    migration.close.assert_called_once_with()


@pytest.mark.parametrize("output_file", [False, True])
def test_migrate_reports_success_and_closes_resources(
    console_app: Flask, migration: Mock, tmp_path: Path, output_file: bool
) -> None:
    target = tmp_path / "migration.txt"
    args = ["console", "migrate"]
    if output_file:
        args.extend(["--output-file", str(target)])
    result = console_app.test_cli_runner().invoke(args=args)
    assert result.exit_code == 0, result.output
    assert "Migration completed: 10/10 records (100.0%)" in result.output
    if output_file:
        assert target.read_text(encoding="utf-8") == "Migration report body"
        assert "Migration report saved to:" in result.output
    else:
        assert "Migration report body" in result.output
    migration.migrate_all_tables.assert_awaited_once()
    migration.verify_data_consistency.assert_awaited_once()
    migration.generate_migration_report.assert_called_once_with(
        migration.migrate_all_tables.return_value,
        migration.verify_data_consistency.return_value,
    )
    migration.close.assert_called_once_with()


@pytest.mark.parametrize(("rate", "exit_code"), [(94.9, 1), (95.0, 0)])
def test_migrate_failure_threshold_controls_exit_status(
    console_app: Flask, migration: Mock, rate: float, exit_code: int
) -> None:
    migration.migrate_all_tables.return_value["legacy"].success_rate = rate
    result = console_app.test_cli_runner().invoke(args=["console", "migrate"])
    assert result.exit_code == exit_code
    assert ("Migration failed for tables: legacy (94.9%)" in result.output) is bool(
        exit_code
    )
    migration.close.assert_called_once_with()


def test_migrate_warns_on_inconsistent_counts_and_handles_empty_source(
    console_app: Flask, migration: Mock
) -> None:
    migration.migrate_all_tables.return_value["legacy"] = SimpleNamespace(
        success_rate=100.0, synced_records=0, total_records=0
    )
    migration.verify_data_consistency.return_value["legacy"].is_consistent = False
    result = console_app.test_cli_runner().invoke(args=["console", "migrate"])
    assert result.exit_code == 0
    assert "Consistency check failed for: legacy" in result.output
    assert "Migration completed: 0/0 records (0.0%)" in result.output


@pytest.mark.parametrize(
    "stage",
    ["migrate_all_tables", "verify_data_consistency", "generate_migration_report"],
)
def test_migrate_surfaces_stage_failure_and_always_closes(
    console_app: Flask, migration: Mock, stage: str
) -> None:
    getattr(migration, stage).side_effect = RuntimeError("task unavailable")
    result = console_app.test_cli_runner().invoke(args=["console", "migrate"])
    assert result.exit_code == 1
    assert "Migration failed: task unavailable" in result.output
    migration.close.assert_called_once_with()


@pytest.mark.parametrize("operation", ["migrate", "verify", "status"])
def test_initialization_failures_are_reported_without_unbound_cleanup(
    console_app: Flask, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    monkeypatch.setattr(
        commands,
        "UnifiedMigrationTask",
        Mock(side_effect=RuntimeError("invalid database")),
    )
    monkeypatch.setattr(commands, "create_engine", Mock())
    result = console_app.test_cli_runner().invoke(args=["console", operation])
    assert result.exit_code == 1
    assert "invalid database" in result.output


@pytest.mark.parametrize("consistent", [False, True])
def test_verify_reports_each_table_and_mismatches(
    console_app: Flask, migration: Mock, consistent: bool
) -> None:
    record = migration.verify_data_consistency.return_value["legacy"]
    record.is_consistent = consistent
    record.data_mismatches = [] if consistent else ["value differs"]
    result = console_app.test_cli_runner().invoke(args=["console", "verify"])
    assert result.exit_code == 0
    assert "legacy -> current" in result.output
    assert "Count: 10 -> 10" in result.output
    if consistent:
        assert "All consistency checks passed!" in result.output
    else:
        assert "Mismatches: 1" in result.output
        assert "Some consistency checks failed." in result.output
    migration.close.assert_called_once_with()


def test_verify_reports_exception_and_closes(
    console_app: Flask, migration: Mock
) -> None:
    migration.verify_data_consistency.side_effect = RuntimeError("query failed")
    result = console_app.test_cli_runner().invoke(args=["console", "verify"])
    assert result.exit_code == 1
    assert "Verification failed: query failed" in result.output
    migration.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("source_count", "target_count"), [(0, 0), (100, 100), (100, 75), (100, 20)]
)
def test_status_reports_counts_and_percentages(
    console_app: Flask,
    migration: Mock,
    monkeypatch: pytest.MonkeyPatch,
    source_count: int,
    target_count: int,
) -> None:
    migration._get_table_count.side_effect = [source_count, target_count]
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = []
    engine = Mock()
    engine.connect.return_value.__enter__ = Mock(return_value=connection)
    engine.connect.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(commands, "create_engine", Mock(return_value=engine))
    result = console_app.test_cli_runner().invoke(args=["console", "status"])
    assert result.exit_code == 0, result.output
    percentage = target_count / source_count * 100 if source_count else 0
    assert (
        f"Records: {target_count}/{source_count} ({percentage:.1f}%)" in result.output
    )
    assert "No migration activity recorded." in result.output
    assert migration._get_table_count.call_args_list[1].args == (
        "current",
        "deleted = 0",
    )
    migration.close.assert_called_once_with()


@pytest.mark.parametrize("log_fails", [False, True])
def test_status_isolates_table_count_and_log_failures(
    console_app: Flask,
    migration: Mock,
    monkeypatch: pytest.MonkeyPatch,
    log_fails: bool,
) -> None:
    migration._get_table_count.side_effect = RuntimeError("table absent")
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = [
        SimpleNamespace(
            sync_type="legacy",
            last_sync="2026-09-20",
            last_synced_id=None,
            last_id=None,
        ),
        SimpleNamespace(sync_type="other", last_sync="2026-09-20", last_id=12),
    ]
    engine = Mock()
    engine.connect.return_value.__enter__ = Mock(return_value=connection)
    engine.connect.return_value.__exit__ = Mock(return_value=False)
    if log_fails:
        connection.execute.side_effect = RuntimeError("log absent")
    monkeypatch.setattr(commands, "create_engine", Mock(return_value=engine))
    result = console_app.test_cli_runner().invoke(args=["console", "status"])
    assert result.exit_code == 0, result.output
    assert "Error: table absent" in result.output
    if log_fails:
        assert "Could not read migration log: log absent" in result.output
    else:
        assert "Last Migration Activity:" in result.output
        assert "legacy: 2026-09-20 (ID: N/A)" in result.output
        assert "other: 2026-09-20 (ID: 12)" in result.output
    migration.close.assert_called_once_with()


@pytest.mark.parametrize(
    "outcome", ["success", "partial", RuntimeError("export unavailable")]
)
def test_export_command_reports_service_outcome(
    console_app: Flask, monkeypatch: pytest.MonkeyPatch, outcome: object
) -> None:
    export = Mock(return_value=outcome)
    if isinstance(outcome, Exception):
        export.side_effect = outcome
    monkeypatch.setattr(commands, "export_shifu", export)
    result = console_app.test_cli_runner().invoke(
        args=["console", "export_shifu", "course", "course.json"]
    )
    export.assert_called_once_with(console_app, "course", "course.json")
    if isinstance(outcome, Exception):
        assert result.exit_code == 1
        assert "Export failed: export unavailable" in result.output
    elif outcome == "success":
        assert result.exit_code == 0
        assert "Shifu exported successfully" in result.output
    else:
        assert result.exit_code == 0
        assert "Export completed with message: partial" in result.output


@pytest.mark.parametrize("existing", [None, "course"])
def test_import_preserves_file_bytes_and_course_target(
    console_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    existing: str | None,
) -> None:
    file_path = tmp_path / "course.json"
    file_path.write_bytes(b'{"course": "example"}')

    def importer(app: Flask, course: str | None, upload: object, user: str) -> str:
        assert app is console_app
        assert course == existing
        assert user == "teacher"
        assert upload.filename == "course.json"
        assert upload.read() == file_path.read_bytes()
        return existing or "new-course"

    monkeypatch.setattr(commands, "import_shifu", importer)
    args = ["console", "import_shifu", str(file_path), "--user-id", "teacher"]
    if existing:
        args.extend(["--shifu-id", existing])
    result = console_app.test_cli_runner().invoke(args=args)
    assert result.exit_code == 0, result.output
    assert (
        "updated successfully"
        if existing
        else "New shifu new-course created successfully"
    ) in result.output


@pytest.mark.parametrize("exists", [False, True])
def test_import_reports_missing_file_or_service_error(
    console_app: Flask, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, exists: bool
) -> None:
    file_path = tmp_path / "course.json"
    if exists:
        file_path.write_text("{}", encoding="utf-8")
    importer = Mock(side_effect=ValueError("invalid course"))
    monkeypatch.setattr(commands, "import_shifu", importer)
    result = console_app.test_cli_runner().invoke(
        args=["console", "import_shifu", str(file_path), "--user-id", "teacher"]
    )
    assert result.exit_code == 1
    assert (
        "Import failed: invalid course" if exists else "File not found:"
    ) in result.output
    assert importer.call_count == int(exists)


def test_user_import_and_demo_commands_forward_to_services(
    console_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    import_user = Mock()
    update_demo = Mock()
    monkeypatch.setattr(commands, "import_user", import_user)
    monkeypatch.setattr(commands, "update_demo_shifu", update_demo)
    runner = console_app.test_cli_runner()
    result = runner.invoke(
        args=["console", "import_user", "test-mobile", "course", "coupon", "name"]
    )
    assert result.exit_code == 0
    import_user.assert_called_once_with(
        console_app, "test-mobile", "course", "coupon", "name"
    )
    result = runner.invoke(args=["console", "update_demo_shifu"])
    assert result.exit_code == 0
    update_demo.assert_called_once_with(console_app)
