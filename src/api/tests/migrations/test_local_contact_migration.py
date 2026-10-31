"""Keep pre-release local bindings intact when contact login labels are introduced."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flaskr.util.datetime import now_utc
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def _revision(filename: str) -> object:
    path = Path(__file__).parents[2] / "migrations/versions" / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("named_constraint", [False, True])
def test_legacy_local_binding_survives_upgrade_and_safe_downgrade(
    tmp_path: Path,
    named_constraint: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _revision("b8e4a1d3c9f0_add_installation_bootstrap_state.py")
    new = _revision("207321e55031_use_contact_identifiers_for_local_.py")
    engine = create_engine(f"sqlite:///{tmp_path / 'contacts.db'}")
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        old.op = new.op = operations
        monkeypatch.setattr(old.context, "get_x_argument", lambda **_kwargs: {})
        old.upgrade()
        if named_constraint:
            with operations.batch_alter_table(
                "user_local_admin_accounts",
                recreate="always",
                naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"},
            ):
                pass
        connection.execute(
            text(
                "INSERT INTO user_local_admin_accounts VALUES (1,'old_owner','user-bid','credential-bid',0,:timestamp,:timestamp)"
            ),
            {"timestamp": now_utc()},
        )
        new.upgrade()
        row = (
            connection.execute(text("SELECT * FROM user_local_admin_accounts"))
            .mappings()
            .one()
        )
        assert row["identifier"] == "old_owner"
        assert row["identifier_kind"] == "legacy_username"
        assert row["user_bid"] == "user-bid"
        assert row["credential_bid"] == "credential-bid"
        assert row["id"] == 1
        assert any(
            item["column_names"] == ["identifier"]
            for item in inspect(connection).get_unique_constraints(
                "user_local_admin_accounts"
            )
        )
        new.downgrade()
        assert (
            connection.execute(
                text("SELECT username FROM user_local_admin_accounts")
            ).scalar_one()
            == "old_owner"
        )
    engine.dispose()


@pytest.mark.parametrize("kind", ["email", "phone"])
def test_contact_downgrade_refuses_before_altering_any_column(
    tmp_path: Path, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _revision("b8e4a1d3c9f0_add_installation_bootstrap_state.py")
    new = _revision("207321e55031_use_contact_identifiers_for_local_.py")
    engine = create_engine(f"sqlite:///{tmp_path / 'contacts.db'}")
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        old.op = new.op = operations
        monkeypatch.setattr(old.context, "get_x_argument", lambda **_kwargs: {})
        old.upgrade()
        new.upgrade()
        identifier = "owner@example.com" if kind == "email" else "13800138000"
        connection.execute(
            text(
                "INSERT INTO user_local_admin_accounts VALUES (1,:identifier,'user-bid','credential-bid',0,:timestamp,:timestamp,:kind)"
            ),
            {"identifier": identifier, "timestamp": now_utc(), "kind": kind},
        )
        with pytest.raises(
            RuntimeError, match="Cannot downgrade contact administrator"
        ):
            new.downgrade()
        assert "identifier_kind" in {
            col["name"]
            for col in inspect(connection).get_columns("user_local_admin_accounts")
        }
        assert (
            connection.execute(
                text("SELECT identifier FROM user_local_admin_accounts")
            ).scalar_one()
            == identifier
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO user_local_admin_accounts VALUES (2,:identifier,'other-user','other-credential',0,:timestamp,:timestamp,:kind)"
                ),
                {"identifier": identifier, "timestamp": now_utc(), "kind": kind},
            )
    engine.dispose()


def test_mysql_upgrade_renames_without_dropping_existing_bindings_or_unique_indexes() -> (
    None
):
    new = _revision("207321e55031_use_contact_identifiers_for_local_.py")
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="mysql", opts={"as_sql": True, "output_buffer": output}
    )
    new.op = Operations(context)
    new.upgrade()
    ddl = output.getvalue()
    assert "CHANGE username identifier VARCHAR(255) NOT NULL" in ddl
    assert "DEFAULT 'legacy_username'" in ddl
    assert "DROP" not in ddl
    assert "DELETE" not in ddl
