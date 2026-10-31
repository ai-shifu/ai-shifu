"""Provision and recover installation administrators using ordinary passwords."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from flaskr.dao import db, uow
from flaskr.service.common.contact_identifiers import (
    CONTACT_TYPE_EMAIL,
    CONTACT_TYPE_PHONE,
    resolve_contact_type,
    validate_contact_identifier,
)
from flaskr.service.common.models import AppError, raise_error
from flaskr.service.user.consts import (
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
)
from flaskr.service.user.installation_models import LocalAdminAccount
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.password_flow import (
    lock_password_credential,
    write_password_credential,
)
from flaskr.service.user.password_rate_limit import PasswordLoginAttempt
from flaskr.service.user.password_utils import hash_password, validate_password
from flaskr.service.user.repository import (
    create_user_entity,
    mark_user_roles,
    set_password_hash,
)
from flaskr.service.user.token_store import token_store
from flaskr.util.uuid import generate_id
from sqlalchemy import func

if TYPE_CHECKING:
    from flask import Flask


LOCAL_ADMIN_PROVIDER = "password"
_USERNAME_PATTERN = re.compile(r"[a-z][a-z0-9_.-]{2,63}\Z", flags=re.ASCII)
_ACTIVE_LOCAL_ACCOUNT_STATES = (
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_PAID,
)


def normalize_local_identifier(identifier: str, *, allow_legacy: bool = False) -> str:
    """Accept a contact login label without asserting ownership of that contact."""
    kind = resolve_contact_type(
        identifier, allowed={CONTACT_TYPE_EMAIL, CONTACT_TYPE_PHONE}
    )
    try:
        normalized = validate_contact_identifier(identifier, kind)
    except AppError:
        normalized = ""
    if normalized and normalized.isascii() and len(normalized) <= 254:
        return normalized
    legacy = identifier.strip().lower()
    if not allow_legacy or not _USERNAME_PATTERN.fullmatch(legacy):
        raise_error("server.installation.invalidIdentifier")
    return legacy


def _binding_matches_identifier(account: LocalAdminAccount, identifier: str) -> bool:
    """Keep old names readable while requiring the persisted new contact kind."""
    kind = "email" if "@" in identifier else "phone"
    if _USERNAME_PATTERN.fullmatch(identifier):
        kind = "legacy_username"
    return account.identifier_kind == kind


def validate_local_binding(account: LocalAdminAccount, identifier: str) -> None:
    """Reject a mismatched contact-kind or fabricated legacy mapping."""
    if not _binding_matches_identifier(account, identifier):
        raise_error("server.installation.invalidIdentifier")


def validate_local_password(password: str) -> None:
    """Apply the shared strength rules without bcrypt truncation or overflow."""
    validate_password(password)


def lock_local_admin_credentials(
    *,
    user_bid: str | None = None,
    identifier: str | None = None,
    credential_bid: str | None = None,
) -> tuple[UserEntity, LocalAdminAccount, AuthCredential]:
    """Serialize local credential changes and token writes on MySQL and SQLite."""
    if not uow.in_unit_of_work():
        message = "Local administrator locking requires an active unit_of_work"
        raise RuntimeError(message)
    if not user_bid and not identifier:
        raise_error("server.user.invalidCredentials")
    account_query = LocalAdminAccount.query.filter_by(deleted=0)
    if user_bid:
        account_query = account_query.filter_by(user_bid=user_bid)
    if identifier:
        account_query = account_query.filter_by(identifier=identifier)
    account = account_query.first()
    if account is None:
        raise_error("server.user.invalidCredentials")
    user, credential = lock_password_credential(
        user_bid=account.user_bid, credential_bid=account.credential_bid
    )
    if not user.is_operator or user.state not in _ACTIVE_LOCAL_ACCOUNT_STATES:
        raise_error("server.user.invalidCredentials")
    account_query = LocalAdminAccount.query.filter_by(user_bid=user.user_bid, deleted=0)
    if identifier:
        account_query = account_query.filter_by(identifier=identifier)
    if credential_bid:
        account_query = account_query.filter_by(credential_bid=credential_bid)
    account = account_query.populate_existing().with_for_update().first()
    if account is None or account.credential_bid != credential.credential_bid:
        raise_error("server.user.invalidCredentials")
    validate_local_binding(account, account.identifier)
    # The setup contact is a durable console recovery key. Ordinary contact
    # replacement may rename the same password credential without changing this
    # binding; authority comes from its locked user/credential IDs. Legacy names
    # still require their explicit, unchanged password mapping.
    if (
        account.identifier_kind == "legacy_username"
        and credential.identifier != account.identifier
    ):
        raise_error("server.user.invalidCredentials")
    return user, account, credential


def provision_local_admin_account(
    app: Flask,
    *,
    identifier: str,
    password: str,
    language: str = "en-US",
) -> str:
    """Create a local administrator inside the caller's bootstrap transaction."""
    if not uow.in_unit_of_work():
        message = "Local administrator provisioning requires an active unit_of_work"
        raise RuntimeError(message)
    normalized = normalize_local_identifier(identifier)
    validate_local_password(password)
    # Deleted names remain reserved. A unique database constraint also closes
    # the race between this friendly validation and the eventual INSERT.
    lookup = {normalized}
    if "@" not in normalized:
        lookup.update({f"+86{normalized}", f"+86 {normalized}"})
    if (
        LocalAdminAccount.query.filter_by(identifier=normalized).first() is not None
        or UserEntity.query.filter(
            func.lower(func.trim(UserEntity.user_identify)).in_(lookup)
        ).first()
        is not None
        or AuthCredential.query.filter(
            AuthCredential.provider_name.in_(["phone", "email", "password"]),
            func.lower(func.trim(AuthCredential.identifier)).in_(lookup),
        ).first()
        is not None
    ):
        raise_error("server.installation.identifierUnavailable")

    user_bid = generate_id(app)
    create_user_entity(
        user_bid=user_bid,
        identify=normalized,
        nickname="",
        language=language,
        state=USER_STATE_REGISTERED,
    )
    credential = write_password_credential(
        app,
        user_bid=user_bid,
        identifier=normalized,
        new_password=password,
        metadata={"contact_verification": "unverified", "installation_admin": "true"},
    )
    db.session.add(
        LocalAdminAccount(
            identifier=normalized,
            identifier_kind="email" if "@" in normalized else "phone",
            user_bid=user_bid,
            credential_bid=credential.credential_bid,
            deleted=0,
        )
    )
    mark_user_roles(user_bid, is_creator=True, is_operator=True)
    db.session.flush()
    return user_bid


def reset_local_admin_password(
    app: Flask, *, identifier: str, new_password: str
) -> None:
    """Reset a local password through trusted console authority, revoking sessions."""
    uow.require_transaction_owner("reset_local_admin_password", app)
    normalized = normalize_local_identifier(identifier, allow_legacy=True)
    validate_local_password(new_password)
    new_hash = hash_password(new_password)
    with uow.app_context_scope(app), uow.unit_of_work():
        user, _account, credential = lock_local_admin_credentials(identifier=normalized)
        user_bid = user.user_bid
        set_password_hash(credential, new_hash)
        token_store.revoke_all(app, user_id=user_bid)

    # Console recovery is allowed to clear a password cooldown, but doing so
    # must not hold a database transaction while waiting for Redis guards.
    for identity in (f"user:{user_bid}", f"response:{normalized}"):
        with PasswordLoginAttempt(app, identity) as attempt:
            attempt.clear()
    app.logger.info("security_event=local_admin_password_reset")
