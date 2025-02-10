from flask import Flask, request
from .funcs import get_scenario_list, create_scenario, mark_or_unmark_favorite_scenario
from flaskr.route.common import make_common_response
from flaskr.framework.plugin.inject import inject
from flaskr.service.common.models import raise_error


@inject
def register_scenario_routes(app: Flask, path_prefix="/api/scenario"):
    app.logger.info(f"register scenario routes {path_prefix}")

    @app.route(path_prefix + "/scenarios", methods=["GET"])
    def get_scenario_list_api():
        """
        get scenario list
        ---
        tags:
            - scenario
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
                description: get scenario list success
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
            raise_error(
                "COMMON.PARAMS_ERROR", "page_index or page_size is not a number"
            )

        if page_index < 0 or page_size < 1:
            raise_error("COMMON.PARAMS_ERROR", "page_index or page_size is less than 0")
        app.logger.info(
            f"get scenario list, user_id: {user_id}, page_index: {page_index}, page_size: {page_size}, is_favorite: {is_favorite}"
        )
        return make_common_response(
            get_scenario_list(app, user_id, page_index, page_size, is_favorite)
        )

    @app.route(path_prefix + "/create-scenario", methods=["POST"])
    def create_scenario_api():
        """
        create scenario
        ---
        tags:
            - scenario
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    scenario_name:
                        type: string
                        description: scenario name
                    scenario_description:
                        type: string
                        description: scenario description
                    scenario_image:
                        type: string
                        description: scenario image
        responses:
            200:
                description: create scenario success
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
                                    $ref: "#/components/schemas/ScenarioDto"
        """
        user_id = request.user.user_id
        scenario_name = request.get_json().get("scenario_name")
        if not scenario_name:
            raise_error("COMMON.PARAMS_ERROR", "scenario_name is required")
        scenario_description = request.get_json().get("scenario_description")
        if not scenario_description:
            raise_error("COMMON.PARAMS_ERROR", "scenario_description is required")
        scenario_image = request.get_json().get("scenario_image")
        return make_common_response(
            create_scenario(
                app, user_id, scenario_name, scenario_description, scenario_image
            )
        )

    @app.route(path_prefix + "/mark-favorite-scenario", methods=["POST"])
    def mark_favorite_scenario_api():
        """
        mark favorite scenario
        ---
        tags:
            - scenario
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    scenario_id:
                        type: string
                        description: scenario id
                    is_favorite:
                        type: boolean
                        description: is favorite
        responses:
            200:
                description: mark favorite scenario success
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
        scenario_id = request.get_json().get("scenario_id")
        is_favorite = request.get_json().get("is_favorite")
        is_favorite = True if is_favorite.lower() == "true" else False
        return make_common_response(
            mark_or_unmark_favorite_scenario(app, user_id, scenario_id, is_favorite)
        )

    return app
