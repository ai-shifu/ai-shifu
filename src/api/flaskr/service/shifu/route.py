from flask import Flask, request, current_app
from .funcs import (
    get_shifu_list,
    create_shifu,
    mark_or_unmark_favorite_shifu,
    publish_shifu,
    preview_shifu,
    get_shifu_info,
    save_shifu_detail,
    get_shifu_detail,
    upload_file,
    shifu_permission_verification,
)
from .outline_funcs import (
    get_chapter_list,
    create_chapter,
    modify_chapter,
    update_chapter_order,
    get_outline_tree,
)
from .unit_funcs import (
    get_unit_list,
    create_unit,
    modify_unit,
    delete_unit,
    get_unit_by_id,
)
from .block_funcs import (
    get_block_list,
    save_block_list,
    add_block,
)
from flaskr.route.common import make_common_response
from flaskr.framework.plugin.inject import inject
from flaskr.service.common.models import raise_param_error, raise_error
from ..lesson.models import LESSON_TYPE_TRIAL
from functools import wraps
from enum import Enum


class ShifuPermission(Enum):
    VIEW = "view"
    EDIT = "edit"
    PUBLISH = "publish"


# Shifu permission verification decorator
# @ShifuTokenValidation(ShifuPermission.xxx)
class ShifuTokenValidation:
    def __init__(self, permission: ShifuPermission = ShifuPermission.VIEW):
        self.permission = permission

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

            shifu_id = request.args.get("shifu_id", None)
            if not shifu_id and request.method.upper() == "POST" and request.is_json:
                shifu_id = request.get_json().get("shifu_id", None)

            if not token:
                raise_param_error("token is required")
            if not shifu_id or not str(shifu_id).strip():
                raise_param_error("shifu_id is required")

            user_id = request.user.user_id
            app = current_app._get_current_object()
            has_permission = shifu_permission_verification(
                app, user_id, shifu_id, self.permission.value
            )
            if not has_permission:
                raise_error("SHIFU.NO_PERMISSION")

            return f(*args, **kwargs)

        return decorated_function


@inject
def register_shifu_routes(app: Flask, path_prefix="/api/shifu"):
    app.logger.info(f"register shifu routes {path_prefix}")

    @app.route(path_prefix + "/shifu-list", methods=["GET"])
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
        try:
            page_index = int(page_index)
            page_size = int(page_size)
        except ValueError:
            raise_param_error("page_index or page_size is not a number")

        if page_index < 0 or page_size < 1:
            raise_param_error("page_index or page_size is less than 0")
        app.logger.info(
            f"get shifu list, user_id: {user_id}, page_index: {page_index}, page_size: {page_size}, is_favorite: {is_favorite}"
        )
        return make_common_response(
            get_shifu_list(app, user_id, page_index, page_size, is_favorite)
        )

    @app.route(path_prefix + "/create-shifu", methods=["POST"])
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
                    shifu_name:
                        type: string
                        description: shifu name
                    shifu_description:
                        type: string
                        description: shifu description
                    shifu_image:
                        type: string
                        description: shifu image
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
        shifu_name = request.get_json().get("shifu_name")
        if not shifu_name:
            raise_param_error("shifu_name is required")
        shifu_description = request.get_json().get("shifu_description")
        shifu_image = request.get_json().get("shifu_image")
        return make_common_response(
            create_shifu(app, user_id, shifu_name, shifu_description, shifu_image)
        )

    @app.route(path_prefix + "/shifu-info", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def get_shifu_info_api():
        """
        get shifu info
        ---
        tags:
            - shifu
        parameters:
            - name: shifu_id
              type: string
              required: true
        responses:
            200:
                description: get shifu info success
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
        shifu_id = request.args.get("shifu_id")
        return make_common_response(get_shifu_info(app, user_id, shifu_id))

    @app.route(path_prefix + "/shifu-detail", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def get_shifu_detail_api():
        """
        get shifu detail
        ---
        tags:
            - shifu
        parameters:
            - name: shifu_id
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
        shifu_id = request.args.get("shifu_id")
        return make_common_response(get_shifu_detail(app, user_id, shifu_id))

    @app.route(path_prefix + "/save-shifu-detail", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    def save_shifu_detail_api():
        """
        save shifu detail
        ---
        tags:
            - shifu
        parameters:
            - name: body
              in: body
              type: object
              required: true
              schema:
                type: object
                properties:
                    shifu_id:
                        type: string
                        description: shifu id
                    shifu_name:
                        type: string
                        description: shifu name
                    shifu_description:
                        type: string
                        description: shifu description
                    shifu_avatar:
                        type: string
                        description: shifu avatar
                    shifu_keywords:
                        type: array
                        items:
                            type: string
                        description: shifu keywords
                    shifu_model:
                        type: string
                        description: shifu model
                    shifu_price:
                        type: number
                        description: shifu price
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
        shifu_id = request.get_json().get("shifu_id")
        shifu_name = request.get_json().get("shifu_name")
        shifu_description = request.get_json().get("shifu_description")
        shifu_avatar = request.get_json().get("shifu_avatar")
        shifu_keywords = request.get_json().get("shifu_keywords")
        shifu_model = request.get_json().get("shifu_model")
        shifu_price = request.get_json().get("shifu_price")
        return make_common_response(
            save_shifu_detail(
                app,
                user_id,
                shifu_id,
                shifu_name,
                shifu_description,
                shifu_avatar,
                shifu_keywords,
                shifu_model,
                shifu_price,
            )
        )

    @app.route(path_prefix + "/mark-favorite-shifu", methods=["POST"])
    def mark_favorite_shifu_api():
        """
        mark favorite shifu
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
                    shifu_id:
                        type: string
                        description: shifu id
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
        shifu_id = request.get_json().get("shifu_id")
        is_favorite = request.get_json().get("is_favorite")
        if isinstance(is_favorite, str):
            is_favorite = True if is_favorite.lower() == "true" else False
        elif isinstance(is_favorite, bool):
            is_favorite = is_favorite
        else:
            raise_param_error("is_favorite is not a boolean")
        return make_common_response(
            mark_or_unmark_favorite_shifu(app, user_id, shifu_id, is_favorite)
        )

    @app.route(path_prefix + "/publish-shifu", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.PUBLISH)
    def publish_shifu_api():
        """
        publish shifu
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
                    shifu_id:
                        type: string
                        description: shifu id

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
        shifu_id = request.get_json().get("shifu_id")
        return make_common_response(publish_shifu(app, user_id, shifu_id))

    @app.route(path_prefix + "/preview-shifu", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def preview_shifu_api():
        """
        preview shifu
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
                    shifu_id:
                        type: string
                        description: shifu id
                    variables:
                        type: object
                        description: variables
                    skip:
                        type: boolean
                        description: skip
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
        shifu_id = request.get_json().get("shifu_id")
        variables = request.get_json().get("variables")
        skip = request.get_json().get("skip", False)
        return make_common_response(
            preview_shifu(app, user_id, shifu_id, variables, skip)
        )

    @app.route(path_prefix + "/chapters", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def get_chapter_list_api():
        """
        get chapter list
        ---
        tags:
            - shifu
        parameters:
            - name: shifu_id
              type: string
              required: true
        """
        user_id = request.user.user_id
        shifu_id = request.args.get("shifu_id")
        if not shifu_id:
            raise_param_error("shifu_id is required")
        return make_common_response(get_chapter_list(app, user_id, shifu_id))

    @app.route(path_prefix + "/create-chapter", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    def create_chapter_api():
        """
        create chapter
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
                    shifu_id:
                        type: string
                        description: shifu id
                    chapter_name:
                        type: string
                        description: chapter name
                    chapter_description:
                        type: string
                        description: chapter description
                    chapter_index:
                        type: integer
                        description: chapter index
        responses:
            200:
                description: create chapter success
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
                                    $ref: "#/components/schemas/ChapterDto"
        """

        app.logger.info(
            f"create chapter, user_id: {request.user.user_id} {request.get_json()}"
        )
        user_id = request.user.user_id
        shifu_id = request.get_json().get("shifu_id")
        if not shifu_id:
            raise_param_error("shifu_id is required")
        chapter_name = request.get_json().get("chapter_name")
        if not chapter_name:
            raise_param_error("chapter_name is required")
        chapter_description = request.get_json().get("chapter_description")
        if not chapter_description:
            raise_param_error("chapter_description is required")
        chapter_index = request.get_json().get("chapter_index", None)
        chapter_type = request.get_json().get("chapter_type", LESSON_TYPE_TRIAL)
        return make_common_response(
            create_chapter(
                app,
                user_id,
                shifu_id,
                chapter_name,
                chapter_description,
                chapter_index,
                chapter_type,
            )
        )

    @app.route(path_prefix + "/modify-chapter", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    def modify_chapter_api():
        """
        modify chapter
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
                    chapter_id:
                        type: string
                        description: chapter id
                    chapter_name:
                        type: string
                        description: chapter name
                    chapter_description:
                        type: string
                        description: chapter description
                    chapter_index:
                        type: integer
                        description: chapter index
        responses:
            200:
                description: modify chapter success
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
                                    $ref: "#/components/schemas/ChapterDto"
        """
        user_id = request.user.user_id
        chapter_id = request.get_json().get("chapter_id")
        if not chapter_id:
            raise_param_error("chapter_id is required")
        chapter_name = request.get_json().get("chapter_name")
        if not chapter_name:
            raise_param_error("chapter_name is required")
        chapter_description = request.get_json().get("chapter_description")
        if not chapter_description:
            raise_param_error("chapter_description is required")
        chapter_index = request.get_json().get("chapter_index", None)
        chapter_type = request.get_json().get("chapter_type", LESSON_TYPE_TRIAL)
        return make_common_response(
            modify_chapter(
                app,
                user_id,
                chapter_id,
                chapter_name,
                chapter_description,
                chapter_index,
                chapter_type,
            )
        )

    @app.route(path_prefix + "/delete-chapter", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    def delete_chapter_api():
        """
        delete chapter
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
                    chapter_id:
                        type: string
                        description: chapter id
        responses:
            200:
                description: delete chapter success
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
                                    description: is deleted
        """
        user_id = request.user.user_id
        chapter_id = request.get_json().get("chapter_id")
        if not chapter_id:
            raise_param_error("chapter_id is required")
        return make_common_response(delete_unit(app, user_id, chapter_id))

    @app.route(path_prefix + "/update-chapter-order", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    def update_chapter_order_api():
        """
        update chapter order
        reset the chapter order to the order of the chapter ids
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
                    shifu_id:
                        type: string
                        description: shifu id
                    chapter_ids:
                        type: array
                        items:
                            type: string
                        description: chapter ids
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
                                        $ref: "#/components/schemas/ChapterDto"
        """
        user_id = request.user.user_id
        shifu_id = request.get_json().get("shifu_id")
        if not shifu_id:
            raise_param_error("shifu_id is required")
        chapter_ids = request.get_json().get("chapter_ids")
        if not chapter_ids:
            raise_param_error("chapter_ids is required")
        return make_common_response(
            update_chapter_order(app, user_id, shifu_id, chapter_ids)
        )

    @app.route(path_prefix + "/units", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def get_unit_list_api():
        """
        get unit list
        ---
        tags:
            - shifu
        parameters:
            - name: shifu_id
              type: string
              required: true
            - name: chapter_id
              type: string
              required: true
        responses:
            200:
                description: get unit list success
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
        shifu_id = request.args.get("shifu_id")
        chapter_id = request.args.get("chapter_id")
        return make_common_response(get_unit_list(app, user_id, shifu_id, chapter_id))

    @app.route(path_prefix + "/create-unit", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    def create_unit_api():
        """
        create unit
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
                    shifu_id:
                        type: string
                        description: shifu id
                    parent_id:
                        type: string
                        description: chapter id
                    unit_name:
                        type: string
                        description: unit name
                    unit_description:
                        type: string
                        description: unit description
                    unit_type:
                        type: string
                        description: unit type (normal,trial)
                    unit_system_prompt:
                        type: string
                        description: unit system prompt
                    unit_is_hidden:
                        type: boolean
                        description: unit is hidden
                    unit_index:
                        type: integer
                        description: unit index
        responses:
            200:
                description: create unit success
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
        shifu_id = request.get_json().get("shifu_id")
        parent_id = request.get_json().get("parent_id")
        unit_name = request.get_json().get("unit_name")
        unit_description = request.get_json().get("unit_description", "")
        unit_type = request.get_json().get("unit_type", LESSON_TYPE_TRIAL)
        unit_index = request.get_json().get("unit_index", None)
        unit_system_prompt = request.get_json().get("unit_system_prompt", None)
        unit_is_hidden = request.get_json().get("unit_is_hidden", False)
        return make_common_response(
            create_unit(
                app,
                user_id,
                shifu_id,
                parent_id,
                unit_name,
                unit_description,
                unit_type,
                unit_index,
                unit_system_prompt,
                unit_is_hidden,
            )
        )

    @app.route(path_prefix + "/modify-unit", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    def modify_unit_api():
        """
        modify unit
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
                    unit_id:
                        type: string
                        description: unit id
                    unit_name:
                        type: string
                        description: unit name
                    unit_description:
                        type: string
                        description: unit description
                    unit_index:
                        type: integer
                        description: unit index
                    unit_system_prompt:
                        type: string
                        description: unit system prompt
                    unit_is_hidden:
                        type: boolean
                        description: unit is hidden
                    unit_type:
                        type: string
                        description: unit type (normal,trial)
        responses:
            200:
                description: modify unit success
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
        unit_id = request.get_json().get("unit_id")
        unit_name = request.get_json().get("unit_name")
        unit_description = request.get_json().get("unit_description")
        unit_index = request.get_json().get("unit_index")
        unit_system_prompt = request.get_json().get("unit_system_prompt", None)
        unit_is_hidden = request.get_json().get("unit_is_hidden", False)
        unit_type = request.get_json().get("unit_type", LESSON_TYPE_TRIAL)
        return make_common_response(
            modify_unit(
                app,
                user_id,
                unit_id,
                unit_name,
                unit_description,
                unit_index,
                unit_system_prompt,
                unit_is_hidden,
                unit_type,
            )
        )

    @app.route(path_prefix + "/unit-info", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def get_unit_info_api():
        """
        get unit info
        ---
        tags:
            - shifu
        parameters:
            - name: unit_id
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
        unit_id = request.args.get("unit_id")
        return make_common_response(get_unit_by_id(app, user_id, unit_id))

    @app.route(path_prefix + "/delete-unit", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    def delete_unit_api():
        """
        delete unit
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
                    unit_id:
                        type: string
                        description: unit id
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
        unit_id = request.get_json().get("unit_id")
        return make_common_response(delete_unit(app, user_id, unit_id))

    @app.route(path_prefix + "/outline-tree", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def get_outline_tree_api():
        """
        get outline tree
        ---
        tags:
            - shifu
        parameters:
            - name: shifu_id
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
        shifu_id = request.args.get("shifu_id")
        return make_common_response(get_outline_tree(app, user_id, shifu_id))

    @app.route(path_prefix + "/blocks", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    def get_block_list_api():
        """
        get block list
        ---
        tags:
            - shifu
        parameters:
            - name: outline_id
              type: string
              required: true
        responses:
            200:
                description: get block list success
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
                                        $ref: "#/components/schemas/BlockDto"
        """
        user_id = request.user.user_id
        outline_id = request.args.get("outline_id")
        return make_common_response(get_block_list(app, user_id, outline_id))

    @app.route(path_prefix + "/save-blocks", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    def save_blocks_api():
        """
        save blocks
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
                    outline_id:
                        type: string
                        description: outline id
                    blocks:
                        type: array
                        items:
                            $ref: "#/components/schemas/BlockDto"
        responses:
            200:
                description: save blocks success
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
                                        $ref: "#/components/schemas/BlockDto"
        """
        user_id = request.user.user_id
        outline_id = request.get_json().get("outline_id")
        blocks = request.get_json().get("blocks")
        return make_common_response(save_block_list(app, user_id, outline_id, blocks))

    @app.route(path_prefix + "/add-block", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    def add_block_api():
        """
        add block
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
                    outline_id:
                        type: string
                        description: outline id
                    block:
                        type: object
                        $ref: "#/components/schemas/BlockDto"
                    block_index:
                        type: integer
                        description: block index
        responses:
            200:
                description: add block success
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
                                    $ref: "#/components/schemas/BlockDto"
        """
        user_id = request.user.user_id
        outline_id = request.get_json().get("outline_id")
        block = request.get_json().get("block")
        block_index = request.get_json().get("block_index")

        return make_common_response(
            add_block(app, user_id, outline_id, block, block_index)
        )

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

    return app
