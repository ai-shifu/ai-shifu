"""Password credential flows (set / change / reset).

Moved out of ``route/user.py`` so the route only validates the request while
the credential write owns its transaction boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.phone_numbers import normalize_phone_identifier
from flaskr.service.user.consts import CREDENTIAL_STATE_VERIFIED
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.password_utils import hash_password, verify_password
from flaskr.service.user.repository import (
    find_credential,
    get_password_hash,
    list_credentials,
    load_user_aggregate_by_identifier,
    set_password_hash,
)
from flaskr.service.user.verification_codes import consume_verification_code
from flaskr.util.uuid import generate_id

if TYPE_CHECKING:
    from flask import Flask


def _normalize_identifier(identifier: str) -> str:
    stripped = identifier.strip()
    return stripped.lower() if "@" in stripped else normalize_phone_identifier(stripped)


def _write_password_credential(
    app: Flask, *, user_bid: str, identifier: str, new_password: str
) -> None:
    """Create or update the password credential for ``identifier`` in one unit of work."""
    subject_format = "email" if "@" in identifier else "phone"
    with unit_of_work():
        pwd_cred = find_credential(
            provider_name="password", identifier=identifier, user_bid=user_bid
        )
        if pwd_cred:
            set_password_hash(pwd_cred, hash_password(new_password))
            return
        pwd_cred = AuthCredential(
            credential_bid=generate_id(app),
            user_bid=user_bid,
            provider_name="password",
            subject_id=identifier,
            subject_format=subject_format,
            identifier=identifier,
            raw_profile="",
            state=CREDENTIAL_STATE_VERIFIED,
            deleted=0,
        )
        db.session.add(pwd_cred)
        set_password_hash(pwd_cred, hash_password(new_password))


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
    _write_password_credential(
        app,
        user_bid=user_bid,
        identifier=selected_identifier,
        new_password=new_password,
    )


def change_password(
    app: Flask, *, user_bid: str, old_password: str, new_password: str
) -> None:
    """Change the password of a logged-in user after verifying the old one."""
    del app  # kept for a uniform service signature
    creds = list_credentials(user_bid=user_bid, provider_name="password")
    if not creds:
        raise_error("server.user.invalidCredentials")

    pwd_cred = creds[0]
    current_hash = get_password_hash(pwd_cred)
    if not current_hash or not verify_password(old_password, current_hash):
        raise_error("server.user.invalidCredentials")

    with unit_of_work():
        set_password_hash(pwd_cred, hash_password(new_password))


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
    _write_password_credential(
        app,
        user_bid=aggregate.user_bid,
        identifier=normalized_identifier,
        new_password=new_password,
    )
