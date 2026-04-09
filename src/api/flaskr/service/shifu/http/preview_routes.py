from __future__ import annotations

from contextlib import nullcontext

from flask import Flask, request

from flaskr.i18n import get_current_language, set_language
from flaskr.route.common import bypass_token_validation, make_common_response
from flaskr.service.billing.admission import admit_creator_usage
from flaskr.service.billing.admission import reserve_creator_runtime_slot
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.service.user.common import validate_user
from flaskr.service.user.utils import get_user_language

from ..ask_preview import preview_ask_response
from ..ask_provider_registry import get_ask_provider_metadata
from ..tts_preview import build_tts_preview_response


def register_shifu_preview_routes(app: Flask, path_prefix: str) -> None:
    def _admit_creator_debug_usage() -> dict[str, object] | None:
        request_user = getattr(request, "user", None)
        creator_bid = str(getattr(request_user, "user_id", "") or "").strip()
        if not creator_bid or not getattr(request_user, "is_creator", False):
            return None
        return admit_creator_usage(
            app,
            creator_bid=creator_bid,
            usage_scene=BILL_USAGE_SCENE_DEBUG,
        )

    @app.route(path_prefix + "/ask/config", methods=["GET"])
    @bypass_token_validation
    def ask_config_api():
        original_language = get_current_language()
        token = request.cookies.get("token", None)
        if not token:
            token = request.args.get("token", None)
        if not token:
            token = request.headers.get("Token", None)

        if token:
            try:
                user = validate_user(app, str(token))
                set_language(get_user_language(user))
            except Exception:
                pass

        try:
            return make_common_response(get_ask_provider_metadata())
        finally:
            set_language(original_language)

    @app.route(path_prefix + "/ask/preview", methods=["POST"])
    @bypass_token_validation
    def ask_preview_api():
        admission_payload = _admit_creator_debug_usage()
        runtime_lease = None
        if admission_payload is not None:
            runtime_lease = reserve_creator_runtime_slot(
                app,
                admission_payload=admission_payload,
            )
        request_user = getattr(request, "user", None)
        request_user_id = str(
            getattr(getattr(request, "user", None), "user_id", "")
        ).strip()

        with runtime_lease or nullcontext():
            return make_common_response(
                preview_ask_response(
                    app,
                    request.get_json() or {},
                    request_user_id=request_user_id,
                    request_user_is_creator=bool(
                        getattr(request_user, "is_creator", False)
                    ),
                )
            )

    @app.route(path_prefix + "/tts/config", methods=["GET"])
    @bypass_token_validation
    def tts_config_api():
        from flaskr.api.tts import get_all_provider_configs

        return make_common_response(get_all_provider_configs())

    @app.route(path_prefix + "/tts/preview", methods=["POST"])
    @bypass_token_validation
    def tts_preview_api():
        admission_payload = _admit_creator_debug_usage()
        runtime_lease = None
        if admission_payload is not None:
            runtime_lease = reserve_creator_runtime_slot(
                app,
                admission_payload=admission_payload,
            )
        request_user = getattr(request, "user", None)
        return build_tts_preview_response(
            request.get_json() or {},
            request_user_id=str(getattr(request_user, "user_id", "") or "").strip(),
            request_user_is_creator=bool(getattr(request_user, "is_creator", False)),
            runtime_lease=runtime_lease,
        )
