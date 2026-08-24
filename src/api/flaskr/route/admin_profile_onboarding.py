"""Register operator profile-onboarding configuration and preview routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Flask, Response, request

from flaskr.i18n import get_current_language, get_i18n_list
from flaskr.route.common import make_common_response
from flaskr.service.common.models import raise_param_error
from flaskr.service.common.profile_research_request_validation import (
    normalize_profile_research_session_id,
    parse_profile_research_run_request,
)
from flaskr.service.shifu.admin_operations.profile_onboarding import (
    create_operator_profile_onboarding_preview_session,
    get_operator_profile_onboarding_config,
    stream_operator_profile_onboarding_preview_session,
    update_operator_profile_onboarding_config,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _profile_onboarding_json_object(parameter_name: str) -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise_param_error(parameter_name)
    return payload


def _reject_profile_onboarding_unknown_fields(
    payload: dict, *, allowed_fields: set[str], parameter_name: str
) -> None:
    if set(payload) - allowed_fields:
        raise_param_error(parameter_name)


def _normalize_profile_onboarding_language(_app: Flask, raw_language: str) -> str:
    normalized = raw_language.strip().replace("_", "-")
    parts = [part for part in normalized.split("-") if part]
    if not parts:
        raise_param_error("language")
    normalized_parts = [parts[0].lower()]
    for part in parts[1:]:
        if len(part) == 2 and part.isalpha():
            normalized_parts.append(part.upper())
        elif len(part) == 4 and part.isalpha():
            normalized_parts.append(part.title())
        else:
            normalized_parts.append(part)
    normalized = "-".join(normalized_parts)
    supported_languages = get_i18n_list()
    for supported_language in supported_languages:
        if supported_language.lower() == normalized.lower():
            return supported_language
    primary_language = normalized.split("-", 1)[0].lower()
    for supported_language in supported_languages:
        if supported_language.split("-", 1)[0].lower() == primary_language:
            return supported_language
    raise_param_error("language")
    return ""  # pragma: no cover


def register_operator_profile_onboarding_routes(
    app: Flask,
    path_prefix: str,
    *,
    require_operator: Callable[[], None],
) -> None:
    """Register operator profile-onboarding routes."""
    _require_operator = require_operator

    @app.route(
        path_prefix + "/admin/operations/profile-onboarding",
        methods=["GET"],
    )
    def admin_operation_profile_onboarding_config() -> str:
        """Get operator profile onboarding config."""
        _require_operator()
        return make_common_response(get_operator_profile_onboarding_config(app))

    @app.route(
        path_prefix + "/admin/operations/profile-onboarding",
        methods=["POST"],
    )
    def admin_operation_update_profile_onboarding_config() -> str:
        """Update operator profile onboarding config."""
        _require_operator()
        payload = _profile_onboarding_json_object("profile_onboarding_config")
        _reject_profile_onboarding_unknown_fields(
            payload,
            allowed_fields={"enabled", "markdownflow"},
            parameter_name="profile_onboarding_config",
        )
        return make_common_response(
            update_operator_profile_onboarding_config(
                app,
                payload=payload,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
            )
        )

    @app.route(
        path_prefix + "/admin/operations/profile-onboarding/preview",
        methods=["POST"],
    )
    def admin_operation_create_profile_onboarding_preview() -> str:
        """Create an isolated preview from the operator's unsaved editor draft."""
        _require_operator()
        payload = _profile_onboarding_json_object("profile_onboarding_preview")
        _reject_profile_onboarding_unknown_fields(
            payload,
            allowed_fields={"markdownflow", "language"},
            parameter_name="profile_onboarding_preview",
        )
        markdownflow = payload.get("markdownflow")
        language = payload.get("language")
        if not isinstance(markdownflow, str) or not markdownflow.strip():
            raise_param_error("markdownflow")
        if language is not None and (
            not isinstance(language, str) or not language.strip()
        ):
            raise_param_error("language")
        config = get_operator_profile_onboarding_config(app)
        return make_common_response(
            create_operator_profile_onboarding_preview_session(
                app,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                markdownflow=markdownflow.strip(),
                config_revision=int(
                    config.get("config_revision") or config.get("version") or 0
                ),
                output_language=(
                    _normalize_profile_onboarding_language(app, language)
                    if language is not None
                    else get_current_language()
                ),
            )
        )

    @app.route(
        path_prefix + "/admin/operations/profile-onboarding/preview/<session_id>/run",
        methods=["POST"],
    )
    def admin_operation_run_profile_onboarding_preview(session_id: str) -> Response:
        """Stream one owner- and preview-purpose-scoped cursor step."""
        _require_operator()
        normalized_session_id = normalize_profile_research_session_id(session_id)
        payload = _profile_onboarding_json_object("profile_onboarding_preview")
        run_request = parse_profile_research_run_request(
            payload,
            parameter_name="profile_onboarding_preview",
        )
        operator_user_bid = str(getattr(request.user, "user_id", "") or "")
        from flaskr.service.profile_research.api import (
            build_profile_research_sse_response,
        )

        return build_profile_research_sse_response(
            app,
            event_iter_factory=lambda: (
                stream_operator_profile_onboarding_preview_session(
                    app,
                    operator_user_bid=operator_user_bid,
                    session_id=normalized_session_id,
                    user_input=run_request.user_input,
                    expected_block_index=run_request.expected_block_index,
                    request_id=run_request.request_id,
                )
            ),
            log_context="operator profile onboarding preview",
        )
