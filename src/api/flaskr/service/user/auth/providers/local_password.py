"""Password authentication for deliberately provisioned local administrators."""

from __future__ import annotations

import hashlib
import hmac
from typing import TYPE_CHECKING

from flaskr.dao.uow import unit_of_work
from flaskr.service.common.dtos import UserToken
from flaskr.service.common.models import AppError, raise_error
from flaskr.service.user.auth.base import AuthProvider, AuthResult, VerificationRequest
from flaskr.service.user.auth.factory import has_provider, register_provider
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
)
from flaskr.service.user.installation_models import LocalAdminAccount
from flaskr.service.user.local_accounts import (
    LOCAL_ADMIN_PROVIDER,
    lock_local_admin_credentials,
    normalize_local_username,
)
from flaskr.service.user.password_rate_limit import PasswordLoginAttempt
from flaskr.service.user.password_utils import verify_password
from flaskr.service.user.repository import (
    UserAggregate,
    build_user_info_from_aggregate,
    find_credential,
    get_password_hash,
    load_user_aggregate,
)
from flaskr.service.user.utils import create_token_value

if TYPE_CHECKING:
    from flask import Flask
    from flaskr.service.user.models import AuthCredential


_DUMMY_PASSWORD_HASH = (
    # Public work-equalization hash, never an account credential.
    "$2b$12$yJ8OaHGqFRZ4ZmjGk8y63OUgJxVcMfcHbzXOMmD9Zc2tCKxqcQ9pK"  # noqa: S105
)
_ACTIVE_ACCOUNT_STATES = frozenset(
    {USER_STATE_REGISTERED, USER_STATE_TRAIL, USER_STATE_PAID}
)


def _credential_version(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()


def _load_login_evidence(
    username: str,
) -> tuple[UserAggregate | None, AuthCredential | None]:
    account = LocalAdminAccount.query.filter_by(username=username, deleted=0).first()
    aggregate = load_user_aggregate(account.user_bid) if account is not None else None
    if (
        aggregate is None
        or aggregate.deleted
        or not aggregate.is_operator
        or aggregate.state not in _ACTIVE_ACCOUNT_STATES
    ):
        return None, None
    credential = find_credential(
        provider_name=LOCAL_ADMIN_PROVIDER,
        identifier=username,
        user_bid=aggregate.user_bid,
    )
    if (
        credential is None
        or account is None
        or credential.credential_bid != account.credential_bid
        or credential.state != CREDENTIAL_STATE_VERIFIED
    ):
        return None, None
    return aggregate, credential


def _limit_identity(username: str, aggregate: UserAggregate | None) -> str:
    return (
        f"user:{aggregate.user_bid}"
        if aggregate is not None
        else f"local-identifier:{username}"
    )


def _raise_account_blocked(app: Flask, response_identity: str) -> None:
    with PasswordLoginAttempt(app, response_identity) as response_attempt:
        if response_attempt.cooldown_active:
            raise_error("server.user.passwordLoginTooManyAttempts")
        response_attempt.record_failure()
        if response_attempt.cooldown_active:
            raise_error("server.user.passwordLoginTooManyAttempts")
    raise_error("server.user.invalidCredentials")


class LocalPasswordAuthProvider(AuthProvider):
    """Authenticate a local username without asserting contact ownership."""

    provider_name = LOCAL_ADMIN_PROVIDER
    supports_challenge = False

    def verify(self, app: Flask, request: VerificationRequest) -> AuthResult:
        """Verify the local credential using the shared password attempt budget."""
        try:
            username = normalize_local_username(request.identifier)
        except AppError:
            verify_password(request.code, _DUMMY_PASSWORD_HASH)
            raise_error("server.user.invalidCredentials")
        password = request.code
        if not password:
            verify_password(password, _DUMMY_PASSWORD_HASH)
            raise_error("server.user.invalidCredentials")
        response_identity = f"local-response:{username}"

        with unit_of_work():
            aggregate, _ = _load_login_evidence(username)
            limit_identity = _limit_identity(username, aggregate)

        for resolution_attempt in range(2):
            with PasswordLoginAttempt(app, limit_identity) as attempt:
                if attempt.blocked:
                    verify_password(password, _DUMMY_PASSWORD_HASH)
                    _raise_account_blocked(app, response_identity)
                with unit_of_work():
                    aggregate, credential = _load_login_evidence(username)
                    current_identity = _limit_identity(username, aggregate)
                    password_hash = get_password_hash(credential) if credential else ""
                    user_info = (
                        build_user_info_from_aggregate(aggregate)
                        if aggregate is not None
                        else None
                    )
                    credential_bid = credential.credential_bid if credential else ""

                if current_identity != limit_identity:
                    limit_identity = current_identity
                    if resolution_attempt == 0:
                        continue
                    raise_error("server.user.passwordLoginTooManyAttempts")
                matches = verify_password(
                    password, password_hash or _DUMMY_PASSWORD_HASH
                )
                if aggregate is None or credential is None or not matches:
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

        if aggregate is None or user_info is None:
            raise_error("server.user.invalidCredentials")
        token = UserToken(user_info, create_token_value(app, aggregate.user_bid))
        return AuthResult(
            user=user_info,
            token=token,
            credential=credential,
            is_new_user=False,
            metadata={
                "user_bid": aggregate.user_bid,
                "local_username": username,
                "local_credential_bid": credential_bid,
                "credential_version": _credential_version(password_hash),
            },
        )


def confirm_local_admin_login_for_token_issue(
    *,
    user_bid: str,
    credential_bid: str,
    username: str,
    credential_version: str,
) -> None:
    """Lock and recheck local-login authority immediately before storing a token."""
    _user, _account, credential = lock_local_admin_credentials(
        user_bid=user_bid,
        username=username,
        credential_bid=credential_bid,
    )
    if not isinstance(credential_version, str) or not hmac.compare_digest(
        _credential_version(get_password_hash(credential)), credential_version
    ):
        raise_error("server.user.invalidCredentials")


if not has_provider(LocalPasswordAuthProvider.provider_name):
    register_provider(LocalPasswordAuthProvider)
