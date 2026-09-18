"""Exercise the course-only settings migration with populated outline tables."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_migration_preserves_course_settings_and_outline_content() -> None:
    path = (
        Path(__file__).resolve().parents[3]
        / "migrations/versions/fde432bceab4_remove_outline_model_settings.py"
    )
    spec = importlib.util.spec_from_file_location("course_settings_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    for name in migration._TABLES:
        sa.Table(
            name,
            metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("content", sa.Text, nullable=False),
            *(
                sa.Column(column, sa.String, nullable=False)
                for column in migration._COLUMNS
            ),
        )
    for name in ("shifu_draft_shifus", "shifu_published_shifus"):
        sa.Table(
            name,
            metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("llm", sa.String),
            sa.Column("ask_llm", sa.String),
            sa.Column("ask_enabled_status", sa.Integer),
            sa.Column("llm_system_prompt", sa.Text),
        )
    with engine.begin() as connection:
        metadata.create_all(connection)
        for name in migration._TABLES:
            connection.execute(
                metadata.tables[name]
                .insert()
                .values(
                    id=1,
                    content="Keep lesson content",
                    **dict.fromkeys(migration._COLUMNS, "old-setting"),
                )
            )
        for name in ("shifu_draft_shifus", "shifu_published_shifus"):
            connection.execute(
                metadata.tables[name]
                .insert()
                .values(
                    id=1,
                    llm="course-main",
                    ask_llm="course-ask",
                    ask_enabled_status=5102,
                    llm_system_prompt="Course prompt",
                )
            )
        with Operations.context(MigrationContext.configure(connection)):
            # Downgrading a populated table must work; upgrading again stays clean.
            for _ in range(2):
                migration.upgrade()
                for name in migration._TABLES:
                    assert {
                        c["name"] for c in sa.inspect(connection).get_columns(name)
                    } == {"id", "content"}
                    assert (
                        connection.execute(
                            sa.select(metadata.tables[name].c.content)
                        ).scalar_one()
                        == "Keep lesson content"
                    )
                for name in ("shifu_draft_shifus", "shifu_published_shifus"):
                    row = (
                        connection.execute(metadata.tables[name].select())
                        .mappings()
                        .one()
                    )
                    assert dict(row) == {
                        "id": 1,
                        "llm": "course-main",
                        "ask_llm": "course-ask",
                        "ask_enabled_status": 5102,
                        "llm_system_prompt": "Course prompt",
                    }
                migration.downgrade()
                for name in migration._TABLES:
                    columns = sa.inspect(connection).get_columns(name)
                    assert {c["name"] for c in columns} == {
                        "id",
                        "content",
                        *migration._COLUMNS,
                    }
                    assert all(not c["nullable"] for c in columns)
                    row = connection.execute(
                        sa.select(
                            metadata.tables[name].c.llm,
                            metadata.tables[name].c.ask_llm,
                            metadata.tables[name].c.ask_enabled_status,
                        )
                    ).one()
                    assert tuple(row) == ("", "", 5101)
    engine.dispose()
