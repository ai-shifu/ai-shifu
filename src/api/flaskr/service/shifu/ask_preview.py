from __future__ import annotations

import uuid

from flask import Flask

from flaskr.api import llm as llm_api
from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
)
from flaskr.common.config import get_config
from flaskr.service.common.models import raise_param_error
from flaskr.service.learn import ask_provider_adapters
from flaskr.service.learn.ask_provider_langfuse import stream_provider_with_langfuse
from flaskr.service.learn.langfuse_naming import (
    build_langfuse_generation_name,
    build_langfuse_span_name,
    build_langfuse_trace_name,
)
from flaskr.service.metering import UsageContext
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.service.shifu.route_support import parse_ask_provider_config
from flaskr.service.shifu.shifu_draft_funcs import (
    ASK_PROVIDER_LLM,
    ASK_PROVIDER_MODE_PROVIDER_ONLY,
    ASK_PROVIDER_MODE_PROVIDER_THEN_LLM,
    normalize_ask_provider_config,
)


def preview_ask_response(
    app: Flask,
    json_data: dict | None,
    *,
    request_user_id: str = "",
    request_user_is_creator: bool = False,
) -> dict[str, object]:
    payload = json_data or {}

    query = str(payload.get("query") or "").strip()
    if not query or len(query) > 1000:
        raise_param_error("query")

    raw_ask_provider_config = payload.get("ask_provider_config")
    if raw_ask_provider_config is None and any(
        key in payload for key in ("provider", "mode", "config")
    ):
        raw_ask_provider_config = {
            "provider": payload.get("provider"),
            "mode": payload.get("mode"),
            "config": payload.get("config"),
        }
    ask_provider_config = parse_ask_provider_config(raw_ask_provider_config or {})
    if ask_provider_config is None:
        ask_provider_config = normalize_ask_provider_config({})

    requested_provider = ask_provider_config.get("provider", ASK_PROVIDER_LLM)
    mode = ask_provider_config.get("mode", ASK_PROVIDER_MODE_PROVIDER_ONLY)
    require_llm_model = (
        requested_provider == ASK_PROVIDER_LLM
        or mode == ASK_PROVIDER_MODE_PROVIDER_THEN_LLM
    )

    ask_model = str(payload.get("ask_model") or "").strip()
    if not ask_model and require_llm_model:
        ask_model = str(get_config("DEFAULT_LLM_MODEL") or "").strip()
    if not ask_model and require_llm_model:
        raise_param_error("ask_model")

    ask_temperature = payload.get("ask_temperature", 0.3)
    try:
        ask_temperature = float(ask_temperature)
    except (TypeError, ValueError):
        raise_param_error("ask_temperature")
    if ask_temperature < 0 or ask_temperature > 2:
        raise_param_error("ask_temperature")

    ask_system_prompt = str(payload.get("ask_system_prompt") or "").strip()

    messages: list[dict[str, str]] = []
    if ask_system_prompt:
        messages.append({"role": "system", "content": ask_system_prompt})
    messages.append({"role": "user", "content": query})

    preview_user_id = (
        str(request_user_id).strip() or f"ask-preview-{uuid.uuid4().hex[:8]}"
    )
    preview_scene = "ask_provider_preview"
    preview_title = "ask_provider_preview"
    preview_trace, preview_span = create_trace_with_root_span(
        client=get_langfuse_client(),
        trace_payload={
            "user_id": preview_user_id,
            "input": query,
            "name": build_langfuse_trace_name(preview_title, preview_scene),
            "metadata": {
                "scene": preview_scene,
                "requested_provider": requested_provider,
                "mode": mode,
            },
        },
        root_span_payload={
            "name": build_langfuse_span_name(
                preview_title,
                preview_scene,
                "ask_provider_preview",
            ),
            "input": query,
        },
    )

    def _build_llm_runtime() -> ask_provider_adapters.AskProviderRuntime:
        runtime_billable = 1 if request_user_is_creator else 0
        return ask_provider_adapters.AskProviderRuntime(
            llm_stream_factory=lambda: llm_api.chat_llm(
                app,
                preview_user_id,
                preview_span,
                model=ask_model,
                messages=messages,
                generation_name="ask_provider_preview",
                temperature=ask_temperature,
                usage_context=UsageContext(
                    user_bid=preview_user_id,
                    usage_scene=BILL_USAGE_SCENE_DEBUG,
                    billable=runtime_billable,
                ),
                usage_scene=BILL_USAGE_SCENE_DEBUG,
                billable=runtime_billable,
                stream=True,
            )
        )

    def _invoke_provider(
        provider_name: str,
        runtime: ask_provider_adapters.AskProviderRuntime | None = None,
    ) -> str:
        chunks: list[str] = []
        provider_resp = ask_provider_adapters.stream_ask_provider_response(
            app=app,
            provider=provider_name,
            user_id=preview_user_id,
            user_query=query,
            messages=messages,
            provider_config=ask_provider_config,
            runtime=runtime,
        )
        if provider_name != ASK_PROVIDER_LLM:
            provider_resp = stream_provider_with_langfuse(
                provider_stream=provider_resp,
                span=preview_span,
                provider_name=provider_name,
                generation_name=build_langfuse_generation_name(
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
                _build_llm_runtime() if requested_provider == ASK_PROVIDER_LLM else None
            )
            answer = _invoke_provider(requested_provider, runtime=llm_runtime)
        except (
            ask_provider_adapters.AskProviderError,
            ask_provider_adapters.AskProviderTimeoutError,
        ) as error:
            provider_error = str(error)
            if (
                mode != ASK_PROVIDER_MODE_PROVIDER_THEN_LLM
                or requested_provider == ASK_PROVIDER_LLM
            ):
                raise_param_error(provider_error)
            used_provider = ASK_PROVIDER_LLM
            fallback_used = True
            answer = _invoke_provider(ASK_PROVIDER_LLM, runtime=_build_llm_runtime())

        if not answer:
            raise_param_error("ask preview returned empty response")

        return {
            "answer": answer,
            "provider": used_provider,
            "requested_provider": requested_provider,
            "mode": mode,
            "fallback_used": fallback_used,
            "provider_error": provider_error,
        }
    finally:
        preview_output = answer or provider_error
        finalize_langfuse_trace(
            trace=preview_trace,
            root_span=preview_span,
            trace_payload={"output": preview_output},
            root_span_payload={"output": preview_output},
        )
