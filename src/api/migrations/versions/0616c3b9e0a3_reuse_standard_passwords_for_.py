"""Reuse standard passwords for installation administrators.

Revision ID: 0616c3b9e0a3
Revises: 207321e55031
Create Date: 2026-10-26 06:21:02.971731 UTC

Generated with flask db revision. This is a data-only revision: existing
models and columns are unchanged. Stop application writers before upgrading.
"""

import json
import re

from alembic import op
import sqlalchemy as sa


revision = "0616c3b9e0a3"
down_revision = "207321e55031"
branch_labels = None
depends_on = None

_ERROR = (
    "Installation password migration found conflicting or incomplete account data. "
    "Stop application writers, reconcile installation account bindings with ordinary "
    "accounts, and retry. No account is merged or overwritten automatically."
)


def _tables():
    bindings = sa.table(
        "user_local_admin_accounts",
        sa.column("id", sa.Integer),
        sa.column("identifier", sa.String),
        sa.column("identifier_kind", sa.String),
        sa.column("user_bid", sa.String),
        sa.column("credential_bid", sa.String),
    )
    users = sa.table(
        "user_users",
        sa.column("id", sa.Integer),
        sa.column("user_bid", sa.String),
        sa.column("user_identify", sa.String),
    )
    credentials = sa.table(
        "user_auth_credentials",
        sa.column("id", sa.Integer),
        sa.column("credential_bid", sa.String),
        sa.column("user_bid", sa.String),
        sa.column("provider_name", sa.String),
        sa.column("subject_id", sa.String),
        sa.column("subject_format", sa.String),
        sa.column("identifier", sa.String),
        sa.column("raw_profile", sa.Text),
    )
    return bindings, users, credentials


def _fail():
    raise RuntimeError(_ERROR)


def _one(bind, statement):
    rows = bind.execute(statement.with_for_update()).mappings().all()
    if len(rows) != 1:
        _fail()
    return rows[0]


def _profile(raw_profile):
    try:
        payload = json.loads(raw_profile)
    except (TypeError, ValueError):
        _fail()
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("password_hash"), str)
        or not payload["password_hash"]
        or not isinstance(payload.get("metadata", {}), dict)
    ):
        _fail()
    return payload


def _valid_identifier(identifier, kind):
    if not isinstance(identifier, str) or not identifier.isascii():
        return False
    if kind == "legacy_username":
        return re.fullmatch(r"[a-z][a-z0-9_.-]{2,63}", identifier) is not None
    if kind == "phone":
        return re.fullmatch(r"1[0-9]{10}", identifier) is not None
    return bool(
        kind == "email"
        and len(identifier) <= 254
        and identifier == identifier.strip().lower()
        and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", identifier)
    )


def _preflight(bind):
    bindings, users, credentials = _tables()
    rows = (
        bind.execute(sa.select(bindings).order_by(bindings.c.id).with_for_update())
        .mappings()
        .all()
    )
    plans = []
    mapped_credentials = set()
    mapped_users = set()
    mapped_identifiers = set()
    for account in rows:
        identifier = account["identifier"]
        kind = account["identifier_kind"]
        if (
            not _valid_identifier(identifier, kind)
            or account["credential_bid"] in mapped_credentials
            or account["user_bid"] in mapped_users
            or identifier in mapped_identifiers
        ):
            _fail()
        mapped_credentials.add(account["credential_bid"])
        mapped_users.add(account["user_bid"])
        mapped_identifiers.add(identifier)
        user = _one(
            bind, sa.select(users).where(users.c.user_bid == account["user_bid"])
        )
        credential = _one(
            bind,
            sa.select(credentials).where(
                credentials.c.credential_bid == account["credential_bid"]
            ),
        )
        if (
            credential["user_bid"] != account["user_bid"]
            or credential["identifier"] != identifier
            or credential["subject_id"] != identifier
            or credential["provider_name"] not in {"local_password", "password"}
        ):
            _fail()
        profile = _profile(credential["raw_profile"])
        original_identity = f"local:{account['user_bid']}"
        target_identity = original_identity if kind == "legacy_username" else identifier
        original_format = (
            "local_username" if kind == "legacy_username" else f"local_{kind}"
        )
        target_format = "local_username" if kind == "legacy_username" else kind
        other_password = bind.execute(
            sa.select(credentials.c.id)
            .where(
                credentials.c.user_bid == account["user_bid"],
                credentials.c.provider_name.in_(["password", "local_password"]),
                credentials.c.id != credential["id"],
            )
            .with_for_update()
        ).first()
        if other_password is not None:
            _fail()
        if kind != "legacy_username":
            user_conflict = bind.execute(
                sa.select(users.c.id)
                .where(
                    users.c.user_bid != account["user_bid"],
                    sa.func.lower(sa.func.trim(users.c.user_identify)) == identifier,
                )
                .with_for_update()
            ).first()
            credential_conflict = bind.execute(
                sa.select(credentials.c.id)
                .where(
                    credentials.c.user_bid != account["user_bid"],
                    credentials.c.provider_name.in_(
                        ["phone", "email", "password", "local_password"]
                    ),
                    sa.func.lower(sa.func.trim(credentials.c.identifier)) == identifier,
                )
                .with_for_update()
            ).first()
            if user_conflict is not None or credential_conflict is not None:
                _fail()
        if credential["provider_name"] == "local_password":
            if (
                user["user_identify"] != original_identity
                or credential["subject_format"] != original_format
            ):
                _fail()
            plans.append((user, credential, profile, target_identity, target_format))
        elif (
            user["user_identify"] != target_identity
            or credential["subject_format"] != target_format
            or profile.get("metadata", {}).get("installation_admin") != "true"
        ):
            _fail()

    old_credentials = (
        bind.execute(
            sa.select(credentials.c.credential_bid)
            .where(credentials.c.provider_name == "local_password")
            .with_for_update()
        )
        .scalars()
        .all()
    )
    if any(
        credential_bid not in mapped_credentials for credential_bid in old_credentials
    ):
        _fail()
    return plans


def upgrade():
    if op.get_context().as_sql:
        raise RuntimeError(
            "Installation password migration requires online account checks."
        )
    bind = op.get_bind()
    _bindings, users, credentials = _tables()
    # This revision has no nontransactional DDL. A savepoint protects partial
    # DML on MySQL even though Alembic does not assume transactional MySQL DDL.
    # Application writers must be stopped: legacy user_identify is not unique.
    with bind.begin_nested():
        plans = _preflight(bind)
        for user, credential, profile, identity, subject_format in plans:
            profile["provider"] = "password"
            profile.setdefault("metadata", {}).update(
                installation_admin="true", contact_verification="unverified"
            )
            bind.execute(
                sa.update(users)
                .where(users.c.id == user["id"])
                .values(user_identify=identity)
            )
            bind.execute(
                sa.update(credentials)
                .where(credentials.c.id == credential["id"])
                .values(
                    provider_name="password",
                    subject_format=subject_format,
                    raw_profile=json.dumps(profile, ensure_ascii=False),
                )
            )


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError(
            "Installation password downgrade requires online account checks."
        )
    bindings, _users, _credentials = _tables()
    # A converted ordinary account may subsequently acquire verified contacts
    # or change its password. Do not split that identity or restore stale hashes.
    if op.get_bind().execute(sa.select(bindings.c.id).limit(1)).first() is not None:
        raise RuntimeError(
            "Cannot downgrade installation password accounts. Keep compatible "
            "password login and recovery, or restore the pre-upgrade database backup."
        )
