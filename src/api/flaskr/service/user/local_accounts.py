"""Explicit local administrator identities, independent of contact verification."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from flaskr.dao import db, uow
from flaskr.service.common.models import raise_error
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
)
from flaskr.service.user.installation_models import LocalAdminAccount
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.password_rate_limit import PasswordLoginAttempt
from flaskr.service.user.password_utils import hash_password, validate_password_strength
from flaskr.service.user.repository import (
    create_user_entity,
    mark_user_roles,
    set_password_hash,
)
from flaskr.service.user.token_store import token_store
from flaskr.util.uuid import generate_id
from sqlalchemy import select, update

if TYPE_CHECKING:
    from flask import Flask


LOCAL_ADMIN_PROVIDER = "local_password"
_USERNAME_PATTERN = re.compile(r"[a-z][a-z0-9_.-]{2,63}\Z", flags=re.ASCII)
_BCRYPT_PASSWORD_MAX_BYTES = 72
_ACTIVE_LOCAL_ACCOUNT_STATES = (
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_PAID,
)


def normalize_local_username(username: str) -> str:
    """Normalize an ASCII local login name without treating it as a contact."""
    normalized = username.strip().lower()
    if not _USERNAME_PATTERN.fullmatch(normalized):
        raise_error("server.installation.invalidUsername")
    return normalized


def validate_local_password(password: str) -> None:
    """Apply the shared strength rules without bcrypt truncation or overflow."""
    validate_password_strength(password)
    if len(password.encode("utf-8")) > _BCRYPT_PASSWORD_MAX_BYTES:
        raise_error("server.installation.passwordTooLong")


def lock_local_admin_credentials(
    *,
    user_bid: str | None = None,
    username: str | None = None,
    credential_bid: str | None = None,
) -> tuple[UserEntity, LocalAdminAccount, AuthCredential]:
    """Serialize local credential changes and token writes on MySQL and SQLite."""
    if not uow.in_unit_of_work():
        message = "Local administrator locking requires an active unit_of_work"
        raise RuntimeError(message)
    if not user_bid and not username:
        raise_error("server.user.invalidCredentials")
    conditions = [
        UserEntity.deleted == 0,
        UserEntity.is_operator == 1,
        UserEntity.state.in_(_ACTIVE_LOCAL_ACCOUNT_STATES),
    ]
    if user_bid:
        conditions.append(UserEntity.user_bid == user_bid)
    if username:
        conditions.append(
            UserEntity.user_bid.in_(
                select(LocalAdminAccount.user_bid).where(
                    LocalAdminAccount.username == username,
                    LocalAdminAccount.deleted == 0,
                )
            )
        )
    # SELECT FOR UPDATE is ignored by SQLite. A real write must precede any
    # credential read and remain held through token persistence or recovery.
    # Referencing the existing value also avoids changing the profile timestamp.
    result = db.session.execute(
        update(UserEntity)
        .where(*conditions)
        .values(updated_at=UserEntity.updated_at)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise_error("server.user.invalidCredentials")
    user = (
        UserEntity.query.filter(*conditions)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if user is None:
        raise_error("server.user.invalidCredentials")
    account_query = LocalAdminAccount.query.filter_by(user_bid=user.user_bid, deleted=0)
    if username:
        account_query = account_query.filter_by(username=username)
    if credential_bid:
        account_query = account_query.filter_by(credential_bid=credential_bid)
    account = account_query.populate_existing().with_for_update().first()
    if account is None:
        raise_error("server.user.invalidCredentials")
    credential = (
        AuthCredential.query.filter_by(
            credential_bid=account.credential_bid,
            user_bid=user.user_bid,
            provider_name=LOCAL_ADMIN_PROVIDER,
            identifier=account.username,
            state=CREDENTIAL_STATE_VERIFIED,
            deleted=0,
        )
        .populate_existing()
        .with_for_update()
        .first()
    )
    if credential is None:
        raise_error("server.user.invalidCredentials")
    return user, account, credential


def provision_local_admin_account(
    app: Flask,
    *,
    username: str,
    password: str,
    language: str = "en-US",
) -> str:
    """Create a local administrator inside the caller's bootstrap transaction."""
    if not uow.in_unit_of_work():
        message = "Local administrator provisioning requires an active unit_of_work"
        raise RuntimeError(message)
    normalized = normalize_local_username(username)
    validate_local_password(password)
    # Deleted names remain reserved. A unique database constraint also closes
    # the race between this friendly validation and the eventual INSERT.
    if LocalAdminAccount.query.filter_by(username=normalized).first() is not None:
        raise_error("server.installation.usernameUnavailable")

    user_bid = generate_id(app)
    create_user_entity(
        user_bid=user_bid,
        identify=f"local:{user_bid}",
        nickname=normalized,
        language=language,
        state=USER_STATE_REGISTERED,
    )
    credential = AuthCredential(
        credential_bid=generate_id(app),
        user_bid=user_bid,
        provider_name=LOCAL_ADMIN_PROVIDER,
        subject_id=normalized,
        subject_format="local_username",
        identifier=normalized,
        state=CREDENTIAL_STATE_VERIFIED,
        raw_profile="",
        deleted=0,
    )
    set_password_hash(credential, hash_password(password))
    db.session.add(credential)
    db.session.add(
        LocalAdminAccount(
            username=normalized,
            user_bid=user_bid,
            credential_bid=credential.credential_bid,
            deleted=0,
        )
    )
    mark_user_roles(user_bid, is_creator=True, is_operator=True)
    db.session.flush()
    return user_bid


def reset_local_admin_password(app: Flask, *, username: str, new_password: str) -> None:
    """Reset a local password through trusted console authority, revoking sessions."""
    uow.require_transaction_owner("reset_local_admin_password", app)
    normalized = normalize_local_username(username)
    validate_local_password(new_password)
    new_hash = hash_password(new_password)
    with uow.app_context_scope(app), uow.unit_of_work():
        user, _account, credential = lock_local_admin_credentials(username=normalized)
        user_bid = user.user_bid
        set_password_hash(credential, new_hash)
        token_store.revoke_all(app, user_id=user_bid)

    # Console recovery is allowed to clear a password cooldown, but doing so
    # must not hold a database transaction while waiting for Redis guards.
    for identity in (f"user:{user_bid}", f"local-response:{normalized}"):
        with PasswordLoginAttempt(app, identity) as attempt:
            attempt.clear()
    app.logger.info("security_event=local_admin_password_reset")
