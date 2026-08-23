"""Protect learner-profile rolling-upgrade compatibility."""

from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateColumn

API_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    API_ROOT
    / "migrations"
    / "versions"
    / "c8f1a2d3e4b5_add_learner_profile_to_users.py"
)
MERGE_MIGRATION_PATH = (
    API_ROOT
    / "migrations"
    / "versions"
    / "f9a2b3c4d5e6_merge_learner_profile_and_tts_provider_heads.py"
)


def _load_migration_module(path: object = MIGRATION_PATH):
    spec = importlib.util.spec_from_file_location(
        "test_learner_profile_migration_module",
        path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_learner_profile_column_remains_nullable_for_rolling_writers() -> None:
    from flaskr.service.user.models import UserInfo

    migration = _load_migration_module()
    added_columns = []
    altered_columns = []
    executed_statements = []

    class _BatchOperations:
        def add_column(self, column: object):
            added_columns.append(column)

        def alter_column(self, column_name: object, **kwargs: object):
            altered_columns.append((column_name, kwargs))

    class _Operations:
        @contextmanager
        def batch_alter_table(self, *_args: object, **_kwargs: object):
            yield _BatchOperations()

        def execute(self, statement: object):
            executed_statements.append(str(statement))

    migration.op = _Operations()

    migration.upgrade()

    profile_column = next(
        column for column in added_columns if column.name == "learner_profile"
    )
    mysql_ddl = str(CreateColumn(profile_column).compile(dialect=mysql.dialect()))
    assert profile_column.nullable is True
    assert profile_column.server_default is None
    assert " DEFAULT " not in mysql_ddl.upper()
    assert executed_statements == []
    assert altered_columns == []
    assert UserInfo.__table__.c.learner_profile.nullable is True


def test_learner_profile_revision_extends_the_existing_main_head() -> None:
    migration = _load_migration_module()

    assert migration.revision == "c8f1a2d3e4b5"
    assert migration.down_revision == "b8d5f0a2c3e4"


def test_merge_revision_joins_learner_profile_and_tts_provider_heads() -> None:
    migration = _load_migration_module(MERGE_MIGRATION_PATH)

    assert migration.revision == "f9a2b3c4d5e6"
    assert migration.down_revision == ("c8f1a2d3e4b5", "e7b3c9d1f5a2")
