"""Expose HTTP routes for LLM routing."""

from flask import Flask
from flaskr.api.llm import (
    get_course_model_options,
    get_follow_up_models,
    get_legacy_course_model_options,
)
from flaskr.framework.plugin.inject import inject
from flaskr.route.common import make_common_response
from flaskr.service.llm.dtos import FollowUpModelOptionDTO


@inject
def register_llm_routes(app: Flask, path_prefix: str = "/api/llm") -> Flask:
    """Register LLM routes."""
    app.logger.info("register llm routes %s", path_prefix)

    @app.route(path_prefix + "/model-list", methods=["GET"])
    def model_list_api() -> str:
        """Get model list.

        ---
        tags:
            - llm
        responses:
            200:
                description: model list
                content:
                    application/json:
                        schema:
                            type: array
                            items:
                                type: object
                                properties:
                                    model:
                                        type: string
                                        description: configured course model index
                                    display_name:
                                        type: string
                                        description: display label for UI
        """
        return make_common_response(get_legacy_course_model_options(app))

    @app.route(path_prefix + "/follow-up-model-list", methods=["GET"])
    def follow_up_model_list_api() -> str:
        """Get follow-up model options with interaction capabilities.

        ---
        tags:
            - llm
            - cook
        responses:
            200:
                description: follow-up model list
                content:
                    application/json:
                        schema:
                            type: array
                            items:
                                $ref: "#/components/schemas/FollowUpModelOptionDTO"
        """
        return make_common_response(
            [FollowUpModelOptionDTO(**option) for option in get_follow_up_models(app)]
        )

    @app.route(path_prefix + "/course-model-options", methods=["GET"])
    def course_model_options_api() -> str:
        """Return configured course model choices with current availability and credit multipliers."""
        return make_common_response(get_course_model_options(app))

    return app
