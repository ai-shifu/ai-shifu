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


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "test_learner_profile_migration_module",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_learner_profile_column_remains_nullable_for_rolling_writers():
    from flaskr.service.user.models import UserInfo

    migration = _load_migration_module()
    added_columns = []
    altered_columns = []
    executed_statements = []

    class _BatchOperations:
        def add_column(self, column):
            added_columns.append(column)

        def alter_column(self, column_name, **kwargs):
            altered_columns.append((column_name, kwargs))

    class _Operations:
        @contextmanager
        def batch_alter_table(self, *_args, **_kwargs):
            yield _BatchOperations()

        def execute(self, statement):
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


def test_learner_profile_revision_extends_the_existing_main_head():
    migration = _load_migration_module()

    assert migration.revision == "c8f1a2d3e4b5"
    assert migration.down_revision == "b8d5f0a2c3e4"
