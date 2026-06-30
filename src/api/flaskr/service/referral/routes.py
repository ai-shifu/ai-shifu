"""Creator and anonymous referral routes."""

from __future__ import annotations

from flask import Flask, request

from flaskr.route.common import bypass_token_validation, make_common_response
from flaskr.service.common.models import raise_param_error

from .service import (
    InviteEventInput,
    build_invite_preview,
    build_invite_profile,
    record_invite_event,
)


def register_referral_routes(app: Flask, path_prefix: str = "/api/referral") -> None:
    """Register referral routes."""

    @app.route(path_prefix + "/invite-profile", methods=["GET"])
    def referral_invite_profile_api():
        user = getattr(request, "user", None)
        user_bid = str(getattr(user, "user_id", "") or "").strip()
        if not user_bid:
            raise_param_error("user")
        profile = build_invite_profile(app, inviter_user_bid=user_bid)
        return make_common_response(profile.to_dict())

    @app.route(path_prefix + "/invite-preview", methods=["GET"])
    @bypass_token_validation
    def referral_invite_preview_api():
        preview = build_invite_preview(
            app,
            invite_code=str(request.args.get("invite_code") or "").strip(),
        )
        return make_common_response(preview.to_dict())

    @app.route(path_prefix + "/invite-event", methods=["POST"])
    @bypass_token_validation
    def referral_invite_event_api():
        payload = request.get_json(silent=True)
        payload = payload if isinstance(payload, dict) else {}
        result = record_invite_event(
            app,
            InviteEventInput(
                event_type=str(payload.get("event_type") or "").strip(),
                invite_code=str(payload.get("invite_code") or "").strip(),
                landing_path=str(payload.get("landing_path") or "").strip(),
                session_id=str(payload.get("session_id") or "").strip(),
                entry_source=str(payload.get("entry_source") or "").strip(),
                client_ip=_client_ip(),
                user_agent=str(request.headers.get("User-Agent") or ""),
                metadata={
                    "frontend_session_id": str(
                        payload.get("frontend_session_id") or ""
                    ).strip()
                },
            ),
        )
        return make_common_response(
            {
                "success": result.success,
                "session_id": result.session_id,
                "recognized": result.recognized,
            }
        )


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return str(request.remote_addr or "").strip()
