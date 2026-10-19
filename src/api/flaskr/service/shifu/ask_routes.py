"""Register ask-provider configuration and preview routes.

Route bodies resolve service functions through ``flaskr.service.shifu.route``
so patching a name on that module keeps affecting the registered views.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flask import request
from flaskr.common.http import bypass_token_validation, make_common_response
from flaskr.i18n import _, get_current_language, set_language
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from types import ModuleType

    from flask import Flask
    from flaskr.service.learn.ask_provider_adapters import AskProviderRuntime


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
        json_data = request.get_json() or {}
        query = _parse_ask_preview_query(json_data)
        ask_provider_config, requested_provider, mode, require_llm_model = (
            _resolve_ask_preview_provider(json_data)
        )
        preview_shifu_bid = _admit_creator_debug_usage(json_data.get("shifu_bid"))
        context = _build_ask_preview_context(
            app,
            json_data,
            query=query,
            preview_shifu_bid=preview_shifu_bid,
            ask_provider_config=ask_provider_config,
            requested_provider=requested_provider,
            mode=mode,
            require_llm_model=require_llm_model,
        )
        return _run_ask_preview(context)


def _shifu_route() -> ModuleType:
    """Return the route module so patched names keep affecting the preview."""
    from flaskr.service.shifu import route as shifu_route

    return shifu_route


@dataclass
class _AskPreviewContext:
    """Resolved inputs shared by the ask preview provider calls."""

    app: Flask
    query: str
    preview_shifu_bid: str
    ask_provider_config: dict[str, Any]
    requested_provider: str
    mode: str
    ask_model: Any
    ask_usage_metadata: Any
    ask_temperature: float
    messages: list[dict[str, str]]
    preview_user_id: str
    preview_scene: str
    preview_title: str
    preview_trace: Any
    preview_span: Any


def _parse_ask_preview_query(json_data: dict[str, Any]) -> str:
    query = str(json_data.get("query") or "").strip()
    if not query or len(query) > 1000:
        raise_param_error("query")
    return query


def _resolve_ask_preview_provider(
    json_data: dict[str, Any],
) -> tuple[dict[str, Any], str, str, bool]:
    """Return the provider config, requested provider, mode, and LLM need."""
    from flaskr.service.learn.ask_provider_adapters.consts import (
        ASK_PROVIDERS_WITH_LLM_SYNTHESIS,
    )
    from flaskr.service.shifu.shifu_draft_funcs import (
        ASK_PROVIDER_LLM,
        ASK_PROVIDER_MODE_PROVIDER_ONLY,
        ASK_PROVIDER_MODE_PROVIDER_THEN_LLM,
    )

    shifu_route = _shifu_route()
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
    return ask_provider_config, requested_provider, mode, require_llm_model


def _resolve_ask_preview_model(
    json_data: dict[str, Any], preview_course: object, *, require_llm_model: bool
) -> tuple[Any, Any]:
    """Return the ask model and its usage metadata for the preview."""
    shifu_route = _shifu_route()
    ask_model = (
        json_data["ask_model"]
        if "ask_model" in json_data
        else shifu_route.selection_model(preview_course, follow_up=True)
    )
    from flaskr.service.learn.api import is_live_follow_up_model

    if is_live_follow_up_model(ask_model):
        # Live preview is handled by its separate voice session controller.
        raise_param_error("ask_model")
    ask_usage_metadata = shifu_route.selection_metadata(preview_course, follow_up=True)
    if require_llm_model:
        ask_model, ask_usage_metadata = shifu_route.resolve_course_selection(
            ask_model, ask_usage_metadata
        )
    return ask_model, ask_usage_metadata


def _build_ask_preview_context(
    app: Flask,
    json_data: dict[str, Any],
    *,
    query: str,
    preview_shifu_bid: str,
    ask_provider_config: dict[str, Any],
    requested_provider: str,
    mode: str,
    require_llm_model: bool,
) -> _AskPreviewContext:
    """Load the course, resolve the model, and open the Langfuse trace."""
    shifu_route = _shifu_route()
    preview_course = shifu_route.get_latest_shifu_draft(preview_shifu_bid)
    if preview_course is None:
        raise_error("server.shifu.shifuNotFound")
    ask_model, ask_usage_metadata = _resolve_ask_preview_model(
        json_data, preview_course, require_llm_model=require_llm_model
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
            "name": shifu_route.build_langfuse_trace_name(preview_title, preview_scene),
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
    return _AskPreviewContext(
        app=app,
        query=query,
        preview_shifu_bid=preview_shifu_bid,
        ask_provider_config=ask_provider_config,
        requested_provider=requested_provider,
        mode=mode,
        ask_model=ask_model,
        ask_usage_metadata=ask_usage_metadata,
        ask_temperature=ask_temperature,
        messages=messages,
        preview_user_id=preview_user_id,
        preview_scene=preview_scene,
        preview_title=preview_title,
        preview_trace=preview_trace,
        preview_span=preview_span,
    )


def _build_ask_preview_llm_runtime(context: _AskPreviewContext) -> AskProviderRuntime:
    from flaskr.api.llm import chat_llm
    from flaskr.service.learn.ask_provider_adapters import (
        AskProviderRuntime,
        apply_knowledge_to_messages,
    )
    from flaskr.service.metering import UsageContext

    def _chat_llm_stream(
        stream_messages: list[dict[str, str]],
    ) -> Generator[Any, None, None]:
        return chat_llm(
            context.app,
            context.preview_user_id,
            context.preview_span,
            model=context.ask_model,
            usage_metadata=context.ask_usage_metadata,
            messages=stream_messages,
            generation_name="ask_provider_preview",
            temperature=context.ask_temperature,
            usage_context=UsageContext(
                user_bid=context.preview_user_id,
                shifu_bid=context.preview_shifu_bid,
                usage_scene=BILL_USAGE_SCENE_DEBUG,
                billable=1,
            ),
            usage_scene=BILL_USAGE_SCENE_DEBUG,
            billable=1,
            stream=True,
        )

    messages = context.messages
    return AskProviderRuntime(
        llm_stream_factory=lambda: _chat_llm_stream(
            apply_knowledge_to_messages(messages, "")
        ),
        llm_context_stream_factory=lambda knowledge_context: _chat_llm_stream(
            apply_knowledge_to_messages(messages, knowledge_context)
        ),
    )


def _invoke_ask_preview_provider(
    context: _AskPreviewContext,
    provider_name: str,
    runtime: AskProviderRuntime | None = None,
) -> str:
    from flaskr.service.learn.ask_provider_adapters import (
        stream_ask_provider_response,
    )
    from flaskr.service.shifu.shifu_draft_funcs import ASK_PROVIDER_LLM

    shifu_route = _shifu_route()
    chunks: list[str] = []
    provider_resp = stream_ask_provider_response(
        app=context.app,
        provider=provider_name,
        user_id=context.preview_user_id,
        user_query=context.query,
        messages=context.messages,
        provider_config=context.ask_provider_config,
        runtime=runtime,
    )
    if provider_name != ASK_PROVIDER_LLM:
        provider_resp = shifu_route.stream_provider_with_langfuse(
            provider_stream=provider_resp,
            span=context.preview_span,
            app=context.app,
            provider_name=provider_name,
            generation_name=shifu_route.build_langfuse_generation_name(
                context.preview_title,
                context.preview_scene,
                f"ask_provider_preview_{provider_name}",
            ),
            user_query=context.query,
            messages=context.messages,
            provider_config=context.ask_provider_config,
        )
    for chunk in provider_resp:
        text = getattr(chunk, "content", "")
        if isinstance(text, str) and text:
            chunks.append(text)
    return "".join(chunks).strip()


def _run_ask_preview(context: _AskPreviewContext) -> str:
    """Invoke the provider (with optional LLM fallback) and close the trace."""
    from flaskr.service.learn.ask_provider_adapters import (
        AskProviderError,
        AskProviderTimeoutError,
    )
    from flaskr.service.learn.ask_provider_adapters.consts import (
        ASK_PROVIDERS_WITH_LLM_SYNTHESIS,
    )
    from flaskr.service.shifu.shifu_draft_funcs import (
        ASK_PROVIDER_LLM,
        ASK_PROVIDER_MODE_PROVIDER_THEN_LLM,
    )

    app = context.app
    requested_provider = context.requested_provider
    mode = context.mode
    used_provider = requested_provider
    fallback_used = False
    provider_error = ""
    answer = ""

    try:
        try:
            llm_runtime = (
                _build_ask_preview_llm_runtime(context)
                if (
                    requested_provider == ASK_PROVIDER_LLM
                    or requested_provider in ASK_PROVIDERS_WITH_LLM_SYNTHESIS
                )
                else None
            )
            answer = _invoke_ask_preview_provider(
                context, requested_provider, runtime=llm_runtime
            )
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
            answer = _invoke_ask_preview_provider(
                context,
                ASK_PROVIDER_LLM,
                runtime=_build_ask_preview_llm_runtime(context),
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
        _shifu_route().finalize_langfuse_trace(
            trace=context.preview_trace,
            root_span=context.preview_span,
            trace_payload={"output": preview_output},
            root_span_payload={"output": preview_output},
        )
