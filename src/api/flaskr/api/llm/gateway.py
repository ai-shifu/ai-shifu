"""Serve raw OpenAI-compatible completions for the model gateway."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING

import litellm

if TYPE_CHECKING:
    from collections.abc import Generator

    from flask import Flask

    from flaskr.api.langfuse import (
        LangfuseObservationHandle,
    )


# Package-level names are resolved through the package module at call time so
# tests and operators that patch `flaskr.api.llm.<name>` keep affecting this code.
import flaskr.api.llm as llm_package
from flaskr.api.llm.payloads import (
    _attach_usage_output_text,
    _gateway_output_text,
    _gateway_usage_values,
)
from flaskr.service.metering import UsageContext
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PROD,
)


def _record_gateway_llm_usage(
    app: Flask,
    *,
    user_id: str,
    request_id: str,
    trace_id: str,
    provider: str,
    model: str,
    is_stream: bool,
    usage: object,
    invoke_model: str,
    fallback_input_tokens: int,
    output_capture: str,
    latency_ms: int,
    status: int,
    error_message: str,
    usage_metadata: dict[str, object] | None,
) -> None:
    values, input_cache, usage_source = _gateway_usage_values(
        usage,
        invoke_model=invoke_model,
        fallback_input_tokens=fallback_input_tokens,
        output_capture=output_capture,
    )
    metadata = _attach_usage_output_text(
        {
            **dict(usage_metadata or {}),
            "usage_source": usage_source,
            "billing_source": "model_gateway",
        },
        output_capture,
    )
    llm_package.record_llm_usage(
        app,
        UsageContext(
            user_bid=user_id,
            request_id=request_id,
            trace_id=trace_id,
            usage_scene=BILL_USAGE_SCENE_PROD,
            billable=int(status == 0),
        ),
        provider=provider,
        model=model,
        is_stream=is_stream,
        input=values["input"],
        input_cache=input_cache,
        output=values["output"],
        total=values["total"],
        latency_ms=latency_ms,
        status=status,
        error_message=error_message,
        extra=metadata,
    )


def complete_openai_chat_completion(
    app: Flask,
    *,
    user_id: str,
    span: LangfuseObservationHandle,
    model: str,
    messages: list[dict[str, object]],
    request_id: str,
    fallback_input_tokens: int,
    usage_metadata: dict[str, object] | None = None,
    **kwargs: object,
) -> dict[str, object]:
    """Return one raw OpenAI-compatible completion and persist its usage."""
    requested_model = str(model or "").strip()
    params, invoke_model, provider_key = llm_package.get_litellm_params_and_model(
        requested_model
    )
    if not params:
        llm_package.raise_error_with_args(
            "server.llm.modelNotSupported", model=requested_model
        )

    completion_kwargs = dict(kwargs)
    completion_kwargs.pop("stream", None)
    llm_package._apply_llm_max_output_tokens(
        requested_model, invoke_model, completion_kwargs
    )
    completion_kwargs = llm_package._prepare_litellm_request_kwargs(
        provider_key or "",
        invoke_model,
        params,
        completion_kwargs,
    )
    trace_id = llm_package.resolve_langfuse_trace_id(span)
    generation = span.generation(
        model=requested_model,
        input=messages,
        name="model_gateway_chat_completion",
        **llm_package.build_langfuse_observation_link(span, trace_id),
    )
    started_at = time.monotonic()
    response = None
    payload: dict[str, object] = {}
    output_capture = ""
    status = 0
    error_message = ""
    try:
        response = litellm.completion(
            model=invoke_model,
            messages=messages,
            stream=False,
            **params,
            **completion_kwargs,
        )
        if hasattr(response, "model_dump"):
            payload = response.model_dump(exclude_none=True)
        else:
            payload = dict(response)
        output_capture = _gateway_output_text(payload)
    except Exception as exc:
        status = 1
        error_message = str(exc)
        raise
    finally:
        usage = (
            (getattr(response, "usage", None) or payload.get("usage"))
            if response is not None
            else None
        )
        latency_ms = int((time.monotonic() - started_at) * 1000)
        llm_package._record_gateway_llm_usage(
            app,
            user_id=user_id,
            request_id=request_id,
            trace_id=trace_id,
            provider=provider_key or "",
            model=requested_model,
            is_stream=False,
            usage=usage,
            invoke_model=invoke_model,
            fallback_input_tokens=fallback_input_tokens,
            output_capture=output_capture,
            latency_ms=latency_ms,
            status=status,
            error_message=error_message,
            usage_metadata=usage_metadata,
        )
        with contextlib.suppress(Exception):
            generation.end(
                input=messages,
                output=output_capture,
                usage=usage,
                metadata=completion_kwargs,
            )
    return payload


def stream_openai_chat_completion(
    app: Flask,
    *,
    user_id: str,
    span: LangfuseObservationHandle,
    model: str,
    messages: list[dict[str, object]],
    request_id: str,
    fallback_input_tokens: int,
    usage_metadata: dict[str, object] | None = None,
    **kwargs: object,
) -> Generator[dict[str, object], None, None]:
    """Yield raw OpenAI-compatible chunks and persist final stream usage."""
    requested_model = str(model or "").strip()
    params, invoke_model, provider_key = llm_package.get_litellm_params_and_model(
        requested_model
    )
    if not params:
        llm_package.raise_error_with_args(
            "server.llm.modelNotSupported", model=requested_model
        )

    stream_kwargs = dict(kwargs)
    stream_kwargs.pop("stream", None)
    stream_kwargs["stream_options"] = {"include_usage": True}
    stream_kwargs = llm_package._prepare_litellm_request_kwargs(
        provider_key or "",
        invoke_model,
        params,
        stream_kwargs,
    )
    trace_id = llm_package.resolve_langfuse_trace_id(span)
    generation = span.generation(
        model=requested_model,
        input=messages,
        name="model_gateway_chat_completion",
        **llm_package.build_langfuse_observation_link(span, trace_id),
    )
    started_at = time.monotonic()
    usage = None
    output_parts: list[str] = []
    completed = False
    status = 0
    error_message = ""
    try:
        response = llm_package._iter_stream_with_precontent_retry(
            app,
            requested_model,
            invoke_model,
            messages,
            params,
            stream_kwargs,
            tool_calls_are_output=True,
        )
        for chunk in response:
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage = chunk_usage
            if hasattr(chunk, "model_dump"):
                payload = chunk.model_dump(exclude_none=True)
            else:
                payload = dict(chunk)
            if payload.get("usage") is not None:
                usage = payload["usage"]
            output_parts.append(_gateway_output_text(payload))
            yield payload
        completed = True
    except Exception as exc:
        status = 1
        error_message = str(exc)
        raise
    finally:
        output_capture = "".join(output_parts)
        if not completed:
            status = 1
        latency_ms = int((time.monotonic() - started_at) * 1000)
        llm_package._record_gateway_llm_usage(
            app,
            user_id=user_id,
            request_id=request_id,
            trace_id=trace_id,
            provider=provider_key or "",
            model=requested_model,
            is_stream=True,
            usage=usage,
            invoke_model=invoke_model,
            fallback_input_tokens=fallback_input_tokens,
            output_capture=output_capture,
            latency_ms=latency_ms,
            status=status,
            error_message=error_message,
            usage_metadata=usage_metadata,
        )
        with contextlib.suppress(Exception):
            generation.end(
                input=messages,
                output=output_capture,
                usage=usage,
                metadata=stream_kwargs,
            )
