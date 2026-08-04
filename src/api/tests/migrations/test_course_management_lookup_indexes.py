import importlib

import pytest
from sqlalchemy.exc import SQLAlchemyError


MIGRATION_MODULE = (
    "migrations.versions.c4f6a8b0d2e3_add_course_management_lookup_indexes"
)


def _migration():
    return importlib.import_module(MIGRATION_MODULE)


class _BatchRecorder:
    def __init__(self, table_name: str, calls: list[tuple[str, str, tuple[str, ...]]]):
        self._table_name = table_name
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def create_index(self, index_name, columns, unique=False):
        self._calls.append(("create", index_name, tuple(columns)))

    def drop_index(self, index_name):
        self._calls.append(("drop", index_name, (self._table_name,)))


def test_upgrade_creates_all_course_management_indexes(monkeypatch):
    migration = _migration()
    calls: list[tuple[str, str, tuple[str, ...]]] = []

    monkeypatch.setattr(migration, "_table_exists", lambda _table_name: True)
    monkeypatch.setattr(
        migration, "_index_exists", lambda _table_name, _index_name: False
    )
    monkeypatch.setattr(
        migration.op,
        "batch_alter_table",
        lambda table_name, schema=None: _BatchRecorder(table_name, calls),
    )

    migration.upgrade()

    assert calls == [
        ("create", index_name, tuple(columns))
        for _table_name, index_name, columns in migration.INDEXES
    ]


def test_upgrade_is_idempotent_when_indexes_already_exist(monkeypatch):
    migration = _migration()
    calls: list[tuple[str, str, tuple[str, ...]]] = []

    monkeypatch.setattr(migration, "_table_exists", lambda _table_name: True)
    monkeypatch.setattr(
        migration, "_index_exists", lambda _table_name, _index_name: True
    )
    monkeypatch.setattr(
        migration.op,
        "batch_alter_table",
        lambda table_name, schema=None: _BatchRecorder(table_name, calls),
    )

    migration.upgrade()

    assert calls == []


def test_downgrade_drops_all_course_management_indexes(monkeypatch):
    migration = _migration()
    calls: list[tuple[str, str, tuple[str, ...]]] = []

    monkeypatch.setattr(migration, "_table_exists", lambda _table_name: True)
    monkeypatch.setattr(
        migration, "_index_exists", lambda _table_name, _index_name: True
    )
    monkeypatch.setattr(
        migration.op,
        "batch_alter_table",
        lambda table_name, schema=None: _BatchRecorder(table_name, calls),
    )

    migration.downgrade()

    assert calls == [
        ("drop", index_name, (table_name,))
        for table_name, index_name, _columns in reversed(migration.INDEXES)
    ]


def test_downgrade_is_idempotent_when_indexes_are_absent(monkeypatch):
    migration = _migration()
    calls: list[tuple[str, str, tuple[str, ...]]] = []

    monkeypatch.setattr(migration, "_table_exists", lambda _table_name: True)
    monkeypatch.setattr(
        migration, "_index_exists", lambda _table_name, _index_name: False
    )
    monkeypatch.setattr(
        migration.op,
        "batch_alter_table",
        lambda table_name, schema=None: _BatchRecorder(table_name, calls),
    )

    migration.downgrade()

    assert calls == []


def test_index_lookup_failure_is_not_silenced(monkeypatch):
    migration = _migration()

    class _Inspector:
        def get_indexes(self, table_name):
            raise SQLAlchemyError(f"cannot inspect {table_name}")

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: _Inspector())

    with pytest.raises(SQLAlchemyError):
        migration._index_exists("shifu_draft_shifus", "idx_missing")
