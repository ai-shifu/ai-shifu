"""Exercise the data-only move from preview credentials to ordinary passwords."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flaskr.service.user.models import AuthCredential, UserInfo, UserToken
from flaskr.util.datetime import now_utc
from sqlalchemy import MetaData, Table, create_engine, event, select
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.engine import Connection, ExecutionContext


_MIGRATION = "0616c3b9e0a3_reuse_standard_passwords_for_.py"


def _revision(filename: str) -> object:
    path = Path(__file__).parents[2] / "migrations/versions" / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def migration_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Connection, object, dict[str, object]]]:
    engine = create_engine(f"sqlite:///{tmp_path / 'passwords.db'}")
    metadata = MetaData()
    tables = {
        "users": UserInfo.__table__.to_metadata(metadata),
        "credentials": AuthCredential.__table__.to_metadata(metadata),
        "sessions": UserToken.__table__.to_metadata(metadata),
    }
    migration = _revision(_MIGRATION)
    with engine.begin() as connection:
        for table in tables.values():
            table.create(connection)
        operations = Operations(MigrationContext.configure(connection))
        initial = _revision("b8e4a1d3c9f0_add_installation_bootstrap_state.py")
        contacts = _revision("207321e55031_use_contact_identifiers_for_local_.py")
        initial.op = contacts.op = migration.op = operations
        monkeypatch.setattr(initial.context, "get_x_argument", lambda **_kwargs: {})
        initial.upgrade()
        contacts.upgrade()
        bindings = Table(
            "user_local_admin_accounts", metadata, autoload_with=connection
        )
        tables["bindings"] = bindings
        yield connection, migration, tables
    engine.dispose()


def _account(
    connection: Connection,
    tables: dict[str, object],
    *,
    index: int = 1,
    kind: str = "email",
    deleted: int = 0,
) -> dict[str, object]:
    identifier = {
        "email": f"owner{index}@example.test",
        "phone": f"138{index:08d}",
        "legacy_username": f"old_owner{index}",
    }[kind]
    user_bid = f"migration-user-{index}"
    credential_bid = f"migration-credential-{index}"
    profile = {
        "provider": "local_password",
        "metadata": {"contact_verification": "unverified", "source": "fixture"},
        "password_hash": "public-migration-fixture",
        "extension": {"preserved": True},
    }
    connection.execute(
        tables["users"]
        .insert()
        .values(
            id=index,
            user_bid=user_bid,
            user_identify=f"local:{user_bid}",
            nickname="Preserved display name",
            is_operator=1,
            is_creator=1,
            state=1103,
            deleted=deleted,
        )
    )
    connection.execute(
        tables["credentials"]
        .insert()
        .values(
            id=index,
            credential_bid=credential_bid,
            user_bid=user_bid,
            provider_name="local_password",
            subject_id=identifier,
            subject_format="local_username"
            if kind == "legacy_username"
            else f"local_{kind}",
            identifier=identifier,
            raw_profile=json.dumps(profile),
            state=1202,
            deleted=deleted,
        )
    )
    connection.execute(
        tables["bindings"]
        .insert()
        .values(
            id=index,
            user_bid=user_bid,
            credential_bid=credential_bid,
            identifier=identifier,
            identifier_kind=kind,
            deleted=deleted,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
    )
    connection.execute(
        tables["sessions"]
        .insert()
        .values(
            id=index,
            user_id=user_bid,
            token=f"public-session-fixture-{index}",
            source="local_password",
        )
    )
    return {
        "identifier": identifier,
        "user_bid": user_bid,
        "credential_bid": credential_bid,
        "profile": profile,
    }


def _snapshot(connection: Connection, tables: dict[str, object]) -> dict[str, list]:
    return {
        name: [
            dict(row)
            for row in connection.execute(select(table).order_by(table.c.id)).mappings()
        ]
        for name, table in tables.items()
    }


@pytest.mark.parametrize("kind", ["email", "phone", "legacy_username"])
@pytest.mark.parametrize("deleted", [0, 1])
def test_upgrade_preserves_identity_credentials_roles_and_sessions(
    migration_database: tuple, kind: str, deleted: int
) -> None:
    connection, migration, tables = migration_database
    account = _account(connection, tables, kind=kind, deleted=deleted)
    before = _snapshot(connection, tables)
    migration.upgrade()
    after = _snapshot(connection, tables)
    expected_identity = (
        f"local:{account['user_bid']}"
        if kind == "legacy_username"
        else account["identifier"]
    )
    expected_user = {**before["users"][0], "user_identify": expected_identity}
    assert after["users"] == [expected_user]
    expected_credential = {
        **before["credentials"][0],
        "provider_name": "password",
        "subject_format": "local_username" if kind == "legacy_username" else kind,
    }
    expected_profile = {
        **account["profile"],
        "provider": "password",
        "metadata": {
            **account["profile"]["metadata"],
            "installation_admin": "true",
        },
    }
    actual_credential = after["credentials"][0]
    assert json.loads(actual_credential["raw_profile"]) == expected_profile
    expected_credential["raw_profile"] = actual_credential["raw_profile"]
    assert after["credentials"] == [expected_credential]
    assert after["sessions"] == before["sessions"]
    assert after["bindings"] == before["bindings"]
    # Restarting the data step never rotates or rewrites the password again.
    migration.upgrade()
    assert _snapshot(connection, tables) == after


def test_early_username_profiles_without_metadata_keep_their_password(
    migration_database: tuple,
) -> None:
    connection, migration, tables = migration_database
    _account(connection, tables, kind="legacy_username")
    connection.execute(
        tables["credentials"]
        .update()
        .values(raw_profile=json.dumps({"password_hash": "public-early-fixture"}))
    )
    migration.upgrade()
    credential = connection.execute(select(tables["credentials"])).mappings().one()
    profile = json.loads(credential["raw_profile"])
    assert profile["password_hash"] == "public-early-fixture"
    assert profile["metadata"] == {
        "installation_admin": "true",
        "contact_verification": "unverified",
    }


@pytest.mark.parametrize("source", ["canonical", "phone", "email", "password"])
def test_all_accounts_are_checked_before_any_identity_is_changed(
    migration_database: tuple, source: str
) -> None:
    connection, migration, tables = migration_database
    _account(connection, tables)
    second = _account(connection, tables, index=2)
    ordinary = "other-owner"
    connection.execute(
        tables["users"]
        .insert()
        .values(
            id=3,
            user_bid=ordinary,
            user_identify=(
                f" {second['identifier'].upper()} "
                if source == "canonical"
                else "other@example.test"
            ),
        )
    )
    if source != "canonical":
        connection.execute(
            tables["credentials"]
            .insert()
            .values(
                id=3,
                user_bid=ordinary,
                credential_bid="ordinary-credential",
                provider_name=source,
                identifier=f" {second['identifier'].upper()} ",
            )
        )
    before = _snapshot(connection, tables)
    statements = []

    def capture(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(connection, "before_cursor_execute", capture)
    with pytest.raises(RuntimeError, match="conflicting or incomplete") as error:
        migration.upgrade()
    event.remove(connection, "before_cursor_execute", capture)
    assert second["identifier"] not in str(error.value)
    assert "public-migration-fixture" not in str(error.value)
    assert not any(
        statement.lstrip().upper().startswith("UPDATE") for statement in statements
    )
    assert _snapshot(connection, tables) == before


@pytest.mark.parametrize(
    "damage",
    [
        "missing-user",
        "missing-credential",
        "wrong-credential-owner",
        "wrong-subject",
        "wrong-format",
        "wrong-identity",
        "unknown-kind",
        "noncanonical-contact",
        "invalid-profile",
        "nonobject-profile",
        "invalid-metadata",
        "missing-password",
        "second-password",
        "partial-conversion",
        "orphan-local-credential",
    ],
)
def test_damaged_bindings_fail_before_writing(
    migration_database: tuple, damage: str
) -> None:
    connection, migration, tables = migration_database
    _account(connection, tables)
    users = tables["users"]
    credentials = tables["credentials"]
    bindings = tables["bindings"]
    if damage == "missing-user":
        connection.execute(users.delete())
    elif damage == "missing-credential":
        connection.execute(credentials.delete())
    elif damage == "wrong-credential-owner":
        connection.execute(credentials.update().values(user_bid="different-user"))
    elif damage == "wrong-subject":
        connection.execute(
            credentials.update().values(subject_id="different@example.test")
        )
    elif damage == "wrong-format":
        connection.execute(credentials.update().values(subject_format="email"))
    elif damage == "wrong-identity":
        connection.execute(users.update().values(user_identify="other@example.test"))
    elif damage == "unknown-kind":
        connection.execute(bindings.update().values(identifier_kind="other"))
    elif damage == "noncanonical-contact":
        connection.execute(bindings.update().values(identifier="OWNER1@example.test"))
    elif damage == "invalid-profile":
        connection.execute(credentials.update().values(raw_profile="{"))
    elif damage == "nonobject-profile":
        connection.execute(credentials.update().values(raw_profile="[]"))
    elif damage == "invalid-metadata":
        connection.execute(
            credentials.update().values(
                raw_profile='{"password_hash":"fixture","metadata":[]}'
            )
        )
    elif damage == "missing-password":
        connection.execute(credentials.update().values(raw_profile="{}"))
    elif damage == "second-password":
        connection.execute(
            credentials.insert().values(
                id=2,
                credential_bid="conflicting-password",
                user_bid="migration-user-1",
                provider_name="password",
                identifier="owner1@example.test",
            )
        )
    elif damage == "partial-conversion":
        connection.execute(credentials.update().values(provider_name="password"))
    elif damage == "orphan-local-credential":
        connection.execute(bindings.delete())
    before = _snapshot(connection, tables)
    with pytest.raises(RuntimeError, match="conflicting or incomplete"):
        migration.upgrade()
    assert _snapshot(connection, tables) == before


def test_mid_conversion_failure_rolls_back_all_prior_account_changes(
    migration_database: tuple,
) -> None:
    connection, migration, tables = migration_database
    _account(connection, tables)
    _account(connection, tables, index=2)
    before = _snapshot(connection, tables)
    writes = []

    def fail_second_credential(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("UPDATE USER_AUTH_CREDENTIALS"):
            writes.append(statement)
            if len(writes) == 2:
                message = "synthetic migration write failure"
                raise SQLAlchemyError(message)

    event.listen(connection, "before_cursor_execute", fail_second_credential)
    with pytest.raises(SQLAlchemyError, match="synthetic migration write failure"):
        migration.upgrade()
    event.remove(connection, "before_cursor_execute", fail_second_credential)
    assert len(writes) == 2
    assert _snapshot(connection, tables) == before


@pytest.mark.parametrize("method", ["upgrade", "downgrade"])
def test_offline_modes_refuse_without_data_checks(method: str) -> None:
    migration = _revision(_MIGRATION)
    output = io.StringIO()
    migration.op = Operations(
        MigrationContext.configure(
            dialect_name="mysql", opts={"as_sql": True, "output_buffer": output}
        )
    )
    with pytest.raises(RuntimeError, match="requires online account checks"):
        getattr(migration, method)()
    assert output.getvalue() == ""


@pytest.mark.parametrize("converted", [False, True])
def test_downgrade_refuses_account_bindings_before_modifying_any_data(
    migration_database: tuple, converted: bool
) -> None:
    connection, migration, tables = migration_database
    _account(connection, tables)
    if converted:
        migration.upgrade()
    before = _snapshot(connection, tables)
    with pytest.raises(RuntimeError, match="Cannot downgrade installation password"):
        migration.downgrade()
    assert _snapshot(connection, tables) == before


def test_empty_installation_upgrade_and_downgrade_leave_ordinary_accounts_intact(
    migration_database: tuple,
) -> None:
    connection, migration, tables = migration_database
    connection.execute(
        tables["users"]
        .insert()
        .values(
            user_bid="ordinary-user",
            user_identify="ordinary@example.test",
            is_operator=0,
        )
    )
    connection.execute(
        tables["credentials"]
        .insert()
        .values(
            credential_bid="ordinary-credential",
            user_bid="ordinary-user",
            identifier="ordinary@example.test",
            provider_name="password",
            raw_profile='{"password_hash":"public-ordinary-fixture"}',
        )
    )
    before = _snapshot(connection, tables)
    migration.upgrade()
    migration.downgrade()
    assert _snapshot(connection, tables) == before


def test_mysql_statements_are_only_locked_reads_and_data_updates(
    migration_database: tuple,
) -> None:
    connection, migration, tables = migration_database
    _account(connection, tables)
    statements = []

    def capture(
        _connection: Connection,
        _cursor: object,
        _statement: str,
        _parameters: object,
        context: ExecutionContext,
        _executemany: bool,
    ) -> None:
        if context.compiled is not None:
            statements.append(
                str(context.compiled.statement.compile(dialect=mysql.dialect()))
            )

    event.listen(connection, "before_cursor_execute", capture)
    migration.upgrade()
    event.remove(connection, "before_cursor_execute", capture)
    reads = [statement for statement in statements if statement.startswith("SELECT")]
    writes = [statement for statement in statements if statement.startswith("UPDATE")]
    assert reads
    assert all("FOR UPDATE" in statement for statement in reads)
    assert len(writes) == 2
    assert "UPDATE user_users SET user_identify=" in writes[0]
    assert "UPDATE user_auth_credentials SET provider_name=" in writes[1]
    assert all(
        "DROP " not in statement and "ALTER " not in statement
        for statement in statements
    )
