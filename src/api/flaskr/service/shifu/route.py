"""
Shifu route

This module contains route functions for shifu.
use restful api to manage shifu.
will be auto registered by flaskr.framework.plugin.inject.inject
includes:
    - get shifu list
    - create shifu
    - get shifu detail
    - save shifu detail
    - mark favorite shifu
    - publish shifu
    - preview shifu
    - reorder outline tree
    - create outline
    - modify outline
    - get outline info
    - delete outline
    - get outline tree
    - get block list
    - save blocks
    - add block
    - upload file
    - upload url
    - get video info

Author: yfge
Date: 2025-08-07
"""

import os
import tempfile
import base64
import json
import uuid
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from flask import (
    Flask,
    request,
    current_app,
    send_file,
    after_this_request,
    Response,
    stream_with_context,
)
from .funcs import (
    mark_or_unmark_favorite_shifu,
    upload_file,
    upload_url,
    get_video_info,
    shifu_permission_verification,
)
from flaskr.route.common import make_common_response, bypass_token_validation
from flaskr.framework.plugin.inject import inject
from flaskr.service.common.models import raise_param_error, raise_error
from .consts import UNIT_TYPE_GUEST
from functools import wraps
from enum import Enum
from flaskr.service.shifu.shifu_import_export_funcs import export_shifu
from flaskr.common.shifu_context import with_shifu_context


from flaskr.service.shifu.shifu_draft_funcs import (
    get_shifu_draft_list,
    create_shifu_draft,
    get_shifu_draft_info,
    save_shifu_draft_info,
    archive_shifu,
    unarchive_shifu,
)
from flaskr.service.shifu.shifu_publish_funcs import (
    publish_shifu_draft,
    preview_shifu_draft,
)
from flaskr.service.shifu.shifu_outline_funcs import (
    reorder_outline_tree,
    create_outline,
    modify_unit,
    get_unit_by_id,
    delete_unit,
    get_outline_tree,
)
from flaskr.service.shifu.shifu_mdflow_funcs import (
    get_shifu_mdflow,
    save_shifu_mdflow,
    parse_shifu_mdflow,
)


class ShifuPermission(Enum):
    VIEW = "view"
    EDIT = "edit"
    PUBLISH = "publish"


class ShifuTokenValidation:
    """
    Shifu token validation decorator
    if is_creator is true, only verify creator permission and skip shifu-specific verification
    """

    def __init__(
        self,
        permission: ShifuPermission = ShifuPermission.VIEW,
        is_creator: bool = False,
    ):
        self.permission = permission
        self.is_creator = is_creator

    def __call__(self, f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = request.cookies.get("token", None)
            if not token:
                token = request.args.get("token", None)
            if not token:
                token = request.headers.get("Token", None)
            if not token and request.method.upper() == "POST" and request.is_json:
                token = request.get_json().get("token", None)

            # If is_creator is True, only verify creator permission and skip shifu-specific verification
            if self.is_creator:
                if not request.user.is_creator:
                    raise_error("server.shifu.noPermission")
                return f(*args, **kwargs)

            shifu_bid = request.view_args.get("shifu_bid", None)
            if not shifu_bid:
                shifu_bid = request.view_args.get("shifu_id", None)
            if not shifu_bid:
                shifu_bid = request.args.get("shifu_bid", None)
            if not shifu_bid:
                shifu_bid = request.args.get("shifu_id", None)
            if not shifu_bid and request.method.upper() == "POST" and request.is_json:
                shifu_bid = request.get_json().get("shifu_bid", None)
                if not shifu_bid:
                    shifu_bid = request.get_json().get("shifu_id", None)

            if not token:
                raise_param_error("token is required")
            if not shifu_bid or not str(shifu_bid).strip():
                raise_param_error("shifu_bid is required")

            user_id = request.user.user_id

            app = current_app._get_current_object()
            has_permission = shifu_permission_verification(
                app, user_id, shifu_bid, self.permission.value
            )
            if not has_permission:
                raise_error("server.shifu.noPermission")

            return f(*args, **kwargs)

        return decorated_function


def _get_request_base_url() -> str:
    """
    Determine the base URL based on the incoming request headers.
    """
    origin = request.headers.get("Origin")
    if origin:
        return origin.rstrip("/")
    referer = request.headers.get("Referer")
    if referer:
        parsed_referer = urlsplit(referer)
        if parsed_referer.scheme and parsed_referer.netloc:
            return f"{parsed_referer.scheme}://{parsed_referer.netloc}"
    return request.url_root.rstrip("/")


@inject
def register_shifu_routes(app: Flask, path_prefix="/api/shifu"):
    """
    Register shifu routes
    """
    app.logger.info(f"register shifu routes {path_prefix}")

    @app.route(path_prefix + "/shifus", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW, is_creator=True)
    def get_shifu_list_api():
        """
        get shifu list
        ---
        tags:
            - shifu
        parameters:
            - name: page_index
              type: integer
              required: true
            - name: page_size
              type: integer
              required: true
            - name: is_favorite
              type: boolean
              required: true
            - name: creator_only
              type: boolean
              required: false
            - name: archived
              type: boolean
              required: false
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
        is_favorite = True if is_favorite.lower() == "true" else False
        archived_param = request.args.get("archived")
        archived = False
        if archived_param is not None:
            archived = archived_param.lower() == "true"
        creator_only_param = request.args.get("creator_only")
        creator_only = False
        if creator_only_param is not None:
            creator_only = creator_only_param.lower() == "true"
        try:
            page_index = int(page_index)
            page_size = int(page_size)
        except ValueError:
            raise_param_error("page_index or page_size is not a number")

        if page_index < 0 or page_size < 1:
            raise_param_error("page_index or page_size is less than 0")
        app.logger.info(
            "get shifu list, user_id: %s, page_index: %s, page_size: %s, is_favorite: %s, archived: %s, creator_only: %s",
            user_id,
            page_index,
            page_size,
            is_favorite,
            archived,
            creator_only,
        )
        return make_common_response(
            get_shifu_draft_list(
                app,
                user_id,
                page_index,
                page_size,
                is_favorite,
                archived,
                creator_only,
            )
        )

    @app.route(path_prefix + "/shifus/<shifu_id>/archive", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def archive_shifu_api(shifu_id: str):
        user_id = request.user.user_id
        archive_shifu(app, user_id, shifu_id)
        return make_common_response({"archived": True})

    @app.route(path_prefix + "/shifus/<shifu_id>/unarchive", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def unarchive_shifu_api(shifu_id: str):
        user_id = request.user.user_id
        unarchive_shifu(app, user_id, shifu_id)
        return make_common_response({"archived": False})

    @app.route(path_prefix + "/shifus", methods=["PUT"])
    @ShifuTokenValidation(ShifuPermission.VIEW, is_creator=True)
    def create_shifu_api():
        """
        create shifu
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
        user_id = request.user.user_id
        shifu_name = request.get_json().get("name")
        if not shifu_name:
            raise_param_error("name is required")
        shifu_description = request.get_json().get("description")
        shifu_avatar = request.get_json().get("avatar", "")
        return make_common_response(
            create_shifu_draft(
                app, user_id, shifu_name, shifu_description, shifu_avatar, []
            )
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/detail", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    @with_shifu_context()
    def get_shifu_detail_api(shifu_bid: str):
        """
        get shifu detail
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
        base_url = _get_request_base_url()
        app.logger.info(f"get shifu detail, user_id: {user_id}, shifu_bid: {shifu_bid}")
        return make_common_response(
            get_shifu_draft_info(app, user_id, shifu_bid, base_url)
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/detail", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    @with_shifu_context()
    def save_shifu_detail_api(shifu_bid: str):
        """
        save shifu detail
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
                    temperature:
                        type: number
                        description: shifu temperature
                    tts_enabled:
                        type: boolean
                        description: TTS enabled
                    tts_provider:
                        type: string
                        description: TTS provider (minimax, volcengine, baidu, aliyun)
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
        json_data = request.get_json()
        shifu_name = json_data.get("name")
        shifu_description = json_data.get("description")
        shifu_avatar = json_data.get("avatar")
        shifu_keywords = json_data.get("keywords")
        shifu_model = json_data.get("model")
        shifu_price = json_data.get("price")
        shifu_temperature = json_data.get("temperature")
        shifu_system_prompt = json_data.get("system_prompt", None)
        # TTS Configuration
        tts_enabled = json_data.get("tts_enabled", False)
        tts_provider = json_data.get("tts_provider", "") or ""
        tts_provider = tts_provider.strip().lower()
        if tts_provider == "default":
            tts_provider = ""
        tts_model = json_data.get("tts_model", "")
        tts_voice_id = json_data.get("tts_voice_id", "")
        tts_speed = json_data.get("tts_speed", 1.0)
        tts_pitch = json_data.get("tts_pitch", 0)
        tts_emotion = json_data.get("tts_emotion", "")
        base_url = _get_request_base_url()
        return make_common_response(
            save_shifu_draft_info(
                app,
                user_id,
                shifu_bid,
                shifu_name,
                shifu_description,
                shifu_avatar,
                shifu_keywords,
                shifu_model,
                shifu_temperature,
                shifu_price,
                shifu_system_prompt,
                base_url,
                tts_enabled=tts_enabled,
                tts_provider=tts_provider,
                tts_model=tts_model,
                tts_voice_id=tts_voice_id,
                tts_speed=tts_speed,
                tts_pitch=tts_pitch,
                tts_emotion=tts_emotion,
            )
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/favorite", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.VIEW, is_creator=True)
    @with_shifu_context()
    def mark_favorite_shifu_api():
        """
        mark favorite shifu
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
        shifu_bid = request.view_args.get("shifu_bid")
        is_favorite = request.get_json().get("is_favorite")
        if isinstance(is_favorite, str):
            is_favorite = True if is_favorite.lower() == "true" else False
        elif isinstance(is_favorite, bool):
            is_favorite = is_favorite
        else:
            raise_param_error("is_favorite is not a boolean")
        return make_common_response(
            mark_or_unmark_favorite_shifu(app, user_id, shifu_bid, is_favorite)
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/publish", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.PUBLISH)
    @with_shifu_context()
    def publish_shifu_api(shifu_bid: str):
        """
        publish shifu
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
        user_id = request.user.user_id
        base_url = _get_request_base_url()
        return make_common_response(
            publish_shifu_draft(app, user_id, shifu_bid, base_url)
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/preview", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    @with_shifu_context()
    def preview_shifu_api(shifu_bid: str):
        """
        preview shifu
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
        base_url = _get_request_base_url()
        return make_common_response(
            preview_shifu_draft(app, user_id, shifu_bid, variables, base_url)
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/outlines/reorder", methods=["PATCH"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    @with_shifu_context()
    def update_chapter_order_api(shifu_bid: str):
        """
        update chapter order
        reset the chapter order to the order of the chapter ids
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
                $ref: "#/components/schemas/ReorderOutlineDto"


        responses:
            200:
                description: update chapter order success
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
                                        $ref: "#/components/schemas/OutlineDto"
        """
        user_id = request.user.user_id
        outlines = request.get_json().get("outlines")
        app.logger.info(type(outlines))
        app.logger.info(
            f"reorder outline tree, user_id: {user_id}, shifu_bid: {shifu_bid}, outlines: {outlines}"
        )
        return make_common_response(
            reorder_outline_tree(app, user_id, shifu_bid, outlines)
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/outlines", methods=["PUT"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    @with_shifu_context()
    def create_outline_api(shifu_bid: str):
        """
        create unit
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
                    parent_bid:
                        type: string
                        description: parent id
                    name:
                        type: string
                        description: outline name
                    description:
                        type: string
                        description: outline description
                    type:
                        type: string
                        description: outline type (normal,trial,guest)
                    system_prompt:
                        type: string
                        description: outline system prompt
                    is_hidden:
                        type: boolean
                        description: outline is hidden
                    index:
                        type: integer
                        description: outline index
        responses:
            200:
                description: create outline success
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
                                    $ref: "#/components/schemas/SimpleOutlineDto"
        """
        user_id = request.user.user_id
        parent_bid = request.get_json().get("parent_bid")
        name = request.get_json().get("name")
        description = request.get_json().get("description", "")
        type = request.get_json().get("type", UNIT_TYPE_GUEST)
        index = request.get_json().get("index", None)
        system_prompt = request.get_json().get("system_prompt", None)
        is_hidden = request.get_json().get("is_hidden", False)
        return make_common_response(
            create_outline(
                app,
                user_id,
                shifu_bid,
                parent_bid,
                name,
                description,
                index,
                type,
                system_prompt,
                is_hidden,
            )
        )

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>", methods=["POST"]
    )
    @ShifuTokenValidation(ShifuPermission.EDIT)
    def modify_outline_api(shifu_bid: str, outline_bid: str):
        """
        modify outline
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
                        description: outline name
                    description:
                        type: string
                        description: outline description
                    index:
                        type: integer
                        description: outline index
                    system_prompt:
                        type: string
                        description: outline system prompt
                    is_hidden:
                        type: boolean
                        description: outline is hidden
                    type:
                        type: string
                        description: unit type (normal,trial,guest)
        responses:
            200:
                description: modify outline success
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
                                    $ref: "#/components/schemas/OutlineDto"
        """
        user_id = request.user.user_id
        name = request.get_json().get("name")
        description = request.get_json().get("description")
        index = request.get_json().get("index")
        system_prompt = request.get_json().get("system_prompt", None)
        is_hidden = request.get_json().get("is_hidden", False)
        type = request.get_json().get("type", UNIT_TYPE_GUEST)
        return make_common_response(
            modify_unit(
                app,
                user_id,
                outline_bid,
                name,
                description,
                index,
                system_prompt,
                is_hidden,
                type,
            )
        )

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>", methods=["GET"]
    )
    @ShifuTokenValidation(ShifuPermission.VIEW)
    @with_shifu_context()
    def get_unit_info_api(shifu_bid: str, outline_bid: str):
        """
        get unit info
        ---
        tags:
            - shifu
        parameters:
            - name: outline_bid
              type: string
              required: true
        responses:
            200:
                description: get unit info success
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
                                    $ref: "#/components/schemas/OutlineDto"
        """
        user_id = request.user.user_id
        return make_common_response(get_unit_by_id(app, user_id, outline_bid))

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>",
        methods=["DELETE"],
    )
    @ShifuTokenValidation(ShifuPermission.EDIT)
    @with_shifu_context()
    def delete_unit_api(shifu_bid: str, outline_bid: str):
        """
        delete unit
        ---
        tags:
            - shifu
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - name: outline_bid
              type: string
              required: true
        responses:
            200:
                description: delete unit success
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
                                    description: delete unit success
        """
        user_id = request.user.user_id
        return make_common_response(delete_unit(app, user_id, outline_bid))

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>/mdflow",
        methods=["GET"],
    )
    @ShifuTokenValidation(ShifuPermission.VIEW)
    @with_shifu_context()
    def get_mdflow_api(shifu_bid: str, outline_bid: str):
        """
        get mdflow
        ---
        tags:
            - shifu
        parameters:
            - name: outline_bid
              type: string
              required: true
            - name: shifu_bid
              type: string
              required: true
        responses:
            200:
                description: get mdflow success
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
                                    description: mdflow
        """
        user_id = request.user.user_id
        return make_common_response(get_shifu_mdflow(app, user_id, outline_bid))

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>/mdflow",
        methods=["POST"],
    )
    @ShifuTokenValidation(ShifuPermission.EDIT)
    def save_mdflow_api(shifu_bid: str, outline_bid: str):
        """
        save mdflow
        ---
        tags:
            - shifu
        parameters:
            - name: outline_bid
              type: string
              required: true
            - name: shifu_bid
              type: string
              required: true
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    data:
                        type: string
                        description: mdflow
        responses:
            200:
                description: save mdflow success
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
                                    description: mdflow
        """
        user_id = request.user.user_id
        content = request.get_json().get("data")
        return make_common_response(
            save_shifu_mdflow(app, user_id, shifu_bid, outline_bid, content)
        )

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>/mdflow/parse",
        methods=["POST"],
    )
    @ShifuTokenValidation(ShifuPermission.VIEW)
    @with_shifu_context()
    def parse_mdflow_api(shifu_bid: str, outline_bid: str):
        """
        parse mdflow
        ---
        tags:
            - shifu
        parameters:
            - name: outline_bid
              type: string
              required: true
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    data:
                        type: string
                        description: mdflow
        responses:
            200:
                description: parse mdflow success
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
                                    $ref: "#/components/schemas/MdflowDTOParseResult"
        """
        data = request.get_json().get("data", None)
        return make_common_response(
            parse_shifu_mdflow(app, shifu_bid, outline_bid, data)
        )

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>/mdflow/run",
        methods=["POST"],
    )
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def run_mdflow_api(shifu_bid: str, outline_bid: str):
        """
        run mdflow

        Raises:
            NotImplementedError: This API endpoint is not yet implemented
        """
        raise NotImplementedError("MDFlow run API is not yet implemented")

    @app.route(path_prefix + "/shifus/<shifu_bid>/outlines", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    @with_shifu_context()
    def get_outline_tree_api(shifu_bid: str):
        """
        get outline tree
        ---
        tags:
            - shifu
        parameters:
            - name: shifu_bid
              type: string
              required: true
        responses:
            200:
                description: get outline tree success
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
                                        $ref: "#/components/schemas/SimpleOutlineDto"
        """
        user_id = request.user.user_id
        return make_common_response(get_outline_tree(app, user_id, shifu_bid))

    @app.route(path_prefix + "/upfile", methods=["POST"])
    def upfile_api():
        """
        upfile to oss
        ---
        tags:
            - shifu
        parameters:
            - in: formData
              name: file
              type: file
              required: true
              description: documents
        responses:
            200:
                description: upload success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                    description: code
                                message:
                                    type: string
                                    description: return msg
                                data:
                                    type: string
                                    description: shifu file url
        """
        file = request.files.get("file", None)
        resource_id = request.values.get("resource_id", None)
        if resource_id is None:
            resource_id = ""
        user_id = request.user.user_id
        if not file:
            raise_param_error("file")
        return make_common_response(upload_file(app, user_id, resource_id, file))

    @app.route(path_prefix + "/url-upfile", methods=["POST"])
    def upload_url_api():
        """
        upload url to oss
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
                    url:
                        type: string
                        description: url
        responses:
            200:
                description: upload success
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
                                    description: uploaded file url
        """
        user_id = request.user.user_id
        url = request.get_json().get("url")
        if not url:
            raise_param_error("url is required")
        return make_common_response(upload_url(app, user_id, url))

    @app.route(path_prefix + "/get-video-info", methods=["POST"])
    def get_video_info_api():
        """
        get video info
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
                    url:
                        type: string
                        description: url
        responses:
            200:
                description: get video info success
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
                                    description: video metadata
        """
        user_id = request.user.user_id
        url = request.get_json().get("url")
        if not url:
            raise_param_error("url is required")
        return make_common_response(get_video_info(app, user_id, url))

    @app.route(path_prefix + "/shifus/<shifu_bid>/export", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def export_shifu_api(shifu_bid: str):
        """
        export shifu
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
        export_shifu(app, shifu_bid, str(file_path))

        @after_this_request
        def cleanup(response):
            try:
                os.remove(file_path)
                os.rmdir(temp_dir)
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

    @app.route(path_prefix + "/tts/config", methods=["GET"])
    @bypass_token_validation
    def tts_config_api():
        """
        Get TTS provider configuration
        ---
        tags:
            - tts
        responses:
            200:
                description: TTS provider configuration
                content:
                    application/json:
                        schema:
                            type: object
                            properties:
                                providers:
                                    type: array
                                    description: List of available providers with configs
                                default_provider:
                                    type: string
                                    description: Default provider name
        """
        from flaskr.api.tts import get_all_provider_configs

        config = get_all_provider_configs()
        return make_common_response(config)

    @app.route(path_prefix + "/tts/preview", methods=["POST"])
    @bypass_token_validation
    def tts_preview_api():
        """
        Preview TTS with specified settings
        ---
        tags:
            - tts
        requestBody:
            required: true
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            voice_id:
                                type: string
                                description: Voice ID for synthesis
                            speed:
                                type: number
                                description: Speech speed (provider-specific range)
                            pitch:
                                type: integer
                                description: Pitch adjustment (provider-specific range)
                            emotion:
                                type: string
                                description: Emotion setting
                            text:
                                type: string
                                description: Optional custom text to preview
        responses:
            200:
                description: stream TTS preview audio
                content:
                    text/event-stream:
                        schema:
                            type: string
                            example: 'data: {"type":"audio_segment","content":{"segment_index":0,"audio_data":"...","duration_ms":123,"is_final":false}}'
        """
        from flaskr.api.tts import (
            synthesize_text,
            is_tts_configured,
            get_default_voice_settings,
            get_default_audio_settings,
        )
        from flaskr.service.tts.pipeline import split_text_for_tts
        from flaskr.service.tts.validation import validate_tts_settings_strict

        json_data = request.get_json() or {}
        provider_name = (json_data.get("provider") or "").strip().lower()
        model = (json_data.get("model") or "").strip()
        voice_id = json_data.get("voice_id") or ""
        speed_raw = json_data.get("speed")
        pitch_raw = json_data.get("pitch")
        emotion = json_data.get("emotion", "")
        text = json_data.get(
            "text",
            "你好，这是语音合成的试听效果。Hello, this is a preview of text-to-speech.",
        )

        validated = validate_tts_settings_strict(
            provider=provider_name,
            model=model,
            voice_id=voice_id,
            speed=speed_raw,
            pitch=pitch_raw,
            emotion=emotion,
        )

        if not is_tts_configured(validated.provider):
            raise_param_error(f"TTS provider is not configured: {validated.provider}")

        # Limit text length for preview
        if len(text) > 200:
            text = text[:200]

        voice_settings = get_default_voice_settings(validated.provider)
        voice_settings.voice_id = validated.voice_id
        voice_settings.speed = validated.speed
        voice_settings.pitch = validated.pitch
        voice_settings.emotion = validated.emotion

        segments = split_text_for_tts(text, provider_name=validated.provider)
        if not segments:
            raise_error("TTS_PREVIEW_FAILED")

        audio_settings = get_default_audio_settings(validated.provider)
        safe_audio_settings = replace(audio_settings, format="mp3")
        audio_bid = uuid.uuid4().hex

        def event_stream():
            total_duration_ms = 0
            try:
                for index, segment_text in enumerate(segments):
                    result = synthesize_text(
                        text=segment_text,
                        voice_settings=voice_settings,
                        audio_settings=safe_audio_settings,
                        model=validated.model or None,
                        provider_name=validated.provider,
                    )
                    total_duration_ms += int(result.duration_ms or 0)
                    audio_base64 = base64.b64encode(result.audio_data).decode("utf-8")
                    payload = {
                        "outline_bid": "",
                        "generated_block_bid": "",
                        "type": "audio_segment",
                        "content": {
                            "segment_index": index,
                            "audio_data": audio_base64,
                            "duration_ms": int(result.duration_ms or 0),
                            "is_final": False,
                        },
                    }
                    yield (
                        "data: "
                        + json.dumps(payload, ensure_ascii=False)
                        + "\n\n".encode("utf-8").decode("utf-8")
                    )

                payload = {
                    "outline_bid": "",
                    "generated_block_bid": "",
                    "type": "audio_complete",
                    "content": {
                        "audio_url": "",
                        "audio_bid": audio_bid,
                        "duration_ms": total_duration_ms,
                    },
                }
                yield (
                    "data: "
                    + json.dumps(payload, ensure_ascii=False)
                    + "\n\n".encode("utf-8").decode("utf-8")
                )
            except GeneratorExit:
                current_app.logger.info("client closed tts preview stream early")
                raise
            except Exception:
                current_app.logger.error("TTS preview stream failed", exc_info=True)
                raise

        return Response(
            stream_with_context(event_stream()),
            headers={"Cache-Control": "no-cache"},
            mimetype="text/event-stream",
        )

    return app
