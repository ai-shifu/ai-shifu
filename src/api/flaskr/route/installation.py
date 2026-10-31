"""Expose bounded first-run setup and independent local administrator login."""

from __future__ import annotations

import contextlib
import hashlib
from typing import TYPE_CHECKING

from flask import Response, request

from flaskr.common.client_ip import resolve_client_ip
from flaskr.common.http import bypass_token_validation, sensitive_body
from flaskr.dao.uow import unit_of_work
from flaskr.i18n import _translations, set_language
from flaskr.service.common.models import AppError, raise_error, raise_param_error
from flaskr.service.user.auth import get_provider
from flaskr.service.user.auth.base import VerificationRequest
from flaskr.service.user.auth.providers.password import (
    confirm_password_login_for_token_issue,
)
from flaskr.service.user.installation import (
    get_installation_status,
    initialize_admin,
    normalize_setup_origin,
)
from flaskr.service.user.password_rate_limit import PasswordLoginAttempt
from flaskr.service.user.post_auth import PostAuthContext, run_post_auth_extensions
from flaskr.service.user.token_store import token_store
from flaskr.service.user.utils import persist_token

from .common import make_common_response

if TYPE_CHECKING:
    from flask import Flask


_SENSITIVE_BODY_MAX_BYTES = 32 * 1024


def _json_response(data: object) -> Response:
    return Response(make_common_response(data), mimetype="application/json")


def _payload() -> dict[str, object]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise_param_error("request")
    return payload


def _text(payload: dict[str, object], key: str, max_bytes: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise_param_error(key)
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise_param_error(key)
    if size > max_bytes:
        if key == "password":
            raise_error("server.installation.passwordTooLong")
        raise_param_error(key)
    return value


def _language(payload: dict[str, object]) -> str:
    value = payload.get("language") or "en-US"
    if not isinstance(value, str) or len(value) > 35:
        raise_param_error("language")
    if value not in _translations:
        value = "en-US"
    with contextlib.suppress(Exception):
        set_language(value)
    return value


def _browser_origin() -> str:
    # Read the browser's Origin directly. Forwarded headers must not substitute
    # for a missing origin on this capability-bearing public entrypoint.
    origin = request.headers.get("Origin", "")
    if not origin or len(origin) > 512 or origin == "null":
        raise_error("server.installation.invalidSetupOrigin")
    return normalize_setup_origin(origin)


def _finish_login(
    app: Flask,
    *,
    identifier: str,
    password: str,
    language: str,
    expected_user_bid: str | None = None,
) -> Response:
    provider = get_provider("password")
    result = provider.verify(
        app,
        VerificationRequest(identifier=identifier, code=password),
    )
    if not result.user.is_operator or (
        expected_user_bid and result.user.user_id != expected_user_bid
    ):
        raise_error("server.user.invalidCredentials")
    try:
        with unit_of_work():
            confirm_password_login_for_token_issue(
                user_bid=result.user.user_id,
                credential_bid=str(
                    result.metadata.get("password_credential_bid") or ""
                ),
                identifier=str(result.metadata.get("verified_identifier") or ""),
                credential_identifier=str(
                    result.metadata.get("password_credential_identifier") or ""
                ),
                credential_version=str(result.metadata.get("credential_version") or ""),
                require_operator=True,
            )
            persist_token(app, user_id=result.user.user_id, token=result.token.token)
    except Exception:
        token_store.discard_uncommitted(app, result.token.token)
        raise
    run_post_auth_extensions(
        app,
        PostAuthContext(
            user_id=result.user.user_id,
            source="password",
            login_context="admin",
            created_new_user=False,
            creator_granted_now=False,
            language=language,
        ),
    )
    return _json_response(result.token)


def register_installation_routes(app: Flask, path_prefix: str) -> None:
    """Register the installation endpoints without altering ordinary login."""

    @app.route(path_prefix + "/status", methods=["GET"])
    @bypass_token_validation
    @sensitive_body(max_bytes=_SENSITIVE_BODY_MAX_BYTES)
    def installation_status() -> Response:
        """Return public setup availability without exposing account or code data."""
        return _json_response(get_installation_status(app))

    @app.route(path_prefix + "/initialize", methods=["POST"])
    @bypass_token_validation
    @sensitive_body(max_bytes=_SENSITIVE_BODY_MAX_BYTES)
    def installation_initialize() -> Response:
        """Consume one installation claim and sign in the newly created owner."""
        origin = _browser_origin()
        payload = _payload()
        language = _language(payload)
        setup_token = _text(payload, "setup_token", 256)
        identifier = _text(payload, "identifier", 254)
        password = _text(payload, "password", 72)
        client_ip = resolve_client_ip()
        rate_identity = "installation:" + hashlib.sha256(client_ip.encode()).hexdigest()
        with PasswordLoginAttempt(app, rate_identity) as attempt:
            if attempt.blocked:
                raise_error("server.installation.setupRateLimited")
            try:
                user_bid = initialize_admin(
                    app,
                    setup_token=setup_token,
                    identifier=identifier,
                    password=password,
                    language=language,
                    request_origin=origin,
                )
            except AppError:
                attempt.record_failure()
                raise
            # Setup is already committed; cache cleanup is not authority to
            # undo it. The password provider applies its own login guard.
            attempt.clear()
        # Installation has committed. A session/cache failure must not reopen it;
        # the owner can use the normal local login entrypoint to retry sign-in.
        return _finish_login(
            app,
            identifier=identifier,
            password=password,
            language=language,
            expected_user_bid=user_bid,
        )

    @app.route(path_prefix + "/login", methods=["POST"])
    @bypass_token_validation
    @sensitive_body(max_bytes=_SENSITIVE_BODY_MAX_BYTES)
    def installation_login() -> Response:
        """Sign in a local administrator independently of learner login switches."""
        _browser_origin()
        payload = _payload()
        language = _language(payload)
        # Old clients may still send their pre-release local username. Only
        # sign-in accepts that spelling; setup always requires a contact label.
        key = "identifier" if "identifier" in payload else "username"
        identifier = _text(payload, key, 254)
        password = _text(payload, "password", 72)
        return _finish_login(
            app, identifier=identifier, password=password, language=language
        )
