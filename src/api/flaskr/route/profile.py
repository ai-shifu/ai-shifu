"""Register learner profile and profile-onboarding HTTP routes."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from flask import Flask, Response, request

from flaskr.route.common import make_common_response
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.profile_onboarding import get_profile_onboarding_config
from flaskr.service.common.profile_research_request_validation import (
    normalize_profile_research_session_id,
    parse_profile_research_run_request,
)
from flaskr.service.profile.learner_profile import (
    clear_learner_profile,
    get_learner_profile,
    replace_learner_profile,
)
from flaskr.service.profile.learner_profile_optimizer import optimize_learner_profile
from flaskr.service.profile.learner_profile_optimizer_admission import (
    learner_profile_optimization_admission,
)
from flaskr.service.profile.onboarding import (
    complete_profile_onboarding,
    get_profile_onboarding_status,
    skip_profile_onboarding,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from flaskr.service.user.models import UserInfo


def _request_json_object(parameter_name: str) -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise_param_error(parameter_name)
    return payload


def _reject_unknown_fields(
    payload: dict, *, allowed_fields: set[str], parameter_name: str
) -> None:
    if set(payload) - allowed_fields:
        raise_param_error(parameter_name)


def _optional_nonempty_string(payload: dict, key: str) -> str | None:
    if key not in payload:
        return None
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise_param_error(key)
    return value.strip()


def _optional_profile_research_session_id(payload: dict) -> str | None:
    value = _optional_nonempty_string(payload, "session_id")
    if value is None:
        return None
    return normalize_profile_research_session_id(value)


def _delete_profile_onboarding_session(
    app: Flask, *, user_bid: str, session_id: str | None
) -> None:
    """Best-effort cleanup must not roll back a durable completion state."""
    from flaskr.service.profile_research.api import (
        PROFILE_ONBOARDING_PURPOSE,
        delete_active_profile_research_session,
        delete_profile_research_session,
    )

    with contextlib.suppress(Exception):
        if session_id:
            delete_profile_research_session(
                app,
                user_bid=user_bid,
                session_id=session_id,
                expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            )
        else:
            delete_active_profile_research_session(
                app,
                user_bid=user_bid,
                purpose=PROFILE_ONBOARDING_PURPOSE,
            )


def register_profile_routes(
    app: Flask,
    path_prefix: str,
    *,
    resolve_onboarding_language: Callable[[UserInfo, str | None], str],
) -> None:
    """Register canonical learner-profile and onboarding routes."""
    _resolve_profile_onboarding_runtime_language = resolve_onboarding_language

    @app.route(path_prefix + "/profile-onboarding", methods=["GET"])
    def profile_onboarding_status_api() -> str:
        """Get platform-level profile onboarding state for current user.

        ---
        tags:
            - user
        responses:
            200:
                description: onboarding config and current user state
        """
        return make_common_response(
            get_profile_onboarding_status(app, user_id=request.user.user_id)
        )

    @app.route(path_prefix + "/profile-onboarding/session", methods=["POST"])
    def create_profile_onboarding_session_api() -> str:
        """Create a transient guided-profile session from the live config."""
        payload = _request_json_object("profile_onboarding_session")
        _reject_unknown_fields(
            payload,
            allowed_fields={"language", "intent"},
            parameter_name="profile_onboarding_session",
        )
        language = _optional_nonempty_string(payload, "language")
        intent = _optional_nonempty_string(payload, "intent") or "onboarding"
        if intent not in {"onboarding", "settings"}:
            raise_param_error("intent")
        config = get_profile_onboarding_config()
        document = str(config.get("markdownflow") or "").strip()
        if not bool(config.get("enabled")) or not document:
            raise_param_error("profile_onboarding")
        status = get_profile_onboarding_status(app, user_id=request.user.user_id)
        if not status["guided_available"]:
            raise_param_error("profile_onboarding")
        if intent == "onboarding" and not status["should_show"]:
            raise_param_error("intent")
        if intent == "settings" and not (
            status["handled"] or status["has_learner_profile"]
        ):
            raise_param_error("intent")
        from flaskr.service.profile_research.api import (
            PROFILE_ONBOARDING_PURPOSE,
            ProfileResearchSessionBusy,
            start_profile_research_session,
        )

        try:
            session = start_profile_research_session(
                app,
                user_bid=request.user.user_id,
                document=document,
                purpose=PROFILE_ONBOARDING_PURPOSE,
                config_revision=int(config.get("config_revision") or 0),
                output_language=_resolve_profile_onboarding_runtime_language(
                    request.user,
                    language,
                ),
            )
        except ProfileResearchSessionBusy:
            raise_error("server.profile.profileOnboardingBusy")
        if intent == "onboarding":
            latest_status = get_profile_onboarding_status(
                app,
                user_id=request.user.user_id,
            )
            if not latest_status["should_show"]:
                _delete_profile_onboarding_session(
                    app,
                    user_bid=request.user.user_id,
                    session_id=str(session.get("session_id") or "") or None,
                )
                raise_param_error("intent")
        return make_common_response(session)

    @app.route(
        path_prefix + "/profile-onboarding/session/<session_id>/run",
        methods=["POST"],
    )
    def run_profile_onboarding_session_api(session_id: str) -> Response:
        normalized_session_id = normalize_profile_research_session_id(session_id)
        payload = _request_json_object("profile_onboarding_session")
        run_request = parse_profile_research_run_request(
            payload,
            parameter_name="profile_onboarding_session",
        )
        from flaskr.service.profile_research.api import (
            PROFILE_ONBOARDING_PURPOSE,
            build_profile_research_sse_response,
            stream_profile_research_session,
        )

        return build_profile_research_sse_response(
            app,
            event_iter_factory=lambda: stream_profile_research_session(
                app,
                user_bid=request.user.user_id,
                session_id=normalized_session_id,
                user_input=run_request.user_input,
                expected_purpose=PROFILE_ONBOARDING_PURPOSE,
                expected_block_index=run_request.expected_block_index,
                request_id=run_request.request_id,
            ),
            log_context="learner profile onboarding",
        )

    @app.route(path_prefix + "/profile-onboarding/complete", methods=["POST"])
    def complete_profile_onboarding_api() -> str:
        """Complete or skip platform-level profile onboarding.

        ---
        tags:
            - user
        responses:
            200:
                description: onboarding completion result
        """
        payload = _request_json_object("profile_onboarding")
        allowed_fields = {
            "learner_profile",
            "trigger_source",
            "session_id",
            "nickname",
        }
        keys = set(payload)
        if not {"learner_profile", "trigger_source"}.issubset(
            keys
        ) or not keys.issubset(allowed_fields):
            raise_param_error("profile_onboarding")
        session_id = _optional_profile_research_session_id(payload)
        nickname_kwargs = {}
        if "nickname" in payload:
            if not isinstance(payload["nickname"], str):
                raise_param_error("nickname")
            nickname_kwargs["nickname"] = payload["nickname"]
        result = complete_profile_onboarding(
            app,
            user_id=request.user.user_id,
            learner_profile=payload["learner_profile"],
            trigger_source=payload["trigger_source"],
            **nickname_kwargs,
        )
        _delete_profile_onboarding_session(
            app, user_bid=request.user.user_id, session_id=session_id
        )
        return make_common_response(result)

    @app.route(path_prefix + "/profile-onboarding/skip", methods=["POST"])
    def skip_profile_onboarding_api() -> str:
        payload = _request_json_object("profile_onboarding")
        _reject_unknown_fields(
            payload,
            allowed_fields={"session_id"},
            parameter_name="profile_onboarding",
        )
        session_id = _optional_profile_research_session_id(payload)
        result = skip_profile_onboarding(user_id=request.user.user_id)
        _delete_profile_onboarding_session(
            app, user_bid=request.user.user_id, session_id=session_id
        )
        return make_common_response(result)

    @app.route(path_prefix + "/learner-profile", methods=["GET"])
    def learner_profile_api() -> str:
        """Return the current user's canonical learning profile."""
        return make_common_response(get_learner_profile(user_id=request.user.user_id))

    @app.route(path_prefix + "/learner-profile", methods=["PUT"])
    def update_learner_profile_api() -> str:
        """Replace the current user's canonical learning profile."""
        payload = _request_json_object("learner_profile")
        _reject_unknown_fields(
            payload,
            allowed_fields={"learner_profile", "nickname"},
            parameter_name="learner_profile",
        )
        learner_profile = payload.get("learner_profile")
        if not isinstance(learner_profile, str):
            raise_param_error("learner_profile")
        nickname = payload.get("nickname")
        if "nickname" in payload and not isinstance(nickname, str):
            raise_param_error("nickname")
        return make_common_response(
            replace_learner_profile(
                app,
                user_id=request.user.user_id,
                learner_profile=learner_profile,
                nickname=nickname,
            )
        )

    @app.route(path_prefix + "/learner-profile", methods=["DELETE"])
    def clear_learner_profile_api() -> str:
        """Clear the profile while keeping profile-v2 handled."""
        return make_common_response(clear_learner_profile(user_id=request.user.user_id))

    @app.route(path_prefix + "/learner-profile/optimize", methods=["POST"])
    def optimize_learner_profile_api() -> str:
        """Return an LLM-optimized draft without saving profile state."""
        payload = _request_json_object("learner_profile")
        _reject_unknown_fields(
            payload,
            allowed_fields={"learner_profile"},
            parameter_name="learner_profile",
        )
        learner_profile = payload.get("learner_profile")
        if not isinstance(learner_profile, str):
            raise_param_error("learner_profile")
        with learner_profile_optimization_admission(
            app,
            user_id=request.user.user_id,
        ):
            result = optimize_learner_profile(
                app,
                user_id=request.user.user_id,
                learner_profile=learner_profile,
                output_language=getattr(request.user, "language", None),
            )
        return make_common_response(result)
