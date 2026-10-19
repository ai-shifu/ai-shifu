"""Register shifu outline structure routes.

Route bodies resolve service functions through ``flaskr.service.shifu.route``
so patching a name on that module keeps affecting the registered views.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import request
from flaskr.common.http import make_common_response
from flaskr.common.shifu_context import with_shifu_context
from flaskr.service.common.models import raise_param_error

if TYPE_CHECKING:
    from flask import Flask


def register_shifu_outline_routes(app: Flask, path_prefix: str) -> None:
    """Register outline reorder, create, modify, read, and delete routes."""
    from flaskr.service.shifu import route as shifu_route
    from flaskr.service.shifu.route import ShifuPermission, ShifuTokenValidation

    @app.route(path_prefix + "/shifus/<shifu_bid>/outlines/reorder", methods=["PATCH"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    @with_shifu_context()
    def update_chapter_order_api(shifu_bid: str) -> str:
        """Update chapter order.

        Reorder one complete sibling group, or submit the legacy full tree.
        Supply exactly one of order and outlines.

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
                oneOf:
                    - $ref: "#/components/schemas/ReorderOutlineDto"
                    - $ref: "#/components/schemas/ReorderOutlineSiblingsDto"


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
                                    type: boolean
        """
        user_id = request.user.user_id
        request_json = request.get_json(silent=True)
        if not isinstance(request_json, dict):
            raise_param_error("outlines")
        if "order" in request_json:
            if "outlines" in request_json:
                raise_param_error("order")
            return make_common_response(
                shifu_route.reorder_outline_siblings(
                    app, user_id, shifu_bid, request_json["order"]
                )
            )
        outlines = request_json.get("outlines")
        app.logger.info(type(outlines))
        app.logger.info(
            "reorder outline tree, user_id: %s, shifu_bid: %s, outlines: %s",
            user_id,
            shifu_bid,
            outlines,
        )
        return make_common_response(
            shifu_route.reorder_outline_tree(app, user_id, shifu_bid, outlines)
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/outlines", methods=["PUT"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    @with_shifu_context()
    def create_outline_api(shifu_bid: str) -> str:
        """Create unit.

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
        json_data = request.get_json(silent=True) or {}
        if not isinstance(json_data, dict):
            raise_param_error("json body")
        parent_bid = json_data.get("parent_bid")
        name = json_data.get("name")
        # No defaults: None is passed through to create_outline, which applies its
        # own fallback (a new outline still needs a concrete type/visibility).
        outline_type = json_data.get("type")
        system_prompt = json_data.get("system_prompt", None)
        is_hidden = json_data.get("is_hidden")
        if isinstance(is_hidden, str):
            is_hidden = is_hidden.lower() == "true"
        return make_common_response(
            shifu_route.create_outline(
                app,
                user_id,
                shifu_bid,
                parent_bid,
                name,
                outline_type,
                system_prompt,
                is_hidden,
            )
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/outlines/batch", methods=["PUT"])
    @ShifuTokenValidation(ShifuPermission.EDIT)
    @with_shifu_context()
    def create_outlines_batch_api(shifu_bid: str) -> str:
        """Create multiple outlines atomically.

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
                        description: parent outline bid the batch nests under
                    outlines:
                        type: array
                        description: nested outline nodes to create in order
                        items:
                            type: object
                            properties:
                                name:
                                    type: string
                                type:
                                    type: string
                                system_prompt:
                                    type: string
                                is_hidden:
                                    type: boolean
                                children:
                                    type: array
                                    items:
                                        type: object
        responses:
            200:
                description: create outlines success
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    type: array
                                    items:
                                        $ref: "#/components/schemas/SimpleOutlineDto"
        """
        user_id = request.user.user_id
        json_data = request.get_json(silent=True) or {}
        if not isinstance(json_data, dict):
            raise_param_error("json body")
        parent_bid = json_data.get("parent_bid") or ""
        outlines = json_data.get("outlines")
        return make_common_response(
            shifu_route.create_outlines_batch(
                app, user_id, shifu_bid, outlines, parent_bid
            )
        )

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>", methods=["POST"]
    )
    @ShifuTokenValidation(ShifuPermission.EDIT)
    def modify_outline_api(shifu_bid: str, outline_bid: str) -> str:
        """Modify outline.

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
        system_prompt = request.get_json().get("system_prompt", None)
        # No defaults: an omitted type/is_hidden stays None and is preserved by
        # modify_unit (PATCH semantics), instead of resetting to guest/visible.
        is_hidden = request.get_json().get("is_hidden")
        if isinstance(is_hidden, str):
            is_hidden = is_hidden.lower() == "true"
        outline_type = request.get_json().get("type")
        return make_common_response(
            shifu_route.modify_unit(
                app,
                user_id,
                shifu_bid,
                outline_bid,
                name,
                description,
                system_prompt,
                is_hidden,
                outline_type,
            )
        )

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>", methods=["GET"]
    )
    @ShifuTokenValidation(ShifuPermission.VIEW)
    @with_shifu_context()
    def get_unit_info_api(shifu_bid: str, outline_bid: str) -> str:
        """Get unit info.

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
        return make_common_response(
            shifu_route.get_unit_by_id(app, user_id, shifu_bid, outline_bid)
        )

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/outlines/<outline_bid>",
        methods=["DELETE"],
    )
    @ShifuTokenValidation(ShifuPermission.EDIT)
    @with_shifu_context()
    def delete_unit_api(shifu_bid: str, outline_bid: str) -> str:
        """Delete unit.

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
        return make_common_response(
            shifu_route.delete_unit(app, user_id, shifu_bid, outline_bid)
        )


def register_shifu_outline_tree_routes(app: Flask, path_prefix: str) -> None:
    """Register the outline tree route."""
    from flaskr.service.shifu import route as shifu_route
    from flaskr.service.shifu.route import ShifuPermission, ShifuTokenValidation

    @app.route(path_prefix + "/shifus/<shifu_bid>/outlines", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW)
    @with_shifu_context()
    def get_outline_tree_api(shifu_bid: str) -> str:
        """Get outline tree.

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
        return make_common_response(
            shifu_route.get_outline_tree(app, user_id, shifu_bid)
        )
