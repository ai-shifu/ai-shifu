"""Replace a user's primary login contact on behalf of an operator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common.contact_identifiers import (
    CONTACT_TYPE_EMAIL,
    resolve_primary_contact_type,
    validate_contact_identifier,
)
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.user.consts import CREDENTIAL_STATE_VERIFIED
from flaskr.service.user.models import AuthCredential, UserInfo
from flaskr.service.user.sessions import revoke_all_user_sessions
from flaskr.util.uuid import generate_id

if TYPE_CHECKING:
    from flask import Flask


def _mask_contact(identifier: str, contact_type: str) -> str:
    """Return a log-safe representation of a phone number or email address."""
    if contact_type == CONTACT_TYPE_EMAIL:
        local, separator, domain = identifier.partition("@")
        visible = local[:2]
        return f"{visible}***{separator}{domain}" if separator else "***"
    if len(identifier) <= 7:
        return "***"
    return f"{identifier[:3]}****{identifier[-4:]}"


def _active_contact_credentials(
    *, user_bid: str, contact_type: str
) -> list[AuthCredential]:
    providers = (
        [CONTACT_TYPE_EMAIL, "google"]
        if contact_type == CONTACT_TYPE_EMAIL
        else [contact_type]
    )
    return (
        AuthCredential.query.filter(
            AuthCredential.user_bid == user_bid,
            AuthCredential.provider_name.in_(providers),
            AuthCredential.deleted == 0,
        )
        .order_by(AuthCredential.id.asc())
        .with_for_update()
        .all()
    )


def change_operator_user_contact(
    app: Flask,
    *,
    user_bid: str,
    operator_user_bid: str,
    contact_type: str,
    new_identifier: str,
    reason: str,
) -> dict[str, Any]:
    """Replace the configured primary contact while preserving the user identity."""
    normalized_user_bid = str(user_bid or "").strip()
    normalized_operator_user_bid = str(operator_user_bid or "").strip()
    normalized_contact_type = str(contact_type or "").strip().lower()
    normalized_reason = str(reason or "").strip()
    expected_contact_type = resolve_primary_contact_type()

    if not normalized_user_bid:
        raise_param_error("user_bid")
    if not normalized_operator_user_bid:
        raise_param_error("operator_user_bid")
    if normalized_contact_type != expected_contact_type:
        raise_param_error("contact_type")
    if not normalized_reason:
        raise_param_error("reason")
    if len(normalized_reason) > 500:
        raise_param_error("reason")

    normalized_identifier = validate_contact_identifier(
        new_identifier,
        normalized_contact_type,
        empty_error="identifier",
    )
    if len(normalized_identifier) > 255:
        raise_param_error("identifier")
    old_identifiers: list[str] = []
    revoked_sessions = 0

    with app_context_scope(app), unit_of_work():
        user = (
            UserInfo.query.filter(
                UserInfo.user_bid == normalized_user_bid,
                UserInfo.deleted == 0,
            )
            .with_for_update()
            .first()
        )
        if user is None:
            raise_error("server.user.userNotFound")

        owner_by_identity = (
            UserInfo.query.filter(
                UserInfo.user_identify == normalized_identifier,
                UserInfo.deleted == 0,
            )
            .with_for_update()
            .first()
        )
        if owner_by_identity is not None:
            if owner_by_identity.user_bid == normalized_user_bid:
                raise_error(f"server.user.{normalized_contact_type}Unchanged")
            raise_error(f"server.user.{normalized_contact_type}AlreadyRegistered")

        providers = (
            [CONTACT_TYPE_EMAIL, "google"]
            if normalized_contact_type == CONTACT_TYPE_EMAIL
            else [normalized_contact_type]
        )
        existing_owner = (
            AuthCredential.query.filter(
                AuthCredential.provider_name.in_(providers),
                AuthCredential.identifier == normalized_identifier,
                AuthCredential.deleted == 0,
            )
            .with_for_update()
            .first()
        )
        if existing_owner is not None:
            if existing_owner.user_bid == normalized_user_bid:
                raise_error(f"server.user.{normalized_contact_type}Unchanged")
            raise_error(f"server.user.{normalized_contact_type}AlreadyRegistered")

        old_credentials = _active_contact_credentials(
            user_bid=normalized_user_bid,
            contact_type=normalized_contact_type,
        )
        if not old_credentials:
            raise_error(f"server.user.{normalized_contact_type}NotBound")

        old_identifiers = [
            str(credential.identifier or "").strip()
            for credential in old_credentials
            if str(credential.identifier or "").strip()
        ]
        for credential in old_credentials:
            credential.deleted = 1

        new_credential = AuthCredential(
            credential_bid=generate_id(app),
            user_bid=normalized_user_bid,
            provider_name=normalized_contact_type,
            subject_id=normalized_identifier,
            subject_format=normalized_contact_type,
            identifier=normalized_identifier,
            raw_profile="{}",
            state=CREDENTIAL_STATE_VERIFIED,
            deleted=0,
        )
        db.session.add(new_credential)

        password_credentials = (
            AuthCredential.query.filter(
                AuthCredential.user_bid == normalized_user_bid,
                AuthCredential.provider_name == "password",
                AuthCredential.deleted == 0,
            )
            .with_for_update()
            .all()
        )
        for credential in password_credentials:
            if (
                credential.subject_format == normalized_contact_type
                or credential.identifier in old_identifiers
            ):
                credential.subject_id = normalized_identifier
                credential.subject_format = normalized_contact_type
                credential.identifier = normalized_identifier

        user.user_identify = normalized_identifier
        db.session.flush()
        # Join session deletion to the identity transaction. If durable deletion
        # or cache eviction fails, the contact update rolls back and can be retried.
        revoked_sessions = revoke_all_user_sessions(
            app,
            user_id=normalized_user_bid,
        )["revoked"]
    old_masked = [
        _mask_contact(identifier, normalized_contact_type)
        for identifier in old_identifiers
    ]
    app.logger.info(
        "security_event=operator_user_contact_changed operator_user_bid=%s "
        "target_user_bid=%s contact_type=%s old_contacts=%s new_contact=%s "
        "reason_present=true revoked_sessions=%s",
        normalized_operator_user_bid,
        normalized_user_bid,
        normalized_contact_type,
        old_masked,
        _mask_contact(normalized_identifier, normalized_contact_type),
        revoked_sessions,
    )
    return {
        "user_bid": normalized_user_bid,
        "contact_type": normalized_contact_type,
        "identifier": normalized_identifier,
        "revoked_sessions": revoked_sessions,
    }
