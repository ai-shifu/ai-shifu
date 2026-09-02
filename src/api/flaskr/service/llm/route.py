"""Expose HTTP routes for LLM routing."""

from flask import Flask
from flaskr.api.llm import get_current_models, get_follow_up_models
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
                                        description: actual model identifier
                                    display_name:
                                        type: string
                                        description: display label for UI
        """
        return make_common_response(get_current_models(app))

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

    return app
