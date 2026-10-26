"""Password credential flows (set / change / reset).

Moved out of ``route/user.py`` so the route only validates the request while
the credential write owns its transaction boundary.
"""

from __future__ import annotations

import hmac
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.dao.uow import in_unit_of_work, require_transaction_owner, unit_of_work
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.phone_numbers import normalize_phone_identifier
from flaskr.service.user.consts import CREDENTIAL_STATE_VERIFIED
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.password_utils import (
    hash_password,
    validate_password,
    verify_password,
)
from flaskr.service.user.repository import (
    find_credential,
    get_password_hash,
    list_credentials,
    load_user_aggregate_by_identifier,
    serialize_raw_profile,
    set_password_hash,
)
from flaskr.service.user.token_store import token_store
from flaskr.service.user.verification_codes import consume_verification_code
from flaskr.util.uuid import generate_id
from sqlalchemy import update

if TYPE_CHECKING:
    from flask import Flask


def _normalize_identifier(identifier: str) -> str:
    stripped = identifier.strip()
    return stripped.lower() if "@" in stripped else normalize_phone_identifier(stripped)


def lock_password_user(user_bid: str) -> UserEntity:
    """Serialize credential writes and token issuance, including on SQLite."""
    if not in_unit_of_work():
        message = "Password credential locking requires an active unit_of_work"
        raise RuntimeError(message)
    # SQLite ignores SELECT FOR UPDATE: a write must own the row before reading
    # credentials. Keep the profile timestamp unchanged while acquiring the lock.
    conditions = (UserEntity.user_bid == user_bid, UserEntity.deleted == 0)
    result = db.session.execute(
        update(UserEntity)
        .where(*conditions)
        .values(updated_at=UserEntity.updated_at)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise_error("server.user.invalidCredentials")
    return (
        UserEntity.query.filter(*conditions).populate_existing().with_for_update().one()
    )


def lock_password_credential(
    *, user_bid: str, credential_bid: str
) -> tuple[UserEntity, AuthCredential]:
    """Lock a standard password credential in the caller's transaction."""
    user = lock_password_user(user_bid)
    credential = (
        AuthCredential.query.filter_by(
            credential_bid=credential_bid,
            user_bid=user_bid,
            provider_name="password",
            state=CREDENTIAL_STATE_VERIFIED,
            deleted=0,
        )
        .populate_existing()
        .with_for_update()
        .first()
    )
    if credential is None:
        raise_error("server.user.invalidCredentials")
    return user, credential


def write_password_credential(
    app: Flask,
    *,
    user_bid: str,
    identifier: str,
    new_password: str,
    metadata: dict[str, str | None] | None = None,
    revoke_sessions: bool = False,
) -> AuthCredential:
    """Write a password after the calling flow establishes its own authority."""
    validate_password(new_password)
    password_hash = hash_password(new_password)
    subject_format = "email" if "@" in identifier else "phone"
    with unit_of_work():
        lock_password_user(user_bid)
        pwd_cred = find_credential(
            provider_name="password", identifier=identifier, user_bid=user_bid
        )
        if pwd_cred is None:
            pwd_cred = AuthCredential(
                credential_bid=generate_id(app),
                user_bid=user_bid,
                provider_name="password",
                subject_id=identifier,
                subject_format=subject_format,
                identifier=identifier,
                raw_profile=serialize_raw_profile("password", metadata or {}),
                state=CREDENTIAL_STATE_VERIFIED,
                deleted=0,
            )
            db.session.add(pwd_cred)
        set_password_hash(pwd_cred, password_hash)
        if revoke_sessions:
            token_store.revoke_all(app, user_id=user_bid)
        db.session.flush()
        return pwd_cred


def set_password(
    app: Flask,
    *,
    user_bid: str,
    identifier: str | None,
    code: str,
    new_password: str,
) -> None:
    """Set the first password for a logged-in user after a verification code check."""
    creds = list_credentials(user_bid=user_bid)
    available_identifiers = [
        _normalize_identifier(cred.identifier)
        for cred in creds
        if cred.provider_name in ("phone", "email") and cred.identifier
    ]

    selected_identifier = None
    if identifier:
        normalized = _normalize_identifier(identifier)
        if normalized not in available_identifiers:
            # Avoid leaking whether another account exists for the identifier.
            raise_error("server.user.invalidCredentials")
        selected_identifier = normalized
    else:
        selected_identifier = (
            available_identifiers[0] if available_identifiers else None
        )

    if not selected_identifier:
        raise_param_error("identifier")

    # Reject if user already has a password credential (use change_password instead)
    pwd_cred = find_credential(
        provider_name="password", identifier=selected_identifier, user_bid=user_bid
    )
    if pwd_cred and get_password_hash(pwd_cred):
        raise_error("server.user.passwordAlreadySet")

    # Validate ownership by consuming a verification code for the chosen identifier.
    consume_verification_code(app, identifier=selected_identifier, code=code)
    write_password_credential(
        app,
        user_bid=user_bid,
        identifier=selected_identifier,
        new_password=new_password,
    )


def change_password(
    app: Flask, *, user_bid: str, old_password: str, new_password: str
) -> None:
    """Verify the current password, then reject any intervening credential change."""
    require_transaction_owner("change_password", app)
    validate_password(new_password)
    with unit_of_work():
        creds = list_credentials(user_bid=user_bid, provider_name="password")
        if not creds:
            raise_error("server.user.invalidCredentials")
        credential_bid = creds[0].credential_bid
        current_hash = get_password_hash(creds[0])
    if not current_hash or not verify_password(old_password, current_hash):
        raise_error("server.user.invalidCredentials")
    new_hash = hash_password(new_password)
    with unit_of_work():
        _user, credential = lock_password_credential(
            user_bid=user_bid, credential_bid=credential_bid
        )
        if not hmac.compare_digest(current_hash, get_password_hash(credential)):
            raise_error("server.user.invalidCredentials")
        set_password_hash(credential, new_hash)


def reset_password(
    app: Flask, *, identifier: str, code: str, new_password: str
) -> None:
    """Reset the password of an existing user via a verification code."""
    normalized_identifier = _normalize_identifier(identifier)

    # Reset is only allowed for existing users. New users must go through
    # phone-code / Google login first.
    aggregate = load_user_aggregate_by_identifier(
        normalized_identifier, providers=["phone", "email"]
    )
    if not aggregate:
        raise_error("server.user.userNotFound")

    # Verify identity via verification code without creating/merging users.
    consume_verification_code(app, identifier=normalized_identifier, code=code)
    write_password_credential(
        app,
        user_bid=aggregate.user_bid,
        identifier=normalized_identifier,
        new_password=new_password,
        revoke_sessions=True,
    )
