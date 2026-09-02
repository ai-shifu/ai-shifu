"""Verify the user-avatar storage migration."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

API_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    API_ROOT
    / "migrations"
    / "versions"
    / "6d568133dd29_expand_user_avatar_url_storage.py"
)


def _load_migration_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "test_user_avatar_migration_module",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_downgrade_rejects_oversized_avatar_without_changing_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    user_users = sa.Table(
        "user_users",
        metadata,
        sa.Column("avatar", sa.Text(), nullable=False),
    )
    oversized_avatar = "a" * 256

    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(user_users.insert().values(avatar=oversized_avatar))
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)

        with pytest.raises(RuntimeError, match="avatar exceeds 255 characters"):
            migration.downgrade()

        stored_avatar = connection.execute(sa.select(user_users.c.avatar)).scalar_one()
        assert stored_avatar == oversized_avatar

    engine.dispose()
