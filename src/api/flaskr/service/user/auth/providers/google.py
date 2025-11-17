"""Google OAuth provider implementation."""

from __future__ import annotations

import secrets
from typing import Any, Dict

from authlib.integrations.requests_client import OAuth2Session
import json
from typing import Optional
from urllib.parse import urljoin

from flask import current_app, request

from flaskr.dao import redis_client as redis
from flaskr.service.user.auth.base import (
    AuthProvider,
    AuthResult,
    OAuthCallbackRequest,
)
from flaskr.service.user.auth.factory import has_provider, register_provider
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
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.utils import (
    generate_token,
    ensure_admin_creator_and_demo_permissions,
)
from flaskr.service.common.dtos import UserToken


AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
STATE_TTL = 300


def _state_storage_key(state: str) -> str:
    prefix = current_app.config.get("REDIS_KEY_PREFIX_USER", "ai-shifu:user:")
    return f"{prefix}google_oauth_state:{state}"


def _extract_browser_language() -> Optional[str]:
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


def _resolve_redirect_uri(app, explicit_uri: Optional[str] = None) -> str:
    if explicit_uri:
        return explicit_uri

    forwarded_proto = request.headers.get("X-Forwarded-Proto")
    scheme = forwarded_proto or request.scheme
    forwarded_host = request.headers.get("X-Forwarded-Host")
    host = forwarded_host or request.host
    base_url = f"{scheme}://{host}"
    return urljoin(f"{base_url}/", "login/google-callback")


class GoogleAuthProvider(AuthProvider):
    provider_name = "google"
    supports_oauth = True

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

    def begin_oauth(self, app, metadata: Dict[str, Any]) -> Dict[str, Any]:
        redirect_uri = _resolve_redirect_uri(app, metadata.get("redirect_uri"))
        login_context = metadata.get("login_context")
        session = self._create_session(app, redirect_uri)

        # Prefer explicit UI language from frontend (current interface language),
        # and fall back to browser Accept-Language header if not provided.
        ui_language_from_frontend = metadata.get("language")
        ui_language = ui_language_from_frontend or _extract_browser_language()

        create_url_kwargs: Dict[str, Any] = {
            "prompt": "consent",
            "access_type": "offline",
        }
        # Google respects both "hl" and (for some flows) "ui_locales".
        if ui_language:
            create_url_kwargs["hl"] = ui_language
            create_url_kwargs["ui_locales"] = ui_language

        authorization_url, state = session.create_authorization_url(
            AUTHORIZATION_ENDPOINT,
            **create_url_kwargs,
        )
        current_app.logger.info("Google OAuth begin state=%s", state)
        state_payload: Dict[str, Any] = {
            "redirect_uri": redirect_uri,
            "login_context": login_context,
        }
        # Persist the interface language so we can use it
        # when creating or updating the user record.
        if ui_language_from_frontend:
            state_payload["language"] = ui_language_from_frontend
        elif ui_language:
            state_payload["language"] = ui_language

        redis.set(
            _state_storage_key(state),
            json.dumps(state_payload),
            ex=STATE_TTL,
        )
        return {"authorization_url": authorization_url, "state": state}

    def handle_oauth_callback(self, app, request: OAuthCallbackRequest) -> AuthResult:
        if not request.code:
            raise RuntimeError("Missing authorization code")
        if not request.state:
            raise RuntimeError("Missing state")

        storage_key = _state_storage_key(request.state)
        current_app.logger.info("Google OAuth callback state=%s", request.state)
        stored_state_value = redis.get(storage_key)
        if isinstance(stored_state_value, bytes):
            stored_state_value = stored_state_value.decode("utf-8")
        if not stored_state_value:
            current_app.logger.warning(
                "Google OAuth state missing for key %s", storage_key
            )
            raise RuntimeError("Invalid or expired OAuth state")
        redis.delete(storage_key)

        redirect_uri = None
        login_context = None
        language: Optional[str] = None
        try:
            if stored_state_value:
                state_payload = json.loads(stored_state_value)
                if isinstance(state_payload, dict):
                    redirect_uri = state_payload.get("redirect_uri")
                    login_context = state_payload.get("login_context")
                    language = state_payload.get("language")
        except Exception:  # noqa: BLE001 - defensive fallback
            current_app.logger.warning(
                "Failed to parse Google OAuth state payload for key %s", storage_key
            )

        redirect_uri = _resolve_redirect_uri(app, redirect_uri)
        session = self._create_session(app, redirect_uri)

        token = session.fetch_token(
            TOKEN_ENDPOINT,
            code=request.code,
        )

        resp = session.get(USERINFO_ENDPOINT)
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
        credential = find_credential(provider_name=self.provider_name, identifier=email)

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

            if aggregate:
                entity = get_user_entity_by_bid(
                    aggregate.user_bid, include_deleted=True
                )
                if entity:
                    updates: Dict[str, Any] = {
                        "identify": email,
                        "state": USER_STATE_REGISTERED,
                    }
                    display_name = profile.get("name")
                    if display_name:
                        updates["nickname"] = display_name
                    picture = profile.get("picture")
                    if picture and not aggregate.avatar:
                        updates["avatar"] = picture
                    if language:
                        updates["language"] = language
                    update_user_entity_fields(entity, **updates)
            else:
                defaults = {
                    "user_bid": secrets.token_hex(16),
                    "nickname": profile.get("name") or "",
                    "avatar": profile.get("picture"),
                    "language": language,
                    "state": USER_STATE_REGISTERED,
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

            # Optionally grant creator and demo-course permissions for admin logins
            ensure_admin_creator_and_demo_permissions(
                app, aggregate.user_bid, aggregate.language, login_context
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
                "token_response": token,
                "profile": profile,
                "snapshot": snapshot.to_dict(),
            },
        )


if not has_provider(GoogleAuthProvider.provider_name):
    register_provider(GoogleAuthProvider)
