from flask import Flask, request, Response

from flaskr.framework.plugin.inject import inject
from flaskr.route.common import make_common_response, bypass_token_validation
from flaskr.service.common.models import raise_param_error
from flaskr.service.learn.learn_funcs import (
    get_shifu_info,
    get_outline_item_tree,
    get_learn_record,
    handle_reaction,
    reset_learn_record,
)
from flaskr.service.learn.runscript_v2 import run_script, get_run_status


@inject
def register_learn_routes(app: Flask, path_prefix: str = "/api/learn") -> Flask:
    """
    register learn routes
    """
    app.logger.info(f"register learn routes {path_prefix}")

    @app.route(path_prefix + "/shifu/<shifu_bid>", methods=["GET"])
    @bypass_token_validation
    def get_shifu_api(shifu_bid: str):
        """
        get shifu
        ---
        tags:
            - learn
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - in: query
              name: preview_mode
              type: string
              required: false
        responses:
            200:
                description: get shifu success
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
                                    $ref: "#/components/schemas/LearnShifuInfoDTO"
        """
        preview_mode = request.args.get("preview_mode", "False")
        app.logger.info(
            f"get shifu, shifu_bid: {shifu_bid}, preview_mode: {preview_mode}"
        )
        preview_mode = True if preview_mode.lower() == "true" else False
        return make_common_response(get_shifu_info(app, shifu_bid, preview_mode))

    @app.route(path_prefix + "/shifu/<shifu_bid>/outline-item-tree", methods=["GET"])
    def get_outline_item_tree_api(shifu_bid: str):
        """
        get outline item tree
        ---
        tags:
            - learn
        parameters:
            - in: query
              name: preview_mode
              type: string
              required: false
        responses:
            200:
                description: get outline item tree success
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
                                        $ref: "#/components/schemas/LearnOutlineItemInfoDTO"
        """
        preview_mode = request.args.get("preview_mode", "False")
        app.logger.info(
            f"get outline item tree, shifu_bid: {shifu_bid}, preview_mode: {preview_mode}"
        )
        preview_mode = True if preview_mode.lower() == "true" else False
        user_bid = request.user.user_id
        return make_common_response(
            get_outline_item_tree(app, shifu_bid, user_bid, preview_mode)
        )

    @app.route(path_prefix + "/shifu/<shifu_bid>/run/<outline_bid>", methods=["PUT"])
    def run_outline_item_api(shifu_bid: str, outline_bid: str):
        """
        run the MarkdownFlow of the outline
        ---
        tags:
            - learn
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - name: outline_bid
              type: string
              required: true
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    input:
                        type: object
                        required: true
                    input_type:
                        type: string
                        required: false
                    reload_generated_block_bid:
                        type: string
                        required: false
            - in: query
              name: preview_mode
              type: string
              required: false
        responses:
            200:
                description: run the MarkdownFlow of the outline success
                content:
                    text/event-stream:
                        schema:
                            $ref: "#/components/schemas/RunMarkdownFlowDTO"
        """
        user_bid = request.user.user_id
        input = request.get_json().get("input", None)
        input_type = request.get_json().get("input_type", None)
        reload_generated_block_bid = request.get_json().get(
            "reload_generated_block_bid", None
        )
        preview_mode = request.args.get("preview_mode", "False")
        app.logger.info(
            f"run outline item, shifu_bid: {shifu_bid}, outline_bid: {outline_bid}, preview_mode: {preview_mode}"
        )
        preview_mode = True if preview_mode.lower() == "true" else False
        try:
            return Response(
                run_script(
                    app=app,
                    shifu_bid=shifu_bid,
                    outline_bid=outline_bid,
                    user_bid=user_bid,
                    input=input,
                    input_type=input_type,
                    reload_generated_block_bid=reload_generated_block_bid,
                    preview_mode=preview_mode,
                ),
                headers={"Cache-Control": "no-cache"},
                mimetype="text/event-stream",
            )
        except Exception as e:
            app.logger.error(e)
            return make_common_response(e)

    @app.route(
        path_prefix + "/shifu/<shifu_bid>/preview/<outline_bid>",
        methods=["POST"],
    )
    def preview_outline_block_api(shifu_bid: str, outline_bid: str):
        """
        preview a specific outline block
        ---
        tags:
            - learn
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - name: outline_bid
              type: string
              required: true
            - in: body
              name: body
              required: true
              schema:
                type: object
                properties:
                    input:
                        type: object
                        description: input payload for preview
                    block_index:
                        type: integer
                        required: true
                        description: block index to preview
                    prompt:
                        type: string
                        required: true
                        description: preview prompt
        responses:
            200:
                description: preview block success
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
                                    description: preview request echo
        """
        payload = request.get_json() or {}
        block_index = payload.get("block_index")
        prompt = payload.get("prompt")
        if block_index is None:
            raise_param_error("block_index is required")
        if prompt is None:
            raise_param_error("prompt is required")
        user_bid = request.user.user_id
        app.logger.info(
            "preview outline block, shifu_bid: %s, outline_bid: %s, user_bid: %s, block_index: %s",
            shifu_bid,
            outline_bid,
            user_bid,
            block_index,
        )
        response_payload = {
            "shifu_bid": shifu_bid,
            "outline_bid": outline_bid,
            "user_bid": user_bid,
            "input": payload.get("input"),
            "block_index": block_index,
            "prompt": prompt,
        }
        return make_common_response(response_payload)

    @app.route(
        path_prefix + "/shifu/<shifu_bid>/run/<outline_bid>",
        methods=["GET"],
    )
    def get_run_status_api(shifu_bid: str, outline_bid: str):
        """
        get run status
        ---
        tags:
            - learn
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - name: outline_bid
              type: string
              required: true
        responses:
            200:
                description: get run status success
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
                                    $ref: "#/components/schemas/RunStatusDTO"
        """
        user_bid = request.user.user_id

        return make_common_response(
            get_run_status(app, shifu_bid, outline_bid, user_bid)
        )

    @app.route(
        path_prefix + "/shifu/<shifu_bid>/records/<outline_bid>", methods=["GET"]
    )
    def get_record_api(shifu_bid: str, outline_bid: str):
        """
        get learn records of the outline
        ---
        tags:
            - learn
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - name: outline_bid
              type: string
              required: true
        responses:
            200:
                description: get learn records of the outline success
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
                                    $ref: "#/components/schemas/LearnRecordDTO"

        """
        preview_mode = request.args.get("preview_mode", "False")
        app.logger.info(
            f"get learn record, shifu_bid: {shifu_bid}, outline_bid: {outline_bid}, preview_mode: {preview_mode}"
        )
        preview_mode = True if preview_mode.lower() == "true" else False
        user_bid = request.user.user_id
        return make_common_response(
            get_learn_record(app, shifu_bid, outline_bid, user_bid, preview_mode)
        )

    @app.route(
        path_prefix + "/shifu/<shifu_bid>/records/<outline_bid>", methods=["DELETE"]
    )
    def delete_record_api(shifu_bid: str, outline_bid: str):
        """
        reset the record of the outline
        ---
        tags:
            - learn
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - name: outline_bid
              type: string
              required: true
        responses:
            200:
                description: reset the record of the outline success
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

        """
        user_bid = request.user.user_id

        return make_common_response(
            reset_learn_record(app, shifu_bid, outline_bid, user_bid)
        )

    @app.route(
        path_prefix
        + "/shifu/<shifu_bid>/generated-contents/<generated_block_bid>/<action>",
        methods=["POST"],
    )
    def generate_content_api(shifu_bid: str, generated_block_bid: str, action: str):
        """
        generate the content of the generated block
        ---
        tags:
            - learn
        parameters:
            - name: shifu_bid
              type: string
              required: true
            - name: generated_block_bid
              type: string
              required: true
            - name: action
              type: string
              required: true
        responses:
            200:
                description: generate the content of the generated block success
                content:
                    application/json:
                        schema:
                            code:
                                    type: integer
                                    description: code
                            message:
                                    type: string
                                    description: message
        """
        user_bid = request.user.user_id
        app.logger.info(
            f"generate content, shifu_bid: {shifu_bid}, generated_block_bid: {generated_block_bid}, action: {action}"
        )
        return make_common_response(
            handle_reaction(app, shifu_bid, user_bid, generated_block_bid, action)
        )

    return app
