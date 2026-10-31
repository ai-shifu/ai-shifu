"""Copy a cached SQLite schema into test databases instead of rebuilding it.

Most backend test modules build their own Flask app and call
``db.create_all()`` for every test. On a file-backed SQLite database each
CREATE statement is a separate durable write, so a full schema costs about a
second per test. The schema itself never changes within a session, so it is
created once per worker in memory and copied with SQLite's backup API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.pool import StaticPool

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Hashable

    from flask_sqlalchemy import SQLAlchemy

_TEMPLATES: dict[Hashable, sqlite3.Connection] = {}


def _bind_keys(
    db: SQLAlchemy, bind_key: str | list[str | None] | None
) -> list[str | None]:
    """Resolve ``bind_key`` the way Flask-SQLAlchemy's ``create_all`` does."""
    if bind_key == "__all__":
        return list(db.metadatas)
    if bind_key is None or isinstance(bind_key, str):
        return [bind_key]
    return list(bind_key)


def _database_identity(engine: Engine) -> Hashable:
    """Name the database an engine writes to; in-memory engines are each their own.

    A named URI memory database is shared only with ``cache=shared``; with a
    private cache, each connection opens a separate database.
    """
    database = engine.url.database
    query = engine.url.query
    private_memory = query.get("mode") == "memory" and query.get("cache") != "shared"
    if (
        engine.dialect.name == "sqlite"
        and database not in (None, "", ":memory:")
        and not private_memory
    ):
        return ("file", database)
    return ("engine", id(engine))


def _template(members: list[tuple[str | None, MetaData]]) -> sqlite3.Connection:
    """Return an in-memory database holding the tables of every member metadata."""
    key = tuple(
        (bind_key, id(metadata), tuple(sorted(metadata.tables)))
        for bind_key, metadata in members
    )
    template = _TEMPLATES.get(key)
    if template is None:
        engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        for _, metadata in members:
            metadata.create_all(bind=engine)
        template = engine.raw_connection().driver_connection
        _TEMPLATES[key] = template
    return template


def create_all_from_template(
    self: SQLAlchemy, bind_key: str | list[str | None] | None = "__all__"
) -> None:
    """Behave like ``SQLAlchemy.create_all``, copying the schema when that is safe.

    A copy replaces the whole target, so it is used only for an empty SQLite
    database. Binds that share one database file are copied together. Any other
    target falls back to ``MetaData.create_all``.
    """
    groups: dict[Hashable, list[tuple[str | None, Engine, MetaData]]] = {}
    for key in _bind_keys(self, bind_key):
        engine = self.engines[key]
        groups.setdefault(_database_identity(engine), []).append(
            (key, engine, self.metadatas[key])
        )
    for members in groups.values():
        engine = members[0][1]
        raw = engine.raw_connection()
        try:
            target = raw.driver_connection
            empty = (
                engine.dialect.name == "sqlite"
                and target.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
                == 0
            )
            if empty:
                template = _template([(key, metadata) for key, _, metadata in members])
                template.backup(target)
        finally:
            raw.close()
        if not empty:
            for _, member_engine, metadata in members:
                metadata.create_all(bind=member_engine)
