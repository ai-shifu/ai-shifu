from flask import Flask
from flaskr.route.common import make_common_response
from flaskr.framework.plugin.inject import inject
from flaskr.api.llm import get_current_models


@inject
def register_llm_routes(app: Flask, path_prefix="/api/llm"):
    app.logger.info(f"register llm routes {path_prefix}")

    @app.route(path_prefix + "/model-list", methods=["GET"])
    def model_list_api():
        """
        get model list
        ---
        tags:
            - llm
            - cook
        responses:
            200:
                description: model list
                content:
                    application/json:
                        schema:
                            type: array
                            items:
                                type: string
        """
        return make_common_response(get_current_models(app))

    return app
