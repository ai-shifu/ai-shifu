"""Register ask-provider configuration and preview routes.

Route bodies resolve service functions through ``flaskr.service.shifu.route``
so patching a name on that module keeps affecting the registered views.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from flask import request
from flaskr.common.http import bypass_token_validation, make_common_response
from flaskr.i18n import _, get_current_language, set_language
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from typing import Any

    from flask import Flask


def register_shifu_ask_routes(
    app: Flask, path_prefix: str, *, _admit_creator_debug_usage: Callable[[object], str]
) -> None:
    """Register ask-provider config and preview routes."""
    from flaskr.service.shifu import route as shifu_route

    @app.route(path_prefix + "/ask/config", methods=["GET"])
    @bypass_token_validation
    def ask_config_api() -> str:
        """Get ask provider configuration metadata.

        ---
        tags:
            - ask
        responses:
            200:
                description: Ask provider configuration metadata
                content:
                    application/json:
                        schema:
                            type: object
                            properties:
                                feature_enabled:
                                    type: boolean
                                default:
                                    type: object
                                modes:
                                    type: array
                                providers:
                                    type: array
        """
        original_language = get_current_language()
        token = request.cookies.get("token", None)
        if not token:
            token = request.args.get("token", None)
        if not token:
            token = request.headers.get("Token", None)

        if token:
            # An unusable token just means the default language is kept.
            with contextlib.suppress(Exception):
                user = shifu_route.validate_user(app, str(token))
                set_language(shifu_route.get_user_language(user))

        try:
            return make_common_response(shifu_route.get_ask_provider_metadata())
        finally:
            set_language(original_language)

    @app.route(path_prefix + "/ask/preview", methods=["POST"])
    def ask_preview_api() -> str:
        """Preview ask provider output with current settings.

        ---
        tags:
            - ask
        requestBody:
            required: true
            content:
                application/json:
                    schema:
                        type: object
                        required: [shifu_bid]
                        properties:
                            shifu_bid:
                                type: string
                                description: Course to preview; requires edit permission
                            query:
                                type: string
                                description: Test question content
                            ask_model:
                                type: string
                                description: Ask model used for llm/fallback
                            ask_system_prompt:
                                type: string
                                description: Optional ask system prompt
                            ask_provider_config:
                                type: object
                                description: Ask provider config ({provider, mode, config})
        responses:
            200:
                description: Ask provider preview result
                content:
                    application/json:
                        schema:
                            type: object
                            properties:
                                answer:
                                    type: string
                                    description: Preview output text
                                provider:
                                    type: string
                                    description: Actual provider used
                                requested_provider:
                                    type: string
                                    description: Requested provider in input config
                                mode:
                                    type: string
                                    description: Provider mode
                                fallback_used:
                                    type: boolean
                                    description: Whether fallback to llm happened
                                provider_error:
                                    type: string
                                    description: Provider error before fallback
        """
        from flaskr.api.llm import chat_llm
        from flaskr.service.learn.ask_provider_adapters import (
            AskProviderError,
            AskProviderRuntime,
            AskProviderTimeoutError,
            apply_knowledge_to_messages,
            stream_ask_provider_response,
        )
        from flaskr.service.learn.ask_provider_adapters.consts import (
            ASK_PROVIDERS_WITH_LLM_SYNTHESIS,
        )
        from flaskr.service.metering import UsageContext
        from flaskr.service.shifu.shifu_draft_funcs import (
            ASK_PROVIDER_LLM,
            ASK_PROVIDER_MODE_PROVIDER_ONLY,
            ASK_PROVIDER_MODE_PROVIDER_THEN_LLM,
        )

        json_data = request.get_json() or {}

        query = str(json_data.get("query") or "").strip()
        if not query or len(query) > 1000:
            raise_param_error("query")

        raw_ask_provider_config = json_data.get("ask_provider_config")
        if raw_ask_provider_config is None and any(
            key in json_data for key in ("provider", "mode", "config")
        ):
            raw_ask_provider_config = {
                "provider": json_data.get("provider"),
                "mode": json_data.get("mode"),
                "config": json_data.get("config"),
            }
        ask_provider_config = shifu_route._parse_ask_provider_config(
            raw_ask_provider_config or {}
        )
        if ask_provider_config is None:
            ask_provider_config = shifu_route.normalize_ask_provider_config({})

        requested_provider = ask_provider_config.get("provider", ASK_PROVIDER_LLM)
        mode = ask_provider_config.get("mode", ASK_PROVIDER_MODE_PROVIDER_ONLY)
        require_llm_model = (
            requested_provider == ASK_PROVIDER_LLM
            or mode == ASK_PROVIDER_MODE_PROVIDER_THEN_LLM
            or requested_provider in ASK_PROVIDERS_WITH_LLM_SYNTHESIS
        )

        preview_shifu_bid = _admit_creator_debug_usage(json_data.get("shifu_bid"))
        preview_course = shifu_route.get_latest_shifu_draft(preview_shifu_bid)
        if preview_course is None:
            raise_error("server.shifu.shifuNotFound")
        ask_model = (
            json_data["ask_model"]
            if "ask_model" in json_data
            else shifu_route.selection_model(preview_course, follow_up=True)
        )
        from flaskr.service.learn.api import is_live_follow_up_model

        if is_live_follow_up_model(ask_model):
            # Live preview is handled by its separate voice session controller.
            raise_param_error("ask_model")
        ask_usage_metadata = shifu_route.selection_metadata(
            preview_course, follow_up=True
        )
        if require_llm_model:
            ask_model, ask_usage_metadata = shifu_route.resolve_course_selection(
                ask_model, ask_usage_metadata
            )

        # Preview shares the saved follow-up generation settings.
        stored_ask_temperature = preview_course.ask_llm_temperature
        ask_temperature = (
            float(stored_ask_temperature) if stored_ask_temperature is not None else 0.0
        )

        ask_system_prompt = str(json_data.get("ask_system_prompt") or "").strip()

        messages: list[dict[str, str]] = []
        if ask_system_prompt:
            messages.append({"role": "system", "content": ask_system_prompt})
        messages.append({"role": "user", "content": query})

        preview_user_id = str(request.user.user_id).strip()
        preview_scene = "ask_provider_preview"
        preview_title = "ask_provider_preview"
        preview_trace, preview_span = shifu_route.create_trace_with_root_span(
            client=shifu_route.get_langfuse_client(),
            trace_payload={
                "user_id": preview_user_id,
                "input": query,
                "name": shifu_route.build_langfuse_trace_name(
                    preview_title, preview_scene
                ),
                "metadata": {
                    "scene": preview_scene,
                    "requested_provider": requested_provider,
                    "mode": mode,
                },
            },
            root_span_payload={
                "name": shifu_route.build_langfuse_span_name(
                    preview_title,
                    preview_scene,
                    "ask_provider_preview",
                ),
                "input": query,
            },
        )

        def _build_llm_runtime() -> AskProviderRuntime:
            def _chat_llm_stream(
                stream_messages: list[dict[str, str]],
            ) -> Generator[Any, None, None]:
                return chat_llm(
                    app,
                    preview_user_id,
                    preview_span,
                    model=ask_model,
                    usage_metadata=ask_usage_metadata,
                    messages=stream_messages,
                    generation_name="ask_provider_preview",
                    temperature=ask_temperature,
                    usage_context=UsageContext(
                        user_bid=preview_user_id,
                        shifu_bid=preview_shifu_bid,
                        usage_scene=BILL_USAGE_SCENE_DEBUG,
                        billable=1,
                    ),
                    usage_scene=BILL_USAGE_SCENE_DEBUG,
                    billable=1,
                    stream=True,
                )

            return AskProviderRuntime(
                llm_stream_factory=lambda: _chat_llm_stream(
                    apply_knowledge_to_messages(messages, "")
                ),
                llm_context_stream_factory=lambda knowledge_context: _chat_llm_stream(
                    apply_knowledge_to_messages(messages, knowledge_context)
                ),
            )

        def _invoke_provider(
            provider_name: str,
            runtime: AskProviderRuntime | None = None,
        ) -> str:
            chunks: list[str] = []
            provider_resp = stream_ask_provider_response(
                app=app,
                provider=provider_name,
                user_id=preview_user_id,
                user_query=query,
                messages=messages,
                provider_config=ask_provider_config,
                runtime=runtime,
            )
            if provider_name != ASK_PROVIDER_LLM:
                provider_resp = shifu_route.stream_provider_with_langfuse(
                    provider_stream=provider_resp,
                    span=preview_span,
                    app=app,
                    provider_name=provider_name,
                    generation_name=shifu_route.build_langfuse_generation_name(
                        preview_title,
                        preview_scene,
                        f"ask_provider_preview_{provider_name}",
                    ),
                    user_query=query,
                    messages=messages,
                    provider_config=ask_provider_config,
                )
            for chunk in provider_resp:
                text = getattr(chunk, "content", "")
                if isinstance(text, str) and text:
                    chunks.append(text)
            return "".join(chunks).strip()

        used_provider = requested_provider
        fallback_used = False
        provider_error = ""
        answer = ""

        try:
            try:
                llm_runtime = (
                    _build_llm_runtime()
                    if (
                        requested_provider == ASK_PROVIDER_LLM
                        or requested_provider in ASK_PROVIDERS_WITH_LLM_SYNTHESIS
                    )
                    else None
                )
                answer = _invoke_provider(requested_provider, runtime=llm_runtime)
            except (AskProviderError, AskProviderTimeoutError) as error:
                # Surface a localized, human-readable message; keep the raw
                # error (URL, response body) in the logs only.
                app.logger.warning("ask preview provider error: %s", error)
                if isinstance(error, AskProviderTimeoutError):
                    provider_error = str(_("server.learn.askProviderTimeout"))
                else:
                    provider_error = getattr(error, "user_message", None) or str(
                        _("server.learn.askProviderUnavailable")
                    )
                if (
                    mode != ASK_PROVIDER_MODE_PROVIDER_THEN_LLM
                    or requested_provider == ASK_PROVIDER_LLM
                ):
                    raise_param_error(provider_error)
                used_provider = ASK_PROVIDER_LLM
                fallback_used = True
                answer = _invoke_provider(
                    ASK_PROVIDER_LLM, runtime=_build_llm_runtime()
                )

            if not answer:
                raise_param_error("ask preview returned empty response")

            return make_common_response(
                {
                    "answer": answer,
                    "provider": used_provider,
                    "requested_provider": requested_provider,
                    "mode": mode,
                    "fallback_used": fallback_used,
                    "provider_error": provider_error,
                }
            )
        finally:
            preview_output = answer or provider_error
            shifu_route.finalize_langfuse_trace(
                trace=preview_trace,
                root_span=preview_span,
                trace_payload={"output": preview_output},
                root_span_payload={"output": preview_output},
            )
