"""Own one-time installation authorization independently of ordinary login."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from flaskr.dao import db
from flaskr.dao.uow import (
    app_context_scope,
    on_commit,
    require_transaction_owner,
    unit_of_work,
)
from flaskr.service.common.models import raise_error
from flaskr.service.user.installation_models import InstallationState, LocalAdminAccount
from flaskr.util.datetime import now_utc
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from flask import Flask


INSTALLATION_PROVENANCE_EXTENSION = "installation_database_was_empty"
FRESH_INSTALLATION_MIGRATION_ARGUMENT = "ai_shifu_fresh_installation=true"
SETUP_TOKEN_LIFETIME = timedelta(minutes=20)


def capture_installation_database_provenance(app: Flask) -> bool:
    """Capture empty-schema provenance before plugins or migrations can write."""
    if INSTALLATION_PROVENANCE_EXTENSION in app.extensions:
        return app.extensions[INSTALLATION_PROVENANCE_EXTENSION] is True
    empty = False
    try:
        with app_context_scope(app):
            empty = not inspect(db.engine).get_table_names()
    except (SQLAlchemyError, RuntimeError):
        # An unavailable or unbound database is not proof of a new installation.
        empty = False
    app.extensions[INSTALLATION_PROVENANCE_EXTENSION] = empty
    return empty


def prepare_installation_database(app: Flask) -> None:
    """Migrate with explicit provenance; an ordinary upgrade remains closed."""
    from flask_migrate import upgrade

    require_transaction_owner("prepare_installation_database", app)
    empty = capture_installation_database_provenance(app)
    directory = str(Path(__file__).resolve().parents[3] / "migrations")
    with app_context_scope(app):
        upgrade(
            directory=directory,
            x_arg=[FRESH_INSTALLATION_MIGRATION_ARGUMENT] if empty else None,
        )


def normalize_setup_origin(origin: str) -> str:
    """Accept HTTPS origins and HTTP origins restricted to loopback names."""
    try:
        normalized = _parse_setup_origin(origin)
    except (ValueError, UnicodeError):
        raise_error("server.installation.invalidSetupOrigin")
    return normalized


def _parse_setup_origin(origin: str) -> str:
    parsed = urlsplit(str(origin).strip())
    hostname = parsed.hostname or ""
    port = parsed.port
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError
    hostname = hostname.rstrip(".").lower().encode("idna").decode("ascii")
    if (
        parsed.scheme == "http"
        and hostname != "localhost"
        and not ipaddress.ip_address(hostname).is_loopback
    ):
        raise ValueError
    host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None and port != (443 if parsed.scheme == "https" else 80):
        host = f"{host}:{port}"
    return f"{parsed.scheme}://{host}"


def get_installation_status(app: Flask) -> dict[str, bool]:
    """Expose eligibility without exposing installation credentials or contacts."""
    from flaskr.service.user.models import AuthCredential, UserInfo

    with app_context_scope(app), unit_of_work():
        state = db.session.get(InstallationState, 1)
        pending = bool(
            state is not None
            and state.mode == "managed"
            and state.initialized_at is None
        )
        local_account = (
            LocalAdminAccount.query.join(
                UserInfo, UserInfo.user_bid == LocalAdminAccount.user_bid
            )
            .join(
                AuthCredential,
                AuthCredential.credential_bid == LocalAdminAccount.credential_bid,
            )
            .filter(
                LocalAdminAccount.deleted == 0,
                UserInfo.deleted == 0,
                UserInfo.is_operator == 1,
                AuthCredential.deleted == 0,
                AuthCredential.provider_name == "local_password",
            )
            .first()
        )
        return {
            "setup_required": pending,
            "local_admin_login_enabled": local_account is not None,
        }


def allows_legacy_first_user_bootstrap(app: Flask) -> bool:
    """Allow the historic bootstrap only for explicitly unclaimed legacy state."""
    with app_context_scope(app):
        state = db.session.get(InstallationState, 1)
        return bool(
            state is not None
            and state.mode == "legacy"
            and state.initialized_at is None
        )


def complete_legacy_first_user_bootstrap(user_bid: str) -> None:
    """Seal an explicitly enabled legacy transition in its caller's transaction."""
    InstallationState.query.filter(
        InstallationState.id == 1,
        InstallationState.mode == "legacy",
        InstallationState.initialized_at.is_(None),
    ).update(
        {
            InstallationState.initialized_at: now_utc(),
            InstallationState.initialized_user_bid: user_bid,
        },
        synchronize_session="fetch",
    )


def _lock_installation(*, pending_only: bool = True) -> InstallationState:
    query = InstallationState.query.filter(InstallationState.id == 1)
    if pending_only:
        query = query.filter(
            InstallationState.mode == "managed",
            InstallationState.initialized_at.is_(None),
        )
    # A conditional write locks the singleton on both MySQL and SQLite. A plain
    # FOR UPDATE alone would leave the SQLite test/runtime path raceable.
    matched = query.update(
        {InstallationState.claim_version: InstallationState.claim_version + 1},
        synchronize_session=False,
    )
    if matched != 1:
        raise_error("server.installation.setupUnavailable")
    return (
        InstallationState.query.populate_existing()
        .filter_by(id=1)
        .with_for_update()
        .one()
    )


def issue_setup_token(app: Flask, *, origin: str = "http://localhost:8080") -> str:
    """Issue a short-lived claim through a trusted server-console operation."""
    require_transaction_owner("issue_setup_token", app)
    normalized_origin = normalize_setup_origin(origin)
    token = secrets.token_urlsafe(32)
    with app_context_scope(app), unit_of_work():
        state = _lock_installation()
        state.token_digest = hashlib.sha256(token.encode()).hexdigest()
        state.token_expires_at = now_utc() + SETUP_TOKEN_LIFETIME
        state.token_origin = normalized_origin
    return token


def _schedule_creator_activation(app: Flask, user_bid: str, language: str) -> None:
    from flaskr.service.user.post_auth import PostAuthContext, run_post_auth_extensions

    context = PostAuthContext(
        user_id=user_bid,
        source="installation",
        created_new_user=True,
        language=language,
        creator_granted_now=True,
    )
    on_commit(lambda: run_post_auth_extensions(app, context))


def _provision_admin(
    app: Flask, state: InstallationState, username: str, password: str, language: str
) -> str:
    from flaskr.service.user.local_accounts import provision_local_admin_account
    from flaskr.service.user.utils import ensure_demo_course_permissions

    user_bid = provision_local_admin_account(
        app, username=username, password=password, language=language
    )
    # Existing installations keep the current course owners. Only a managed
    # installation's initial administrator receives the bundled demo ownership.
    if state.mode == "managed":
        assign_configured_demo_ownership(user_bid)
    ensure_demo_course_permissions(app, user_bid)
    state.initialized_at = now_utc()
    state.initialized_user_bid = user_bid
    state.token_digest = ""
    state.token_expires_at = None
    state.token_origin = ""
    db.session.flush()
    _schedule_creator_activation(app, user_bid, language)
    return user_bid


def assign_configured_demo_ownership(user_bid: str) -> None:
    """Transfer only courses explicitly registered by the bundled demo importer."""
    from flaskr.service.shifu.models import DraftShifu, PublishedShifu
    from flaskr.service.user.utils import load_existing_demo_shifu_ids

    demo_ids = load_existing_demo_shifu_ids()
    if not demo_ids:
        return
    for model in (PublishedShifu, DraftShifu):
        model.query.filter(model.shifu_bid.in_(demo_ids), model.deleted == 0).update(
            {model.created_user_bid: user_bid}, synchronize_session="fetch"
        )
    db.session.flush()


def initialize_admin(
    app: Flask,
    *,
    setup_token: str,
    username: str,
    password: str,
    language: str = "en-US",
    request_origin: str,
) -> str:
    """Consume one origin-bound setup claim and atomically create the owner."""
    require_transaction_owner("initialize_admin", app)
    origin = normalize_setup_origin(request_origin)
    token = str(setup_token)
    if not 40 <= len(token) <= 128:
        raise_error("server.installation.invalidSetupToken")
    digest = hashlib.sha256(token.encode()).hexdigest()
    with app_context_scope(app), unit_of_work():
        state = _lock_installation()
        if (
            not state.token_digest
            or state.token_expires_at is None
            or state.token_expires_at <= now_utc()
            or not hmac.compare_digest(state.token_digest, digest)
        ):
            raise_error("server.installation.invalidSetupToken")
        if not hmac.compare_digest(state.token_origin, origin):
            raise_error("server.installation.invalidSetupOrigin")
        return _provision_admin(app, state, username, password, language)


def create_admin_from_console(
    app: Flask,
    *,
    username: str,
    password: str,
    language: str = "en-US",
) -> str:
    """Create the first local admin with console authority, never reopening Web setup."""
    require_transaction_owner("create_admin_from_console", app)
    with app_context_scope(app), unit_of_work():
        state = _lock_installation(pending_only=False)
        if LocalAdminAccount.query.first() is not None or (
            state.mode == "managed" and state.initialized_at is not None
        ):
            raise_error("server.installation.setupComplete")
        return _provision_admin(app, state, username, password, language)
