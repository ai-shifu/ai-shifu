"""Google OAuth provider implementation."""

from __future__ import annotations

import secrets
import time
from typing import Any

import jwt
from authlib.integrations.requests_client import OAuth2Session
from flask import current_app, request
from flaskr.common.public_urls import build_google_oauth_callback_url
from flaskr.service.common.dtos import UserToken
from flaskr.service.common.models import raise_error
from flaskr.service.profile.api import merge_learner_profile_for_sign_in
from flaskr.service.user.auth.base import (
    AuthProvider,
    AuthResult,
    OAuthCallbackRequest,
)
from flaskr.service.user.auth.factory import has_provider, register_provider
from flaskr.service.user.auth.oauth_origins import (
    resolve_oauth_return_origin,
)
from flaskr.service.user.consts import USER_STATE_REGISTERED, USER_STATE_UNREGISTERED
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    build_user_profile_snapshot_from_aggregate,
    ensure_user_for_identifier,
    find_credential,
    get_user_entity_by_bid,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    transactional_session,
    update_user_entity_fields,
    upsert_credential,
)
from flaskr.service.user.utils import (
    ensure_admin_creator_and_demo_permissions,
    generate_token,
)

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105 - endpoint URL
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
# Lifetime (in seconds) for Google OAuth state.
# Used for stateless signed state tokens (no Redis required).
STATE_TTL = 900


def _encode_state(app, payload: dict[str, Any]) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iat": now,
            "exp": now + STATE_TTL,
            "nonce": secrets.token_hex(16),
            "payload": payload,
        },
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )


def _decode_state(app, state: str) -> dict[str, Any] | None:
    try:
        decoded = jwt.decode(state, app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.exceptions.ExpiredSignatureError:
        return None
    except jwt.exceptions.DecodeError:
        return None
    payload = decoded.get("payload")
    return payload if isinstance(payload, dict) else None


def _extract_browser_language() -> str | None:
    """Extract a reasonable UI language from the incoming request.

    Priority:
    1. First language in the Accept-Language header
    2. None if header is missing or cannot be parsed
    """
    accept_language = request.headers.get("Accept-Language")
    if not accept_language:
        return None

    # Example header: "zh-CN,zh;q=0.9,en;q=0.8"
    first_part = accept_language.split(",")[0].strip()
    if not first_part:
        return None

    # Strip any quality value if present, e.g. "en-US;q=0.9" -> "en-US"
    language_token = first_part.split(";")[0].strip()
    if not language_token:
        return None

    # Normalize case for language-region tags, e.g. "en-us" -> "en-US"
    segments = language_token.split("-")
    if len(segments) == 1:
        return segments[0].lower()

    primary = segments[0].lower()
    region = segments[1].upper()
    return f"{primary}-{region}"


def _resolve_redirect_uri(app, explicit_uri: str | None = None) -> str:
    del app, explicit_uri
    return build_google_oauth_callback_url()


def _require_matching_initiator(
    state_payload: dict[str, Any], current_user_id: str | None
) -> None:
    """Refuse a code meant for a different browser session.

    Only applies to flows that recorded a return origin, i.e. the ones whose
    code gets handed to another domain. The origin comes from headers a caller
    can forge, so without this an attacker could name their own verified custom
    domain and have someone else's authorization code delivered there.
    """
    expected_initiator = str(state_payload.get("initiator_user_id") or "").strip()
    if not state_payload.get("origin"):
        return
    if not expected_initiator:
        raise_error("server.user.googleOAuthStateInvalid")
    if str(current_user_id or "").strip() != expected_initiator:
        current_app.logger.warning(
            "Google OAuth callback presented by a different session than started it"
        )
        raise_error("server.user.googleOAuthStateInvalid")


def resolve_state_return_origin(app, state: str | None) -> str:
    """Return the validated origin recorded in an OAuth state, or "".

    The shared callback page calls this to learn whether it should forward the
    authorization code to the domain the login started from. Re-validated here
    rather than trusted from the state, so revoking a custom domain takes effect
    on in-flight logins too.
    """
    if not state:
        return ""
    payload = _decode_state(app, state)
    if not payload:
        return ""
    return resolve_oauth_return_origin(app, payload.get("origin"))


class GoogleAuthProvider(AuthProvider):
    provider_name = "google"
    supports_oauth = True

    def _resolve_token_endpoint(self, app) -> str:
        return app.config.get("GOOGLE_OAUTH_TOKEN_ENDPOINT", TOKEN_ENDPOINT)

    def _resolve_userinfo_endpoint(self, app) -> str:
        return app.config.get("GOOGLE_OAUTH_USERINFO_ENDPOINT", USERINFO_ENDPOINT)

    def verify(self, app, request):
        raise NotImplementedError("GoogleAuthProvider only supports OAuth flows")

    def _create_session(self, app, redirect_uri: str) -> OAuth2Session:
        client_id = app.config.get("GOOGLE_OAUTH_CLIENT_ID")
        client_secret = app.config.get("GOOGLE_OAUTH_CLIENT_SECRET")
        scopes = ["openid", "email", "profile"]
        return OAuth2Session(
            client_id=client_id,
            client_secret=client_secret,
            scope=scopes,
            redirect_uri=redirect_uri,
        )

    def begin_oauth(self, app, metadata: dict[str, Any]) -> dict[str, Any]:
        redirect_uri = _resolve_redirect_uri(app, metadata.get("redirect_uri"))
        login_context = metadata.get("login_context")
        session = self._create_session(app, redirect_uri)

        # Prefer explicit UI language from frontend (current interface language),
        # and fall back to browser Accept-Language header if not provided.
        ui_language_from_frontend = metadata.get("language")
        ui_language = ui_language_from_frontend or _extract_browser_language()

        # Do not force re-consent/offline access by default. For a simple web login
        # flow we only need an authorization code to fetch basic profile info.
        # Forcing "prompt=consent" and "access_type=offline" can add extra Google
        # interstitial/confirmation steps and degrades UX.
        create_url_kwargs: dict[str, Any] = {}
        # Google respects both "hl" and (for some flows) "ui_locales".
        if ui_language:
            create_url_kwargs["hl"] = ui_language
            create_url_kwargs["ui_locales"] = ui_language

        state_payload: dict[str, Any] = {
            "redirect_uri": redirect_uri,
            "login_context": login_context,
        }
        # All domains share one Google callback, so remember where the browser
        # came from to hand it back afterwards. The origin is derived from
        # headers an attacker can set, so it is only honored together with the
        # session that started the flow: the callback requires the same session
        # to present the code. Without a session there is nothing to pair it
        # with, so the login simply finishes on the shared callback domain.
        return_origin = resolve_oauth_return_origin(app, metadata.get("origin"))
        initiator_user_id = str(metadata.get("initiator_user_id") or "").strip()
        if return_origin and initiator_user_id:
            state_payload["origin"] = return_origin
            state_payload["initiator_user_id"] = initiator_user_id
        # Persist the interface language so we can use it
        # when creating or updating the user record.
        if ui_language_from_frontend:
            state_payload["language"] = ui_language_from_frontend
        elif ui_language:
            state_payload["language"] = ui_language

        state = _encode_state(app, state_payload)
        authorization_url, _ = session.create_authorization_url(
            AUTHORIZATION_ENDPOINT,
            state=state,
            **create_url_kwargs,
        )
        current_app.logger.info("Google OAuth begin state=%s", state)
        return {"authorization_url": authorization_url, "state": state}

    def handle_oauth_callback(self, app, request: OAuthCallbackRequest) -> AuthResult:
        if not request.code or not request.state:
            current_app.logger.warning(
                "Google OAuth callback missing code or state: has_code=%s, has_state=%s",
                bool(request.code),
                bool(request.state),
            )
            raise_error("server.user.googleOAuthStateInvalid")

        current_app.logger.info("Google OAuth callback state=%s", request.state)
        state_payload = _decode_state(app, request.state)
        if not state_payload:
            raise_error("server.user.googleOAuthStateInvalid")

        redirect_uri = None
        login_context = None
        language: str | None = None
        try:
            redirect_uri = state_payload.get("redirect_uri")
            login_context = state_payload.get("login_context")
            language = state_payload.get("language")
        except Exception:  # noqa: BLE001 - defensive fallback
            current_app.logger.warning("Failed to parse Google OAuth state payload")

        _require_matching_initiator(state_payload, request.current_user_id)

        redirect_uri = _resolve_redirect_uri(app, redirect_uri)
        session = self._create_session(app, redirect_uri)

        token = session.fetch_token(
            self._resolve_token_endpoint(app),
            code=request.code,
        )

        resp = session.get(self._resolve_userinfo_endpoint(app))
        resp.raise_for_status()
        profile = resp.json()

        # If Google returns a locale and we do not yet have a language
        # from the stored state, fall back to the profile locale.
        if not language:
            profile_locale = profile.get("locale")
            if isinstance(profile_locale, str) and profile_locale:
                language = profile_locale.replace("_", "-")

        subject_id = profile.get("sub")
        email = profile.get("email")
        if not subject_id or not email:
            raise RuntimeError("Google profile missing required identifiers")

        email = email.lower()
        email_verified = bool(profile.get("email_verified", False))
        credential = find_credential(provider_name=self.provider_name, identifier=email)

        origin_user_id = getattr(request, "current_user_id", None)
        origin_aggregate = (
            load_user_aggregate(origin_user_id) if origin_user_id else None
        )

        aggregate = None
        created_user = False
        credential_record = None

        with transactional_session():
            if credential:
                aggregate = load_user_aggregate(credential.user_bid)

            if not aggregate:
                aggregate = load_user_aggregate_by_identifier(
                    email, providers=["email"]
                )

            if not aggregate and origin_aggregate:
                aggregate = origin_aggregate

            if aggregate and origin_user_id and aggregate.user_bid != origin_user_id:
                merge_learner_profile_for_sign_in(
                    source_user_id=origin_user_id,
                    target_user_id=aggregate.user_bid,
                )

            if aggregate:
                entity = get_user_entity_by_bid(
                    aggregate.user_bid, include_deleted=True
                )
                if entity:
                    updates: dict[str, Any] = {"identify": email}
                    if email_verified and aggregate.state in (
                        USER_STATE_UNREGISTERED,
                        0,
                    ):
                        updates["state"] = USER_STATE_REGISTERED
                    display_name = profile.get("name")
                    if display_name:
                        updates["nickname"] = display_name
                    picture = profile.get("picture")
                    if picture and not aggregate.avatar:
                        updates["avatar"] = picture
                    if language:
                        updates["language"] = language
                    update_user_entity_fields(entity, **updates)

                    # Ensure an email credential exists for the resolved user
                    upsert_credential(
                        app,
                        user_bid=aggregate.user_bid,
                        provider_name="email",
                        subject_id=email,
                        subject_format="email",
                        identifier=email,
                        metadata={},
                        verified=profile.get("email_verified", False),
                    )
            else:
                defaults = {
                    "user_bid": origin_user_id or secrets.token_hex(16),
                    "nickname": profile.get("name") or "",
                    "avatar": profile.get("picture"),
                    "language": language,
                    "state": (
                        USER_STATE_REGISTERED
                        if email_verified
                        else USER_STATE_UNREGISTERED
                    ),
                }
                aggregate, created_user = ensure_user_for_identifier(
                    app,
                    provider="email",
                    identifier=email,
                    defaults=defaults,
                )

            credential_record = upsert_credential(
                app,
                user_bid=aggregate.user_bid,
                provider_name=self.provider_name,
                subject_id=subject_id,
                subject_format="google",
                identifier=email,
                metadata=profile,
                verified=profile.get("email_verified", False),
            )

            # Reuse the first-account bootstrap logic across login methods so
            # Google can also initialize a fresh self-hosted deployment.
            creator_granted_now = False
            if email_verified:
                from flaskr.service.user.phone_flow import init_first_course

                creator_granted_now = init_first_course(app, aggregate.user_bid)

            # Optionally grant creator and demo-course permissions for admin logins
            creator_granted_now = (
                ensure_admin_creator_and_demo_permissions(
                    app, aggregate.user_bid, aggregate.language, login_context
                )
                or creator_granted_now
            )

            refreshed = load_user_aggregate(aggregate.user_bid)
            if not refreshed:
                raise RuntimeError(
                    "Failed to refresh user aggregate after Google OAuth"
                )
            user_dto = build_user_info_from_aggregate(refreshed)
            token_value = generate_token(app, refreshed.user_bid)
            user_token = UserToken(userInfo=user_dto, token=token_value)
            snapshot = build_user_profile_snapshot_from_aggregate(refreshed)

        return AuthResult(
            user=user_dto,
            token=user_token,
            credential=credential_record,
            is_new_user=created_user,
            metadata={
                "language": language,
                "login_context": login_context,
                "token_response": token,
                "profile": profile,
                "creator_granted_now": creator_granted_now,
                "snapshot": snapshot.to_dict(),
            },
        )


if not has_provider(GoogleAuthProvider.provider_name):
    register_provider(GoogleAuthProvider)
