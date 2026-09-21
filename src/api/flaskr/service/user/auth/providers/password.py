"""Password authentication provider.

Supports login via phone number or email + password.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.dao.uow import unit_of_work
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
from flaskr.service.user.utils import create_token_value

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
        response_identity = f"response:{identifier}"

        # Resolve aliases in a completed transaction so requests waiting for the
        # Redis guard never retain a checked-out database connection.
        with unit_of_work():
            aggregate = load_user_aggregate_by_identifier(
                identifier, providers=["phone", "email"]
            )
            limit_identity = self._limit_identity(identifier, aggregate)

        for resolution_attempt in range(2):
            with PasswordLoginAttempt(app, limit_identity) as attempt:
                if attempt.blocked:
                    verify_password(password, _DUMMY_PASSWORD_HASH)
                    self._raise_account_blocked(app, response_identity)

                # Re-read after acquiring the guard so a newly linked alias cannot
                # authenticate under a stale or different account lock.
                with unit_of_work():
                    aggregate = load_user_aggregate_by_identifier(
                        identifier, providers=["phone", "email"]
                    )
                    current_identity = self._limit_identity(identifier, aggregate)
                    password_creds = (
                        list_credentials(
                            user_bid=aggregate.user_bid,
                            provider_name="password",
                        )
                        if aggregate is not None
                        else []
                    )
                    credential = password_creds[0] if password_creds else None
                    password_hash = get_password_hash(credential) if credential else ""
                    user_info = (
                        build_user_info_from_aggregate(aggregate)
                        if aggregate is not None
                        else None
                    )

                if current_identity != limit_identity:
                    limit_identity = current_identity
                    if resolution_attempt == 0:
                        continue
                    raise_error("server.user.passwordLoginTooManyAttempts")

                password_matches = verify_password(
                    password, password_hash or _DUMMY_PASSWORD_HASH
                )
                if aggregate is None or credential is None or not password_matches:
                    with PasswordLoginAttempt(
                        app, response_identity
                    ) as response_attempt:
                        response_attempt.record_failure()
                        attempt.record_failure()
                        if response_attempt.cooldown_active:
                            raise_error("server.user.passwordLoginTooManyAttempts")
                    raise_error("server.user.invalidCredentials")

                with PasswordLoginAttempt(app, response_identity) as response_attempt:
                    if not response_attempt.clear() or not attempt.clear():
                        raise_error("server.user.passwordLoginTooManyAttempts")
                break

        # Session creation does not mutate the failure budget and should not hold
        # the per-account Redis lock longer than password verification requires.
        if aggregate is None or user_info is None:
            raise_error("server.user.invalidCredentials")
        token = create_token_value(app, aggregate.user_bid)
        user_token = UserToken(user_info, token)

        return AuthResult(
            user=user_info,
            token=user_token,
            credential=credential,
            is_new_user=False,
            metadata={"user_bid": aggregate.user_bid},
        )

    @staticmethod
    def _limit_identity(identifier: str, aggregate: object | None) -> str:
        user_bid = getattr(aggregate, "user_bid", None)
        return f"user:{user_bid}" if user_bid else f"identifier:{identifier}"

    @staticmethod
    def _raise_account_blocked(app: Flask, response_identity: str) -> None:
        """Reject a blocked account without disclosing alias relationships."""
        with PasswordLoginAttempt(app, response_identity) as response_attempt:
            if response_attempt.cooldown_active:
                raise_error("server.user.passwordLoginTooManyAttempts")
        raise_error("server.user.invalidCredentials")


if not has_provider(PasswordAuthProvider.provider_name):
    register_provider(PasswordAuthProvider)
