"""Password authentication provider.

Supports login via phone number or email + password.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import TYPE_CHECKING

from flaskr.common.config import get_redis_derived_prefix
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
from flaskr.service.user.password_utils import verify_password
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    get_password_hash,
    list_credentials,
    load_user_aggregate_by_identifier,
)
from flaskr.service.user.utils import generate_token
from flaskr.util.datetime import now_utc, to_utc_iso
from redis.exceptions import RedisError

if TYPE_CHECKING:
    from typing import NoReturn

    from flask import Flask


_IDENTIFIER_LIMIT_CONFIG = "PASSWORD_LOGIN_IDENTIFIER_FAILURE_LIMIT"
_IP_LIMIT_CONFIG = "PASSWORD_LOGIN_IP_FAILURE_LIMIT"
_WINDOW_CONFIG = "PASSWORD_LOGIN_FAILURE_WINDOW_SECONDS"
_DEFAULT_IDENTIFIER_LIMIT = 5
_DEFAULT_IP_LIMIT = 20
_DEFAULT_WINDOW_SECONDS = 15 * 60


def _fingerprint(app: Flask, value: str) -> str:
    secret = str(app.config["SECRET_KEY"]).encode("utf-8")
    normalized_value = str(value or "").strip().encode("utf-8")
    return hmac.new(secret, normalized_value, hashlib.sha256).hexdigest()


def _counter_key(app: Flask, scope: str, value: str) -> str:
    prefix = get_redis_derived_prefix(
        "REDIS_KEY_PREFIX_PASSWORD_LOGIN_FAILURE",
        app=app,
    )
    return f"{prefix}{scope}:{_fingerprint(app, value)}"


def _config_int(app: Flask, name: str, default: int) -> int:
    return max(1, int(app.config.get(name, default)))


def _shared_counter_cache(app: Flask):
    """Return the shared Redis backend required by password throttling."""
    from flaskr.dao import get_redis_client

    client = get_redis_client()
    if client is None:
        app.logger.error("Password login failure counters require Redis")
        raise_error("server.user.passwordLoginRateLimited")
    return client


def _read_counter(app: Flask, key: str) -> int:
    try:
        raw_value = _shared_counter_cache(app).get(key)
        return int(raw_value or 0)
    except (RedisError, TypeError, ValueError):
        app.logger.exception("Password login failure counter read failed")
        raise_error("server.user.passwordLoginRateLimited")


def _increment_counter(app: Flask, key: str, window_seconds: int) -> int:
    lock = None
    acquired = False
    try:
        shared_cache = _shared_counter_cache(app)
        lock = shared_cache.lock(
            f"{key}:lock",
            timeout=2,
            blocking_timeout=1,
        )
        acquired = bool(lock.acquire(blocking=True, blocking_timeout=1))
        if not acquired:
            app.logger.warning("Password login failure counter lock is busy")
            raise_error("server.user.passwordLoginRateLimited")
        next_count = _read_counter(app, key) + 1
        shared_cache.set(key, next_count, ex=window_seconds)
    except (RedisError, RuntimeError, TypeError, ValueError):
        app.logger.exception("Password login failure counter update failed")
        raise_error("server.user.passwordLoginRateLimited")
    else:
        return next_count
    finally:
        if acquired and lock is not None:
            try:
                lock.release()
            except (RedisError, RuntimeError):
                app.logger.exception(
                    "Password login failure counter lock release failed",
                )


def _ensure_password_login_allowed(
    app: Flask,
    *,
    identifier: str,
    remote_addr: str,
) -> None:
    identifier_limit = _config_int(
        app,
        _IDENTIFIER_LIMIT_CONFIG,
        _DEFAULT_IDENTIFIER_LIMIT,
    )
    identifier_key = _counter_key(app, "identifier", identifier)
    identifier_blocked = _read_counter(app, identifier_key) >= identifier_limit

    ip_blocked = False
    if remote_addr:
        ip_limit = _config_int(app, _IP_LIMIT_CONFIG, _DEFAULT_IP_LIMIT)
        ip_key = _counter_key(app, "ip", remote_addr)
        ip_blocked = _read_counter(app, ip_key) >= ip_limit

    if identifier_blocked or ip_blocked:
        raise_error("server.user.passwordLoginRateLimited")


def _reject_failed_password_login(
    app: Flask,
    *,
    identifier: str,
    remote_addr: str,
) -> NoReturn:
    window_seconds = _config_int(app, _WINDOW_CONFIG, _DEFAULT_WINDOW_SECONDS)
    identifier_limit = _config_int(
        app,
        _IDENTIFIER_LIMIT_CONFIG,
        _DEFAULT_IDENTIFIER_LIMIT,
    )
    identifier_count = _increment_counter(
        app,
        _counter_key(app, "identifier", identifier),
        window_seconds,
    )

    ip_count = 0
    ip_limit = _config_int(app, _IP_LIMIT_CONFIG, _DEFAULT_IP_LIMIT)
    if remote_addr:
        ip_count = _increment_counter(
            app,
            _counter_key(app, "ip", remote_addr),
            window_seconds,
        )

    app.logger.warning(
        "Password login rejected identifier=%s remote_addr=%s occurred_at=%s "
        "identifier_failures=%d ip_failures=%d",
        _fingerprint(app, identifier)[:12],
        _fingerprint(app, remote_addr)[:12] if remote_addr else "none",
        to_utc_iso(now_utc()),
        identifier_count,
        ip_count,
    )

    if identifier_count >= identifier_limit or (remote_addr and ip_count >= ip_limit):
        raise_error("server.user.passwordLoginRateLimited")
    raise_error("server.user.invalidCredentials")


def clear_password_login_identifier_failures(
    app: Flask,
    *,
    identifier: str,
) -> None:
    try:
        _shared_counter_cache(app).delete(_counter_key(app, "identifier", identifier))
    except (RedisError, RuntimeError):
        app.logger.exception("Password login failure counter clear failed")
        raise_error("server.user.passwordLoginRateLimited")


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
        remote_addr = str(request.metadata.get("remote_addr") or "").strip()

        _ensure_password_login_allowed(
            app,
            identifier=identifier,
            remote_addr=remote_addr,
        )

        if not identifier or not password:
            _reject_failed_password_login(
                app,
                identifier=identifier,
                remote_addr=remote_addr,
            )

        # Look up user via phone or email provider credentials
        aggregate = load_user_aggregate_by_identifier(
            identifier, providers=["phone", "email"]
        )
        if not aggregate:
            _reject_failed_password_login(
                app,
                identifier=identifier,
                remote_addr=remote_addr,
            )

        # Find password credential: look up by user_bid only.
        # The password credential's identifier may differ from the login
        # identifier (e.g. user registered with phone but logs in with
        # email, or vice-versa), so we must not filter by identifier here.
        password_creds = list_credentials(
            user_bid=aggregate.user_bid, provider_name="password"
        )
        credential = password_creds[0] if password_creds else None
        if not credential:
            _reject_failed_password_login(
                app,
                identifier=identifier,
                remote_addr=remote_addr,
            )

        # Read password hash from raw_profile
        password_hash = get_password_hash(credential)
        if not password_hash or not verify_password(password, password_hash):
            _reject_failed_password_login(
                app,
                identifier=identifier,
                remote_addr=remote_addr,
            )

        clear_password_login_identifier_failures(app, identifier=identifier)

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
