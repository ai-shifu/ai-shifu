"""The session-wide create_all patch must build exactly what create_all builds."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flaskr import dao
from flaskr.service.billing import models as billing_models
from flaskr.service.order import models as order_models
from flaskr.service.user import models as user_models
from sqlalchemy import text

from tests.common.fixtures.db_template import create_all_from_template

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# Importing the model modules registers their tables on dao.db's metadata.
_MODELS = (billing_models, order_models, user_models)


def _app(default_uri: str, bind_uri: str) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=default_uri,
        SQLALCHEMY_BINDS={"ai_shifu_saas": bind_uri, "ai_shifu_admin": bind_uri},
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    dao.db.init_app(app)
    return app


def _schema(path: Path) -> list[tuple[str, str, str, str | None]]:
    with sqlite3.connect(path) as connection:
        return connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()


def _real_create_all(db: SQLAlchemy) -> None:
    for key, metadata in db.metadatas.items():
        metadata.create_all(bind=db.engines[key])


@pytest.fixture
def file_app(tmp_path: Path) -> Iterator[tuple[Flask, Path]]:
    path = tmp_path / "copy.sqlite"
    uri = f"sqlite:///{path}"
    app = _app(uri, uri)
    with app.app_context():
        yield app, path
        dao.db.session.remove()
        for engine in dao.db.engines.values():
            engine.dispose()


def test_the_session_patch_is_installed() -> None:
    assert SQLAlchemy.create_all is create_all_from_template


def test_a_copied_schema_matches_a_real_create_all(
    file_app: tuple[Flask, Path], tmp_path: Path
) -> None:
    _, copied = file_app
    dao.db.create_all()

    built = tmp_path / "built.sqlite"
    uri = f"sqlite:///{built}"
    with _app(uri, uri).app_context():
        _real_create_all(dao.db)
        for engine in dao.db.engines.values():
            engine.dispose()

    assert len(_schema(copied)) > 50
    assert _schema(copied) == _schema(built)


def test_a_database_with_tables_falls_back_and_keeps_its_rows(
    file_app: tuple[Flask, Path],
) -> None:
    _, path = file_app
    with dao.db.engine.begin() as connection:
        connection.execute(text("CREATE TABLE kept (value TEXT)"))
        connection.execute(text("INSERT INTO kept VALUES ('row')"))

    dao.db.create_all()

    with dao.db.engine.connect() as connection:
        assert connection.execute(text("SELECT value FROM kept")).scalar() == "row"
    names = {row[1] for row in _schema(path)}
    assert set(dao.db.metadatas[None].tables) <= names


def test_in_memory_binds_each_receive_their_own_tables() -> None:
    app = _app("sqlite:///:memory:", "sqlite:///:memory:")
    with app.app_context():
        dao.db.create_all()
        for key, metadata in dao.db.metadatas.items():
            with dao.db.engines[key].connect() as connection:
                names = {
                    row[0]
                    for row in connection.execute(
                        text("SELECT name FROM sqlite_master WHERE type = 'table'")
                    )
                }
            assert set(metadata.tables) <= names
        dao.db.session.remove()


_local_db = SQLAlchemy()


class _DefaultRow(_local_db.Model):
    __tablename__ = "template_default_row"
    id = _local_db.Column(_local_db.Integer, primary_key=True)


class _BoundRow(_local_db.Model):
    __bind_key__ = "extra"
    __tablename__ = "template_bound_row"
    id = _local_db.Column(_local_db.Integer, primary_key=True)
    name = _local_db.Column(_local_db.String(20), index=True)


def _local_app(default_uri: str, bind_uri: str) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=default_uri,
        SQLALCHEMY_BINDS={"extra": bind_uri},
    )
    _local_db.init_app(app)
    return app


def test_binds_sharing_one_file_are_copied_together(tmp_path: Path) -> None:
    path = tmp_path / "shared.sqlite"
    uri = f"sqlite:///{path}"
    with _local_app(uri, uri).app_context():
        _local_db.create_all()
        for engine in _local_db.engines.values():
            engine.dispose()
    names = {row[1] for row in _schema(path)}
    assert {
        "template_default_row",
        "template_bound_row",
        "ix_template_bound_row_name",
    } <= names


def test_binds_on_separate_files_each_receive_only_their_tables(
    tmp_path: Path,
) -> None:
    default, extra = tmp_path / "default.sqlite", tmp_path / "extra.sqlite"
    with _local_app(f"sqlite:///{default}", f"sqlite:///{extra}").app_context():
        _local_db.create_all()
        for engine in _local_db.engines.values():
            engine.dispose()
    assert {row[1] for row in _schema(default)} == {"template_default_row"}
    assert {row[1] for row in _schema(extra)} == {
        "template_bound_row",
        "ix_template_bound_row_name",
    }
