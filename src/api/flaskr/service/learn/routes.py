import json
import uuid

from flask import Flask, Response, request, stream_with_context
from pydantic import ValidationError

from flaskr.framework.plugin.inject import inject
from flaskr.route.common import make_common_response, bypass_token_validation
from flaskr.service.common.models import raise_param_error
from flaskr.service.learn.learn_funcs import (
    get_shifu_info,
    get_outline_item_tree,
    get_learn_record,
    handle_reaction,
    reset_learn_record,
    get_generated_content,
    stream_generated_block_audio,
    stream_preview_tts_audio,
)
from flaskr.service.learn.runscript_v2 import run_script, get_run_status
from flaskr.service.learn.learn_dtos import PlaygroundPreviewRequest
from flaskr.service.learn.context_v2 import RunScriptPreviewContextV2
from flaskr.service.learn.learn_dtos import PreviewSSEMessage, PreviewSSEMessageType
from flaskr.util import generate_id
from flaskr.common.shifu_context import with_shifu_context, get_shifu_context_snapshot


def _normalize_user_input(value):
    if value is None:
        return None
    if isinstance(value, dict):
        normalized = {}
        for key, raw in value.items():
            if raw is None:
                continue
            if isinstance(raw, list):
                cleaned = [str(item) for item in raw if item is not None]
            else:
                cleaned = [str(raw)]
            if cleaned:
                normalized[str(key)] = cleaned
        return normalized or None
    if isinstance(value, list):
        cleaned = [str(item) for item in value if item is not None]
        return {"user_input": cleaned} if cleaned else None
    return {"user_input": [str(value)]}


@inject
def register_learn_routes(app: Flask, path_prefix: str = "/api/learn") -> Flask:
    """
    register learn routes
    """
    app.logger.info(f"register learn routes {path_prefix}")
    preview_service = RunScriptPreviewContextV2(app)

    @app.route(path_prefix + "/shifu/<shifu_bid>", methods=["GET"])
    @bypass_token_validation
    @with_shifu_context()
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
    @with_shifu_context()
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
    @with_shifu_context()
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
                    listen:
                        type: boolean
                        required: false
                        description: Whether to enable streaming TTS during learning (default: true)
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
        payload = request.get_json() or {}
        input = payload.get("input", None)
        input_type = payload.get("input_type", None)
        reload_generated_block_bid = payload.get("reload_generated_block_bid", None)
        listen_raw = payload.get("listen", True)
        if isinstance(listen_raw, str):
            listen = listen_raw.strip().lower() == "true"
        elif listen_raw is None:
            listen = True
        else:
            listen = bool(listen_raw)
        preview_mode = request.args.get("preview_mode", "False")
        app.logger.info(
            f"run outline item, shifu_bid: {shifu_bid}, outline_bid: {outline_bid}, preview_mode: {preview_mode}, listen: {listen}"
        )
        preview_mode = True if preview_mode.lower() == "true" else False
        shifu_context_snapshot = get_shifu_context_snapshot()
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
                    listen=listen,
                    preview_mode=preview_mode,
                    shifu_context_snapshot=shifu_context_snapshot,
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
    @with_shifu_context()
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
                    content:
                        type: string
                        required: true
                        description: Markdown-Flow document content (legacy alias: prompt)
                    block_index:
                        type: integer
                        required: true
                        description: block index to preview
                    context:
                        type: array
                        required: false
                        description: chat context forwarded to LLM
                        items:
                            type: object
                    document_prompt:
                        type: string
                        required: false
                        description: document prompt
                    variables:
                        type: object
                        required: false
                        description: variables
                    user_input:
                        type: object
                        required: false
                        description: user input map (legacy alias: input)
                    interaction_prompt:
                        type: string
                        required: false
                        description: override interaction render prompt
                    interaction_error_prompt:
                        type: string
                        required: false
                        description: override interaction error prompt
                    model:
                        type: string
                        required: false
                        description: override LLM model
                    temperature:
                        type: number
                        required: false
                        description: override LLM temperature (0.0-2.0)
        responses:
            200:
                description: stream preview block success
                content:
                    text/event-stream:
                        schema:
                            type: string
                            example: 'data: {"type":"content","data":{"mdflow":"..."}}'
        """
        payload = request.get_json(silent=True) or {}
        normalized_user_input = payload.get("user_input")
        if normalized_user_input is None and "input" in payload:
            normalized_user_input = _normalize_user_input(payload.get("input"))
        block_index = payload.get("block_index")
        if block_index is None:
            block_index = payload.get("blockIndex")
        preview_payload = {
            "content": payload.get("content") or payload.get("prompt"),
            "block_index": block_index,
            "context": payload.get("context"),
            "variables": payload.get("variables"),
            "user_input": normalized_user_input,
            "document_prompt": payload.get("document_prompt"),
            "interaction_prompt": payload.get("interaction_prompt"),
            "interaction_error_prompt": payload.get("interaction_error_prompt"),
            "model": payload.get("model"),
            "temperature": payload.get("temperature"),
        }
        try:
            preview_request = PlaygroundPreviewRequest(**preview_payload)
        except ValidationError as exc:
            raise_param_error(str(exc))

        user_bid = request.user.user_id
        session_id = (
            request.headers.get("Session-Id") or f"preview-{uuid.uuid4().hex[:8]}"
        )
        app.logger.info(
            "preview outline block, shifu_bid: %s, outline_bid: %s, user_bid: %s, block_index: %s",
            shifu_bid,
            outline_bid,
            user_bid,
            preview_request.block_index,
        )

        def event_stream():
            try:
                for message in preview_service.stream_preview(
                    preview_request=preview_request,
                    shifu_bid=shifu_bid,
                    outline_bid=outline_bid,
                    user_bid=user_bid,
                    session_id=session_id,
                ):
                    payload = (
                        message.__json__() if hasattr(message, "__json__") else message
                    )
                    yield (
                        "data: "
                        + json.dumps(payload, ensure_ascii=False)
                        + "\n\n".encode("utf-8").decode("utf-8")
                    )
            except GeneratorExit:
                app.logger.info("client closed preview stream early")
                raise
            except Exception as exc:
                app.logger.error("preview outline block failed", exc_info=True)
                yield (
                    "data: "
                    + json.dumps(
                        PreviewSSEMessage(
                            generated_block_bid=generate_id(app),
                            type=PreviewSSEMessageType.ERROR,
                            data=str(exc),
                        ).__json__(),
                        ensure_ascii=False,
                    )
                    + "\n\n".encode("utf-8").decode("utf-8")
                )

        return Response(
            stream_with_context(event_stream()),
            headers={"Cache-Control": "no-cache"},
            mimetype="text/event-stream",
        )

    @app.route(
        path_prefix + "/shifu/<shifu_bid>/run/<outline_bid>",
        methods=["GET"],
    )
    @with_shifu_context()
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
    @with_shifu_context()
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
    @with_shifu_context()
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
    @with_shifu_context()
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

    @app.route(
        path_prefix + "/shifu/<shifu_bid>/generated-contents/<generated_block_bid>",
        methods=["GET"],
    )
    @with_shifu_context()
    def get_generated_content_api(shifu_bid: str, generated_block_bid: str):
        """
        get the content of the generated block
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
        responses:
            200:
                description: get the content of the generated block success
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
                                    $ref: "#/components/schemas/GeneratedInfoDTO"
        """
        user_bid = request.user.user_id
        preview_mode = request.args.get("preview_mode", "False")
        app.logger.info(
            f"get generated content, shifu_bid: {shifu_bid}, generated_block_bid: {generated_block_bid}, preview_mode: {preview_mode}"
        )
        preview_mode = preview_mode.lower() == "true"
        return make_common_response(
            get_generated_content(
                app, shifu_bid, generated_block_bid, user_bid, preview_mode
            )
        )

    @app.route(
        path_prefix + "/shifu/<shifu_bid>/generated-blocks/<generated_block_bid>/tts",
        methods=["POST"],
    )
    @with_shifu_context()
    def synthesize_generated_block_audio_api(shifu_bid: str, generated_block_bid: str):
        """
        Synthesize audio for a generated block (C-end, persisted)
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
            - in: query
              name: preview_mode
              type: string
              required: false
            - in: query
              name: listen
              type: string
              required: false
              description: Whether to enable listen-mode segmented TTS (default: false)
        responses:
            200:
                description: stream synthesized audio
                content:
                    text/event-stream:
                        schema:
                            type: string
                            example: 'data: {"type":"audio_segment","content":{"segment_index":0,"audio_data":"...","duration_ms":123,"is_final":false}}'
        """
        user_bid = request.user.user_id
        preview_mode = request.args.get("preview_mode", "False")
        preview_mode = preview_mode.lower() == "true"
        listen = request.args.get("listen", "False")
        listen = listen.lower() == "true"

        def event_stream():
            try:
                for message in stream_generated_block_audio(
                    app,
                    shifu_bid=shifu_bid,
                    generated_block_bid=generated_block_bid,
                    user_bid=user_bid,
                    preview_mode=preview_mode,
                    listen=listen,
                ):
                    payload = (
                        message.__json__() if hasattr(message, "__json__") else message
                    )
                    yield (
                        "data: "
                        + json.dumps(payload, ensure_ascii=False)
                        + "\n\n".encode("utf-8").decode("utf-8")
                    )
            except GeneratorExit:
                app.logger.info("client closed tts stream early")
                raise
            except Exception:
                app.logger.error(
                    "synthesize generated block audio failed", exc_info=True
                )
                raise

        return Response(
            stream_with_context(event_stream()),
            headers={"Cache-Control": "no-cache"},
            mimetype="text/event-stream",
        )

    @app.route(path_prefix + "/shifu/<shifu_bid>/tts/preview", methods=["POST"])
    @with_shifu_context()
    def synthesize_preview_tts_audio_api(shifu_bid: str):
        """
        Synthesize audio for an arbitrary text (editor preview, not persisted)
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
        requestBody:
            required: true
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            text:
                                type: string
                                description: Text to synthesize
        responses:
            200:
                description: stream preview audio
                content:
                    text/event-stream:
                        schema:
                            type: string
                            example: 'data: {"type":"audio_complete","content":{"audio_url":"...","audio_bid":"...","duration_ms":1234}}'
        """
        user_bid = request.user.user_id
        payload = request.get_json(silent=True) or {}
        text = payload.get("text") or ""
        preview_mode = request.args.get("preview_mode", "False")
        preview_mode = preview_mode.lower() == "true"

        def event_stream():
            try:
                for message in stream_preview_tts_audio(
                    app,
                    shifu_bid=shifu_bid,
                    user_bid=user_bid,
                    text=text,
                    preview_mode=preview_mode,
                ):
                    payload = (
                        message.__json__() if hasattr(message, "__json__") else message
                    )
                    yield (
                        "data: "
                        + json.dumps(payload, ensure_ascii=False)
                        + "\n\n".encode("utf-8").decode("utf-8")
                    )
            except GeneratorExit:
                app.logger.info("client closed preview tts stream early")
                raise
            except Exception:
                app.logger.error("preview tts stream failed", exc_info=True)
                raise

        return Response(
            stream_with_context(event_stream()),
            headers={"Cache-Control": "no-cache"},
            mimetype="text/event-stream",
        )

    return app
