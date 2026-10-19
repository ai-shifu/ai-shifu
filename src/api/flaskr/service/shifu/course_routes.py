"""Register shifu course list, detail, publish, and export routes.

Route bodies resolve service functions through ``flaskr.service.shifu.route``
so patching a name on that module keeps affecting the registered views.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from flask import Response, after_this_request, current_app, request, send_file
from flaskr.common.http import make_common_response
from flaskr.common.shifu_context import with_shifu_context
from flaskr.service.common.models import raise_param_error
from flaskr.service.shifu.shifu_draft_funcs import SUPPORTED_ASK_ENABLED_STATUSES

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask


def register_shifu_course_list_routes(app: Flask, path_prefix: str) -> None:
    """Register the course list route."""
    from flaskr.service.shifu import route as shifu_route
    from flaskr.service.shifu.route import ShifuPermission, ShifuTokenValidation

    @app.route(path_prefix + "/shifus", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW, is_creator=True)
    def get_shifu_list_api() -> str:
        """Get shifu list.

        ---
        tags:
            - shifu
        parameters:
            - name: page_index
              type: integer
              required: false
              description: Page index, defaults to 1 when omitted
            - name: page_size
              type: integer
              required: false
              description: Page size, defaults to 10 when omitted
            - name: is_favorite
              type: boolean
              required: true
        responses:
            200:
                description: get shifu list success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: message
                                data:
                                    type: array
                                    items:
                                        $ref: "#/components/schemas/PageNationDTO"
        """
        user_id = request.user.user_id
        page_index = request.args.get("page_index", 1)
        page_size = request.args.get("page_size", 10)
        is_favorite = request.args.get("is_favorite", "False")
        is_favorite = is_favorite.lower() == "true"
        archived_param = request.args.get("archived")
        archived = False
        if archived_param is not None:
            archived = archived_param.lower() == "true"
        try:
            page_index = int(page_index)
            page_size = int(page_size)
        except ValueError:
            raise_param_error("page_index or page_size is not a number")

        if page_index < 0 or page_size < 1:
            raise_param_error("page_index or page_size is less than 0")
        app.logger.info(
            "get shifu list, user_id: %s, page_index: %s, page_size: %s, is_favorite: %s",
            user_id,
            page_index,
            page_size,
            is_favorite,
        )
        return make_common_response(
            shifu_route.get_shifu_draft_list(
                app, user_id, page_index, page_size, is_favorite, archived
            )
        )


def register_shifu_course_archive_routes(app: Flask, path_prefix: str) -> None:
    """Register course archive and unarchive routes."""
    from flaskr.service.shifu import route as shifu_route
    from flaskr.service.shifu.route import ShifuPermission, ShifuTokenValidation

    @app.route(path_prefix + "/shifus/<shifu_id>/archive", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def archive_shifu_api(shifu_id: str) -> str:
        user_id = request.user.user_id
        shifu_route.archive_shifu(app, user_id, shifu_id)
        return make_common_response({"archived": True})

    @app.route(path_prefix + "/shifus/<shifu_id>/unarchive", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def unarchive_shifu_api(shifu_id: str) -> str:
        user_id = request.user.user_id
        shifu_route.unarchive_shifu(app, user_id, shifu_id)
        return make_common_response({"archived": False})


def register_shifu_course_detail_routes(app: Flask, path_prefix: str) -> None:
    """Register course create, detail, favorite, and publish routes."""
    from flaskr.service.shifu import route as shifu_route
    from flaskr.service.shifu.route import ShifuPermission, ShifuTokenValidation

    @app.route(path_prefix + "/shifus", methods=["PUT"])
    @ShifuTokenValidation(ShifuPermission.VIEW, is_creator=True)
    def create_shifu_api() -> str:
        """Create shifu.

        ---
        tags:
            - shifu
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    name:
                        type: string
                        description: shifu name
                    description:
                        type: string
                        description: shifu description
                    avatar:
                        type: string
                        description: shifu avatar
        responses:
            200:
                description: create shifu success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: message
                                data:
                                    type: object
                                    $ref: "#/components/schemas/ShifuDto"
        """
        with shifu_route._external_client_course_event(app, "creation"):
            user_id = request.user.user_id
            shifu_name = request.get_json().get("name")
            if not shifu_name:
                raise_param_error("name is required")
            shifu_description = request.get_json().get("description")
            shifu_avatar = request.get_json().get("avatar", "")
            result = shifu_route.create_shifu_draft(
                app,
                user_id,
                shifu_name,
                shifu_description,
                shifu_avatar,
                [],
            )
        return make_common_response(result)

    @app.route(path_prefix + "/shifus/<shifu_bid>/detail", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    @with_shifu_context()
    def get_shifu_detail_api(shifu_bid: str) -> str:
        """Get shifu detail.

        ---
        tags:
            - shifu
        parameters:
            - name: shifu_bid
              type: string
              required: true
        responses:
            200:
                description: get shifu detail success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: message
                                data:
                                    type: object
                                    $ref: "#/components/schemas/ShifuDetailDto"
        """
        user_id = request.user.user_id
        base_url = shifu_route._resolve_publish_base_url(app)
        app.logger.info(
            "get shifu detail, user_id: %s, shifu_bid: %s", user_id, shifu_bid
        )
        return make_common_response(
            shifu_route.get_shifu_draft_info(app, user_id, shifu_bid, base_url)
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/detail", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    @with_shifu_context()
    def save_shifu_detail_api(shifu_bid: str) -> str:
        """Save shifu detail.

        ---
        tags:
            - shifu
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - name: body
              in: body
              type: object
              required: true
              schema:
                type: object
                properties:
                    name:
                        type: string
                        description: shifu name
                    description:
                        type: string
                        description: shifu description
                    avatar:
                        type: string
                        description: shifu avatar
                    keywords:
                        type: array
                        items:
                            type: string
                        description: shifu keywords
                    model:
                        type: string
                        description: shifu model
                    price:
                        type: number
                        description: shifu price
                    ask_enabled_status:
                        type: integer
                        description: Ask status (5101=default, 5102=disabled, 5103=enabled)
                    ask_model:
                        type: string
                        description: Ask model name
                    ask_system_prompt:
                        type: string
                        description: Ask model system prompt
                    ask_provider_config:
                        type: object
                        description: Ask provider config ({provider, mode, config})
                    tts_enabled:
                        type: boolean
                        description: TTS enabled
                    tts_provider:
                        type: string
                        description: TTS provider (minimax, volcengine, volcengine_http, baidu, aliyun)
                    tts_model:
                        type: string
                        description: TTS model/resource ID
                    tts_voice_id:
                        type: string
                        description: TTS voice ID
                    tts_speed:
                        type: number
                        description: TTS speech speed (provider-specific range)
                    tts_pitch:
                        type: integer
                        description: TTS pitch adjustment (provider-specific range)
                    tts_emotion:
                        type: string
                        description: TTS emotion setting
                    default_listen_mode_enabled:
                        type: boolean
                        description: Default learner mode to listen when TTS is enabled
        responses:
            200:
                description: save shifu detail success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: message
                                data:
                                    type: object
                                    $ref: "#/components/schemas/ShifuDetailDto"
        """
        user_id = request.user.user_id
        json_data = request.get_json() or {}
        shifu_name = json_data.get("name")
        shifu_description = json_data.get("description")
        shifu_avatar = json_data.get("avatar")
        shifu_keywords = json_data.get("keywords")
        shifu_model = (json_data.get("model") or "") if "model" in json_data else None
        shifu_price = json_data.get("price")
        shifu_system_prompt = json_data.get("system_prompt", None)
        ask_settings = _parse_save_shifu_ask_settings(json_data)
        tts_settings = _parse_save_shifu_tts_settings(json_data)
        # Language Output Configuration
        use_learner_language = json_data.get("use_learner_language")
        if isinstance(use_learner_language, str):
            use_learner_language = use_learner_language.lower() == "true"
        base_url = shifu_route._resolve_publish_base_url(app)
        # Keep stored temperatures and defaults internal to course generation.
        return make_common_response(
            shifu_route.save_shifu_draft_info(
                app,
                user_id,
                shifu_bid,
                shifu_name,
                shifu_description,
                shifu_avatar,
                shifu_keywords,
                shifu_model,
                None,
                shifu_price,
                shifu_system_prompt,
                base_url,
                tts_enabled=tts_settings["tts_enabled"],
                tts_provider=tts_settings["tts_provider"],
                tts_model=tts_settings["tts_model"],
                tts_voice_id=tts_settings["tts_voice_id"],
                tts_speed=tts_settings["tts_speed"],
                tts_pitch=tts_settings["tts_pitch"],
                tts_emotion=tts_settings["tts_emotion"],
                default_listen_mode_enabled=tts_settings["default_listen_mode_enabled"],
                use_learner_language=use_learner_language,
                ask_enabled_status=ask_settings["ask_enabled_status"],
                ask_model=ask_settings["ask_model"],
                ask_temperature=None,
                ask_system_prompt=ask_settings["ask_system_prompt"],
                ask_provider_config=ask_settings["ask_provider_config"],
            )
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/favorite", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.VIEW, is_creator=True)
    @with_shifu_context()
    def mark_favorite_shifu_api(shifu_bid: str) -> str:
        """Mark favorite shifu.

        ---
        tags:
            - shifu
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    is_favorite:
                        type: boolean
                        description: is favorite
        responses:
            200:
                description: mark favorite shifu success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: message
                                data:
                                    type: boolean
                                    description: is favorite
        """
        user_id = request.user.user_id
        is_favorite = request.get_json().get("is_favorite")
        if isinstance(is_favorite, str):
            is_favorite = is_favorite.lower() == "true"
        elif not isinstance(is_favorite, bool):
            raise_param_error("is_favorite is not a boolean")
        return make_common_response(
            shifu_route.mark_or_unmark_favorite_shifu(
                app, user_id, shifu_bid, is_favorite
            )
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/publish", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.PUBLISH)
    @with_shifu_context()
    def publish_shifu_api(shifu_bid: str) -> str:
        """Publish shifu.

        ---
        tags:
            - shifu
        parameters:
            - name: shifu_bid
              type: string
              required: true
        responses:
            200:
                description: publish shifu success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: message
                                data:
                                    type: string
                                    description: publish url
        """
        with shifu_route._external_client_course_event(app, "publish"):
            user_id = request.user.user_id
            base_url = shifu_route._resolve_publish_base_url(app)
            result = shifu_route.publish_shifu_draft(app, user_id, shifu_bid, base_url)
        return make_common_response(result)


def register_shifu_course_preview_routes(
    app: Flask,
    path_prefix: str,
    *,
    _admit_creator_preview_usage_for_shifu: Callable[[str], None],
) -> None:
    """Register the course preview route."""
    from flaskr.service.shifu import route as shifu_route
    from flaskr.service.shifu.route import ShifuPermission, ShifuTokenValidation

    @app.route(path_prefix + "/shifus/<shifu_bid>/preview", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    @with_shifu_context()
    def preview_shifu_api(shifu_bid: str) -> str:
        """Preview shifu.

        ---
        tags:
            - shifu
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    variables:
                        type: object
                        description: variables
        responses:
            200:
                description: preview shifu success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: message
                                data:
                                    type: string
                                    description: preview url
        """
        user_id = request.user.user_id
        variables = request.get_json().get("variables")
        base_url = shifu_route._resolve_publish_base_url(app)
        _admit_creator_preview_usage_for_shifu(shifu_bid)
        return make_common_response(
            shifu_route.preview_shifu_draft(
                app, user_id, shifu_bid, variables, base_url
            )
        )


def register_shifu_course_export_routes(app: Flask, path_prefix: str) -> None:
    """Register the course export route."""
    from flaskr.service.shifu import route as shifu_route
    from flaskr.service.shifu.route import ShifuPermission, ShifuTokenValidation

    @app.route(path_prefix + "/shifus/<shifu_bid>/export", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def export_shifu_api(shifu_bid: str) -> Response:
        """Export shifu.

        ---
        tags:
            - shifu
        parameters:
            - name: shifu_bid
              type: string
              required: true
        responses:
            200:
                description: export shifu success
                content:
                    application/octet-stream:
                        schema:
                            type: string
                            format: binary
        """
        temp_dir = tempfile.mkdtemp(prefix="shifu_export_")
        file_path = Path(temp_dir) / f"{shifu_bid}.json"
        shifu_route.export_shifu(app, shifu_bid, str(file_path))

        @after_this_request
        def cleanup(response: Response) -> Response:
            try:
                file_path.unlink()
                Path(temp_dir).rmdir()
            except OSError:
                current_app.logger.warning(
                    "Failed to cleanup shifu export temp files", exc_info=True
                )
            return response

        return send_file(
            file_path,
            mimetype="application/json",
            as_attachment=True,
            download_name=f"{shifu_bid}.json",
        )


def _parse_save_shifu_ask_settings(json_data: dict[str, Any]) -> dict[str, Any]:
    """Parse and validate the ask fields of a save-detail request."""
    from flaskr.service.shifu import route as shifu_route

    ask_enabled_status = json_data.get("ask_enabled_status")
    if ask_enabled_status is not None:
        try:
            ask_enabled_status = int(ask_enabled_status)
        except (TypeError, ValueError):
            raise_param_error("ask_enabled_status")
        if ask_enabled_status not in SUPPORTED_ASK_ENABLED_STATUSES:
            raise_param_error("ask_enabled_status")
    ask_model = (json_data.get("ask_model") or "") if "ask_model" in json_data else None
    ask_system_prompt = json_data.get("ask_system_prompt")
    if ask_system_prompt is not None:
        ask_system_prompt = str(ask_system_prompt)
    ask_provider_config = shifu_route._parse_ask_provider_config(
        json_data.get("ask_provider_config")
    )
    return {
        "ask_enabled_status": ask_enabled_status,
        "ask_model": ask_model,
        "ask_system_prompt": ask_system_prompt,
        "ask_provider_config": ask_provider_config,
    }


def _parse_save_shifu_tts_settings(json_data: dict[str, Any]) -> dict[str, Any]:
    """Parse the TTS and default listen-mode fields of a save-detail request."""
    # TTS Configuration — read without defaults so an omitted field stays
    # None and is preserved (PATCH semantics), not reset to a default.
    tts_enabled = json_data.get("tts_enabled")
    tts_provider = json_data.get("tts_provider")
    if isinstance(tts_provider, str):
        tts_provider = tts_provider.strip().lower()
    tts_model = json_data.get("tts_model")
    tts_voice_id = json_data.get("tts_voice_id")
    tts_speed = json_data.get("tts_speed")
    tts_pitch = 0 if "tts_pitch" in json_data else None
    tts_emotion = "" if "tts_emotion" in json_data else None
    default_listen_mode_enabled = json_data.get("default_listen_mode_enabled")
    if isinstance(default_listen_mode_enabled, str):
        if default_listen_mode_enabled not in {"true", "false"}:
            raise_param_error("default_listen_mode_enabled")
        default_listen_mode_enabled = default_listen_mode_enabled == "true"
    elif default_listen_mode_enabled is not None and not isinstance(
        default_listen_mode_enabled, bool
    ):
        raise_param_error("default_listen_mode_enabled")
    return {
        "tts_enabled": tts_enabled,
        "tts_provider": tts_provider,
        "tts_model": tts_model,
        "tts_voice_id": tts_voice_id,
        "tts_speed": tts_speed,
        "tts_pitch": tts_pitch,
        "tts_emotion": tts_emotion,
        "default_listen_mode_enabled": default_listen_mode_enabled,
    }
