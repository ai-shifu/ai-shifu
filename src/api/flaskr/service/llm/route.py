from flask import Flask
from flaskr.route.common import make_common_response, bypass_token_validation
from flaskr.framework.plugin.inject import inject
from flaskr.api.llm import get_current_models
from flaskr.service.llm.funcs import get_system_prompt, debug_script
from flask import request, Response


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
            - scenario
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

    @app.route(path_prefix + "/get-system-prompt", methods=["GET"])
    @bypass_token_validation
    def get_system_prompt_api():
        """
        get system prompt
        ---
        tags:
            - llm
            - scenario
            - cook
        parameters:
            - in: query
              name: block_id
              required: true
        responses:
            200:
                description: system prompt
                content:
                    application/json:
                        schema:
                            type: object
                            properties:
                                data:
                                    type: string
                                    example: "你好，我是AI助手，很高兴认识你。"
                                code:
                                    type: integer
                                    example: 0
                                message:
                                    type: string
                                    example: "success"

            400:
                description: block not found
                content:
                    application/json:
                        schema:
                            type: string
                            example: "block not found"
        """
        block_id = request.args.get("block_id")
        return make_common_response(get_system_prompt(app, block_id))

    @app.route(path_prefix + "/debug-prompt", methods=["POST"])
    @bypass_token_validation
    def debug_prompt_api():
        """
        debug prompt
        ---
        tags:
            - llm
            - scenario
            - cook
        parameters:
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    block_id:
                        type: string
                        required: true
                    block_prompt:
                        type: string
                        required: true
                    block_system_prompt:
                        type: string
                        required: false
                    block_model:
                        type: string
                        required: false
                    block_temperature:
                        type: number
                        required: false
                    block_variables:
                        type: object
                        required: false
                    block_other_conf:
                        type: object
                        required: false
        responses:
            200:
                description: debug prompt
                content:
                    application/stream+json:
                        schema:
                            type: string
                            example: "debug prompt"

            400:
                description: block not found
                content:
                    application/json:
                        schema:
                            type: string
                            example: "block not found"
        """
        user_id = request.user.user_id if hasattr(request, "user") else None
        block_id = request.json.get("block_id")
        block_prompt = request.json.get("block_prompt", "")
        block_system_prompt = request.json.get("block_system_prompt", "")
        block_model = request.json.get("block_model", "")
        block_temperature = request.json.get("block_temperature", None)
        block_variables = request.json.get("block_variables", {})
        block_other_conf = request.json.get("block_other_conf", {})
        return Response(
            debug_script(
                app,
                user_id,
                block_id,
                block_prompt,
                block_system_prompt,
                block_model,
                block_temperature,
                block_variables,
                block_other_conf,
            ),
            headers={"Cache-Control": "no-cache"},
            mimetype="text/event-stream",
        )

    return app
