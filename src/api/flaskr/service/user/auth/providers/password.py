"""Password authentication provider.

Supports login via phone number or email + password.
"""

from __future__ import annotations

import hmac
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
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
)
from flaskr.service.user.installation_models import LocalAdminAccount
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.password_flow import lock_password_credential
from flaskr.service.user.password_rate_limit import PasswordLoginAttempt
from flaskr.service.user.password_utils import (
    password_credential_version,
    verify_password,
)
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    find_credential,
    get_password_hash,
    list_credentials,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
)
from flaskr.service.user.utils import create_token_value

if TYPE_CHECKING:
    from flask import Flask


_DUMMY_PASSWORD_HASH = (
    # This public hash only equalizes bcrypt work for missing credentials.
    "$2b$12$yJ8OaHGqFRZ4ZmjGk8y63OUgJxVcMfcHbzXOMmD9Zc2tCKxqcQ9pK"  # noqa: S105
)
_ACTIVE_ACCOUNT_STATES = frozenset(
    {USER_STATE_REGISTERED, USER_STATE_TRAIL, USER_STATE_PAID}
)


def _legacy_password_account(identifier: str) -> LocalAdminAccount | None:
    """Read only an explicit pre-release username binding, never create an alias."""
    return LocalAdminAccount.query.filter_by(
        identifier=identifier,
        identifier_kind="legacy_username",
        deleted=0,
    ).first()


def _load_password_user(identifier: str) -> object | None:
    aggregate = load_user_aggregate_by_identifier(
        identifier, providers=["phone", "email"]
    )
    if aggregate is not None:
        return aggregate
    account = _legacy_password_account(identifier)
    if account is None:
        return None
    aggregate = load_user_aggregate(account.user_bid)
    credential = find_credential(
        provider_name="password", identifier=identifier, user_bid=account.user_bid
    )
    if (
        aggregate is None
        or not aggregate.is_operator
        or aggregate.state not in _ACTIVE_ACCOUNT_STATES
        or not aggregate.identify.startswith("local:")
        or credential is None
        or credential.credential_bid != account.credential_bid
    ):
        return None
    return aggregate


class PasswordAuthProvider(AuthProvider):
    """Authenticate via identifier (phone or email) + password."""

    provider_name = "password"
    supports_challenge = False

    def verify(self, app: Flask, request: VerificationRequest) -> AuthResult:
        """Verify the supplied authentication credential."""
        raw_identifier = request.identifier.strip().lower()
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
            aggregate = _load_password_user(identifier)
            limit_identity = self._limit_identity(identifier, aggregate)

        for resolution_attempt in range(2):
            with PasswordLoginAttempt(app, limit_identity) as attempt:
                if attempt.blocked:
                    verify_password(password, _DUMMY_PASSWORD_HASH)
                    self._raise_account_blocked(app, response_identity)

                # Re-read after acquiring the guard so a newly linked alias cannot
                # authenticate under a stale or different account lock.
                with unit_of_work():
                    aggregate = _load_password_user(identifier)
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
                    if (
                        credential is not None
                        and credential.state != CREDENTIAL_STATE_VERIFIED
                    ):
                        credential = None
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
                if (
                    aggregate is None
                    or credential is None
                    or not password_hash
                    or not password_matches
                ):
                    with PasswordLoginAttempt(
                        app, response_identity
                    ) as response_attempt:
                        response_attempt.record_failure()
                        attempt.record_failure()
                        if response_attempt.cooldown_active:
                            raise_error("server.user.passwordLoginTooManyAttempts")
                    raise_error("server.user.invalidCredentials")

                if not attempt.clear():
                    raise_error("server.user.passwordLoginTooManyAttempts")
                with PasswordLoginAttempt(app, response_identity) as response_attempt:
                    if not response_attempt.clear():
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
            metadata={
                "user_bid": aggregate.user_bid,
                "verified_identifier": identifier,
                "password_credential_bid": credential.credential_bid,
                "password_credential_identifier": credential.identifier,
                "credential_version": password_credential_version(password_hash),
            },
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
            response_attempt.record_failure()
            if response_attempt.cooldown_active:
                raise_error("server.user.passwordLoginTooManyAttempts")
        raise_error("server.user.invalidCredentials")


def confirm_password_login_for_token_issue(
    *,
    identifier: str,
    user_bid: str,
    credential_bid: str,
    credential_identifier: str,
    credential_version: str,
    require_operator: bool = False,
) -> None:
    """Recheck the password and identity under the credential write lock."""
    user, password_credential = lock_password_credential(
        user_bid=user_bid, credential_bid=credential_bid
    )
    if require_operator and (
        not user.is_operator or user.state not in _ACTIVE_ACCOUNT_STATES
    ):
        raise_error("server.user.invalidCredentials")
    contact_matches = user.user_identify == identifier
    if not contact_matches:
        contact_matches = (
            AuthCredential.query.filter(
                AuthCredential.user_bid == user_bid,
                AuthCredential.provider_name.in_(["phone", "email"]),
                AuthCredential.identifier == identifier,
                AuthCredential.deleted == 0,
            )
            .with_for_update()
            .first()
            is not None
        )
    if not contact_matches:
        account = _legacy_password_account(identifier)
        contact_matches = bool(
            account is not None
            and account.user_bid == user_bid
            and account.credential_bid == credential_bid
            and user.user_identify.startswith("local:")
            and user.is_operator
        )
    if (
        not contact_matches
        or password_credential.identifier != credential_identifier
        or not get_password_hash(password_credential)
        or not isinstance(credential_version, str)
        or not hmac.compare_digest(
            password_credential_version(get_password_hash(password_credential)),
            credential_version,
        )
    ):
        raise_error("server.user.invalidCredentials")


if not has_provider(PasswordAuthProvider.provider_name):
    register_provider(PasswordAuthProvider)
