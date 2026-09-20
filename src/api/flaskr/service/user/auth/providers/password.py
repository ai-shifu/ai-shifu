"""Password authentication provider.

Supports login via phone number or email + password.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.service.common.dtos import UserToken
from flaskr.service.common.models import raise_error
from flaskr.service.common.phone_numbers import normalize_phone_identifier
from flaskr.service.user.auth.base import (
    AuthProvider,
    AuthResult,
    VerificationRequest,
)
from flaskr.service.user.auth.factory import (
    has_provider,
    register_provider,
)
from flaskr.service.user.password_rate_limit import PasswordLoginAttempt
from flaskr.service.user.password_utils import verify_password
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    get_password_hash,
    list_credentials,
    load_user_aggregate_by_identifier,
)
from flaskr.service.user.utils import generate_token

if TYPE_CHECKING:
    from flask import Flask


_DUMMY_PASSWORD_HASH = (
    # This public hash only equalizes bcrypt work for missing credentials.
    "$2b$12$yJ8OaHGqFRZ4ZmjGk8y63OUgJxVcMfcHbzXOMmD9Zc2tCKxqcQ9pK"  # noqa: S105
)


class PasswordAuthProvider(AuthProvider):
    """Authenticate via identifier (phone or email) + password."""

    provider_name = "password"
    supports_challenge = False

    def verify(self, app: Flask, request: VerificationRequest) -> AuthResult:
        """Verify the supplied authentication credential."""
        raw_identifier = request.identifier.strip()
        identifier = (
            raw_identifier.lower()
            if "@" in raw_identifier
            else normalize_phone_identifier(raw_identifier)
        )
        password = request.code  # reuse code field for password

        if not identifier or not password:
            raise_error("server.user.invalidCredentials")

        # Look up user via phone or email provider credentials
        aggregate = load_user_aggregate_by_identifier(
            identifier, providers=["phone", "email"]
        )
        limit_identity = (
            f"user:{aggregate.user_bid}"
            if aggregate is not None
            else f"identifier:{identifier}"
        )
        with PasswordLoginAttempt(app, limit_identity) as attempt:
            if attempt.blocked:
                raise_error("server.user.passwordLoginTooManyAttempts")

            # Find password credential by account rather than login identifier so
            # phone and email aliases share the same password and failure budget.
            password_creds = (
                list_credentials(user_bid=aggregate.user_bid, provider_name="password")
                if aggregate is not None
                else []
            )
            credential = password_creds[0] if password_creds else None
            password_hash = get_password_hash(credential) if credential else ""
            password_matches = verify_password(
                password, password_hash or _DUMMY_PASSWORD_HASH
            )
            if aggregate is None or credential is None or not password_matches:
                attempt.record_failure()
                if attempt.blocked:
                    raise_error("server.user.passwordLoginTooManyAttempts")
                raise_error("server.user.invalidCredentials")

            attempt.clear()

        # Session creation does not mutate the failure budget and should not hold
        # the per-account Redis lock longer than password verification requires.
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
