"""Create username + password accounts on behalf of an operator.

Such accounts have no phone number or email address. They sign in through the
regular password login, which resolves the username credential created here.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from flaskr.common.cache_provider import cache
from flaskr.common.config import get_redis_key_prefix
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.models import AuthCredential, UserInfo
from flaskr.service.user.password_utils import (
    hash_password,
    validate_password_strength,
)
from flaskr.service.user.repository import (
    create_user_entity,
    set_password_hash,
    upsert_credential,
)
from flaskr.service.user.usernames import USERNAME_PROVIDER, validate_username
from flaskr.util.uuid import generate_id

if TYPE_CHECKING:
    from flask import Flask

NICKNAME_MAX_LENGTH = 50
_LOCK_TIMEOUT_SECONDS = 30
_LOCK_WAIT_SECONDS = 5


def _username_taken(username: str) -> bool:
    """Return whether any active account already answers to ``username``."""
    identity_owner = (
        UserInfo.query.filter(
            UserInfo.user_identify == username,
            UserInfo.deleted == 0,
        )
        .with_for_update()
        .first()
    )
    if identity_owner is not None:
        return True
    credential_owner = (
        AuthCredential.query.filter(
            AuthCredential.identifier == username,
            AuthCredential.deleted == 0,
        )
        .with_for_update()
        .first()
    )
    return credential_owner is not None


def create_operator_password_account(
    app: Flask,
    *,
    operator_user_bid: str,
    username: str,
    password: str,
    nickname: str = "",
) -> dict[str, Any]:
    """Create an account that signs in with ``username`` and ``password``."""
    normalized_operator_user_bid = str(operator_user_bid or "").strip()
    if not normalized_operator_user_bid:
        raise_param_error("operator_user_bid")
    normalized_username = validate_username(username)
    validate_password_strength(str(password or ""))
    normalized_nickname = str(nickname or "").strip()
    if len(normalized_nickname) > NICKNAME_MAX_LENGTH:
        raise_param_error("nickname")

    # Hash outside the lock and transaction; bcrypt is deliberately slow.
    password_hash = hash_password(password)
    user_bid = generate_id(app)

    # Row locks alone do not serialize inserts of a not-yet-existing username
    # under every isolation level, so a short named lock guards the check.
    lock = cache.lock(
        f"{get_redis_key_prefix(app)}operator_account_username:{normalized_username}",
        timeout=_LOCK_TIMEOUT_SECONDS,
        blocking_timeout=_LOCK_WAIT_SECONDS,
    )
    if not lock.acquire(blocking=True, blocking_timeout=_LOCK_WAIT_SECONDS):
        raise_error("server.user.usernameAlreadyRegistered")
    try:
        with app_context_scope(app), unit_of_work():
            if _username_taken(normalized_username):
                raise_error("server.user.usernameAlreadyRegistered")
            create_user_entity(
                user_bid=user_bid,
                identify=normalized_username,
                nickname=normalized_nickname or normalized_username,
                state=USER_STATE_REGISTERED,
            )
            credentials = {
                provider_name: upsert_credential(
                    app,
                    user_bid=user_bid,
                    provider_name=provider_name,
                    subject_id=normalized_username,
                    subject_format=USERNAME_PROVIDER,
                    identifier=normalized_username,
                    metadata={},
                    verified=True,
                )
                for provider_name in (USERNAME_PROVIDER, "password")
            }
            set_password_hash(credentials["password"], password_hash)
    finally:
        # An expired lock must not turn a committed creation into a failure.
        with contextlib.suppress(Exception):
            lock.release()

    app.logger.info(
        "security_event=operator_password_account_created operator_user_bid=%s "
        "target_user_bid=%s",
        normalized_operator_user_bid,
        user_bid,
    )
    return {"user_bid": user_bid, "username": normalized_username}
