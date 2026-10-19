"""Register operator voice-clone routes.

Service calls resolve through the route module so its patch targets stay effective.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import request
from flaskr.common.http import make_common_response
from flaskr.service.common.models import raise_param_error
from flaskr.service.shifu.admin_operations.route_helpers import (
    _normalize_query_text,
    _parse_choice_query_param,
    _parse_datetime_filter,
    _parse_positive_query_int,
    _require_operator,
    _validate_datetime_range,
)
from flaskr.service.shifu.admin_operations.voice_clones import (
    OPERATOR_VOICE_CLONE_BILLING_STATUSES,
    OPERATOR_VOICE_CLONE_LIST_MAX_PAGE_SIZE,
    OPERATOR_VOICE_CLONE_PROVIDERS,
    OPERATOR_VOICE_CLONE_STATUSES,
)

if TYPE_CHECKING:
    from flask import Flask


def register_admin_operations_voice_clone_list_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register the operator voice-clone list route."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(path_prefix + "/admin/operations/voice-clones", methods=["GET"])
    def admin_operations_voice_clones() -> str:
        """Operator MiniMax cloned voice list.

        ---
        tags:
            - TTS
        parameters:
            - name: page_index
              type: integer
              required: false
            - name: page_size
              type: integer
              required: false
            - name: status
              type: string
              required: false
            - name: failure_reason
              type: string
              required: false
            - name: billing_status
              type: string
              required: false
            - name: start_time
              type: string
              required: false
            - name: end_time
              type: string
              required: false
            - name: user_keyword
              type: string
              required: false
            - name: course_keyword
              type: string
              required: false
            - name: voice_keyword
              type: string
              required: false
            - name: provider
              type: string
              required: false
              description: minimax or volcengine
            - name: minimax_status_code
              type: integer
              required: false
        responses:
            200:
                description: List operator-visible cloned voice jobs
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        page_size = min(page_size, OPERATOR_VOICE_CLONE_LIST_MAX_PAGE_SIZE)
        raw_minimax_status_code = _normalize_query_text(
            request.args.get("minimax_status_code")
        )
        minimax_status_code = (
            _parse_positive_query_int(
                raw_minimax_status_code,
                field_name="minimax_status_code",
                default=0,
                minimum=0,
            )
            if raw_minimax_status_code
            else None
        )

        filters = {
            "status": _parse_choice_query_param(
                request.args.get("status"),
                field_name="status",
                allowed_values=OPERATOR_VOICE_CLONE_STATUSES,
            ),
            "failure_reason": _normalize_query_text(request.args.get("failure_reason")),
            "billing_status": _parse_choice_query_param(
                request.args.get("billing_status"),
                field_name="billing_status",
                allowed_values=OPERATOR_VOICE_CLONE_BILLING_STATUSES,
            ),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
            "user_keyword": _normalize_query_text(request.args.get("user_keyword")),
            "course_keyword": _normalize_query_text(request.args.get("course_keyword")),
            "voice_keyword": _normalize_query_text(request.args.get("voice_keyword")),
            "provider": _parse_choice_query_param(
                request.args.get("provider"),
                field_name="provider",
                allowed_values=OPERATOR_VOICE_CLONE_PROVIDERS,
            ),
            "minimax_status_code": minimax_status_code,
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            ops_route.list_operator_voice_clones(
                app,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )


def register_admin_operations_voice_clone_registration_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register the operator voice-clone registration route."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(path_prefix + "/admin/operations/voice-clones", methods=["POST"])
    def admin_operations_register_voice_clone() -> str:
        """Register a voice cloned on a provider console and assign it to a teacher.

        ---
        tags:
            - TTS
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    owner_user_bid:
                        type: string
                    display_name:
                        type: string
                    voice_id:
                        type: string
                    provider:
                        type: string
                        description: minimax (default) or volcengine
        responses:
            200:
                description: The registered cloned voice record
        """
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("payload must be a JSON object")
        return make_common_response(
            ops_route.register_operator_voice_clone(
                app,
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                owner_user_bid=str(payload.get("owner_user_bid") or ""),
                display_name=str(payload.get("display_name") or ""),
                voice_id=str(payload.get("voice_id") or ""),
                provider=str(payload.get("provider") or ""),
            )
        )
