"""Password authentication provider.

Supports login via phone number or email + password.
"""

from __future__ import annotations

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
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    find_credential,
    load_user_aggregate_by_identifier,
)
from flaskr.service.user.password_utils import verify_password
from flaskr.service.user.utils import generate_token
from flaskr.service.common.dtos import UserToken
from flaskr.service.common.models import raise_error


class PasswordAuthProvider(AuthProvider):
    """Authenticate via identifier (phone or email) + password."""

    provider_name = "password"
    supports_challenge = False

    def verify(self, app: Flask, request: VerificationRequest) -> AuthResult:
        identifier = request.identifier.strip()
        password = request.code  # reuse code field for password

        if not identifier or not password:
            raise_error("server.user.invalidCredentials")

        # Look up user via phone or email provider credentials
        aggregate = load_user_aggregate_by_identifier(
            identifier, providers=["phone", "email"]
        )
        if not aggregate:
            raise_error("server.user.invalidCredentials")

        # Find password credential
        credential = find_credential(
            provider_name="password",
            identifier=identifier,
            user_bid=aggregate.user_bid,
        )
        if not credential:
            raise_error("server.user.invalidCredentials")

        # Read password hash from the dedicated column
        password_hash = credential.password_hash or ""
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
