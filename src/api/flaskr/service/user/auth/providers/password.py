"""Password authentication provider.

Supports login via phone number or email + password.
"""

from __future__ import annotations

import hmac
from typing import Optional

from flask import Flask

from flaskr.service.user.auth.base import (
    AuthProvider,
    AuthResult,
    VerificationRequest,
)
from flaskr.service.user.auth.factory import (
    has_provider,
    register_provider,
)
from flaskr.dao import db
from flaskr.service.user.consts import CREDENTIAL_STATE_VERIFIED, USER_STATE_REGISTERED
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    get_password_hash,
    list_credentials,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    ensure_user_for_identifier,
    set_password_hash,
)
from flaskr.service.user.password_utils import hash_password, verify_password
from flaskr.service.user.utils import (
    ensure_admin_creator_and_demo_permissions,
    generate_token,
)
from flaskr.service.common.dtos import UserToken
from flaskr.service.common.models import raise_error
from flaskr.util.uuid import generate_id


class PasswordAuthProvider(AuthProvider):
    """Authenticate via identifier (phone or email) + password."""

    provider_name = "password"
    supports_challenge = False

    def _maybe_bootstrap_first_admin(
        self, app: Flask, request: VerificationRequest
    ) -> Optional[AuthResult]:
        identifier = (request.identifier or "").strip()
        password = request.code or ""
        metadata = request.metadata or {}

        login_context = (metadata.get("login_context") or "").strip()
        if login_context != "admin":
            return None

        bootstrap_password = (app.config.get("BOOTSTRAP_ADMIN_PASSWORD") or "").strip()
        if not bootstrap_password:
            return None

        if not hmac.compare_digest(str(password), str(bootstrap_password)):
            return None

        normalized_identifier = identifier.strip()
        provider = "phone"
        subject_format = "phone"
        if "@" in normalized_identifier:
            provider = "email"
            subject_format = "email"
            normalized_identifier = normalized_identifier.lower()
        else:
            normalized_phone = normalized_identifier.replace(" ", "")
            if normalized_phone.startswith("+"):
                normalized_phone_digits = normalized_phone[1:]
            else:
                normalized_phone_digits = normalized_phone
            if not normalized_phone_digits.isdigit():
                raise_error("server.user.invalidCredentials")
            normalized_identifier = normalized_phone

        restrict_identifier = (
            app.config.get("BOOTSTRAP_ADMIN_IDENTIFIER") or ""
        ).strip()
        if restrict_identifier:
            restrict_normalized = restrict_identifier.strip()
            if "@" in restrict_normalized:
                restrict_normalized = restrict_normalized.lower()
            if restrict_normalized != normalized_identifier:
                raise_error("server.user.invalidCredentials")

        # Only allow bootstrap when there is no creator user yet.
        from flaskr.service.user.models import UserInfo as UserEntity

        creator_count = UserEntity.query.filter(
            UserEntity.deleted == 0, UserEntity.is_creator == 1
        ).count()
        if creator_count != 0:
            raise_error("server.user.invalidCredentials")

        # Do not allow bootstrap to override an existing user.
        existing = load_user_aggregate_by_identifier(
            normalized_identifier, providers=["phone", "email"]
        )
        if existing:
            raise_error("server.user.invalidCredentials")

        language = (metadata.get("language") or "").strip() or "en-US"
        aggregate, _created = ensure_user_for_identifier(
            app,
            provider=provider,
            identifier=normalized_identifier,
            defaults={
                "identify": normalized_identifier,
                "language": language,
                "state": USER_STATE_REGISTERED,
            },
        )

        pwd_cred = AuthCredential(
            credential_bid=generate_id(app),
            user_bid=aggregate.user_bid,
            provider_name="password",
            subject_id=normalized_identifier,
            subject_format=subject_format,
            identifier=normalized_identifier,
            raw_profile="",
            state=CREDENTIAL_STATE_VERIFIED,
            deleted=0,
        )
        db.session.add(pwd_cred)
        set_password_hash(pwd_cred, hash_password(password))
        db.session.flush()

        ensure_admin_creator_and_demo_permissions(
            app,
            aggregate.user_bid,
            language,
            login_context,
        )

        refreshed = load_user_aggregate(aggregate.user_bid) or aggregate
        user_info = build_user_info_from_aggregate(refreshed)
        token = generate_token(app, refreshed.user_bid)
        user_token = UserToken(user_info, token)

        return AuthResult(
            user=user_info,
            token=user_token,
            credential=pwd_cred,
            is_new_user=True,
            metadata={"user_bid": refreshed.user_bid, "bootstrap": True},
        )

    def verify(self, app: Flask, request: VerificationRequest) -> AuthResult:
        identifier = request.identifier.strip()
        password = request.code  # reuse code field for password

        if not identifier or not password:
            raise_error("server.user.invalidCredentials")

        bootstrap_result = self._maybe_bootstrap_first_admin(app, request)
        if bootstrap_result is not None:
            return bootstrap_result

        # Look up user via phone or email provider credentials
        aggregate = load_user_aggregate_by_identifier(
            identifier, providers=["phone", "email"]
        )
        if not aggregate:
            raise_error("server.user.invalidCredentials")

        # Find password credential – look up by user_bid only.
        # The password credential's identifier may differ from the login
        # identifier (e.g. user registered with phone but logs in with
        # email, or vice-versa), so we must not filter by identifier here.
        password_creds = list_credentials(
            user_bid=aggregate.user_bid, provider_name="password"
        )
        credential = password_creds[0] if password_creds else None
        if not credential:
            raise_error("server.user.invalidCredentials")

        # Read password hash from raw_profile
        password_hash = get_password_hash(credential)
        if not password_hash or not verify_password(password, password_hash):
            raise_error("server.user.invalidCredentials")

        # Build login token
        user_info = build_user_info_from_aggregate(aggregate)
        token = generate_token(app, aggregate.user_bid)
        user_token = UserToken(user_info, token)

        return AuthResult(
            user=user_info,
            token=user_token,
            credential=credential,
            is_new_user=False,
            metadata={"user_bid": aggregate.user_bid},
        )


if not has_provider(PasswordAuthProvider.provider_name):
    register_provider(PasswordAuthProvider)
