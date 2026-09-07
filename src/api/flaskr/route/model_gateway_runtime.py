"""Coordinate gateway requests through the shared asynchronous billing flow."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from flaskr.common.cache_provider import redis_cache as cache
from flaskr.common.config import get_redis_key_prefix
from flaskr.i18n import _
from flaskr.service.billing.admission import admit_creator_usage
from flaskr.service.billing.charges import has_complete_llm_rates
from flaskr.service.common.models import AppError
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD, BILL_USAGE_TYPE_LLM
from flaskr.service.metering.models import BillUsageRecord

if TYPE_CHECKING:
    from collections.abc import Generator

    from flask import Flask

_ALLOWED_PROVIDER_OPTIONS = {
    "frequency_penalty",
    "parallel_tool_calls",
    "presence_penalty",
    "response_format",
    "seed",
    "stop",
    "temperature",
    "tool_choice",
    "tools",
    "top_p",
}
_IDEMPOTENCY_KEY_MAX_LENGTH = 90


_REQUEST_DEDUPLICATION_SECONDS = 24 * 60 * 60


class GatewayRequestError(Exception):
    """Represent a model gateway error with an HTTP contract."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        """Store the HTTP status, stable code, and safe client message."""
        message = {
            "invalid_token": _("server.modelGateway.invalid_token"),
            "missing_client_id": _("server.modelGateway.missing_client_id"),
            "client_not_allowed": _("server.modelGateway.client_not_allowed"),
            "insufficient_credits": _("server.modelGateway.insufficient_credits"),
            "model_not_available": _("server.modelGateway.model_not_available"),
            "invalid_request": _("server.modelGateway.invalid_request"),
            "provider_error": _("server.modelGateway.provider_error"),
            "request_too_large": _("server.modelGateway.request_too_large"),
            "idempotency_key_required": _(
                "server.modelGateway.idempotency_key_required"
            ),
            "model_required": _("server.modelGateway.model_required"),
            "messages_invalid": _("server.modelGateway.messages_invalid"),
            "tools_invalid": _("server.modelGateway.tools_invalid"),
            "stream_invalid": _("server.modelGateway.stream_invalid"),
            "idempotency_conflict": _("server.modelGateway.idempotency_conflict"),
        }.get(code, message)
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(slots=True, frozen=True)
class GatewayChatRequest:
    """Carry a validated request without reserving or mutating wallet credits."""

    creator_bid: str
    request_id: str
    model: str
    messages: list[dict[str, object]]
    input_tokens: int
    provider_options: dict[str, object]


def _claim_gateway_request(app: Flask, creator_bid: str, request_id: str) -> None:
    """Reject duplicates independently of billing or credit ledger entries."""
    try:
        with app.app_context():
            recorded = BillUsageRecord.query.filter(
                BillUsageRecord.user_bid == creator_bid,
                BillUsageRecord.request_id == request_id,
                BillUsageRecord.usage_type == BILL_USAGE_TYPE_LLM,
            ).first()
        key = f"{get_redis_key_prefix(app=app)}:model_gateway:request:{request_id}"
        claimed = recorded is None and cache.set(
            key, "1", nx=True, ex=_REQUEST_DEDUPLICATION_SECONDS
        )
    except Exception as error:
        app.logger.exception(
            "gateway request guard unavailable request_id=%s", request_id
        )
        raise GatewayRequestError(
            503, "gateway_unavailable", _("server.modelGateway.gateway_unavailable")
        ) from error
    if not claimed:
        raise GatewayRequestError(
            409, "idempotency_conflict", "Idempotency-Key has already been used"
        )


def prepare_gateway_chat_request(
    app: Flask,
    *,
    creator_bid: str,
    idempotency_key: str,
    payload: dict[str, object],
) -> GatewayChatRequest:
    """Validate the request and reuse course admission without a credit hold."""
    caller_key = str(idempotency_key or "").strip()
    if not caller_key or len(caller_key) > _IDEMPOTENCY_KEY_MAX_LENGTH:
        raise GatewayRequestError(
            400, "idempotency_key_required", "Idempotency-Key is required"
        )
    request_id = str(
        uuid5(NAMESPACE_URL, f"ai-shifu:model-gateway:{creator_bid}:{caller_key}")
    )
    if not isinstance(payload.get("stream", False), bool):
        raise GatewayRequestError(
            400, "stream_invalid", "stream must be a JSON boolean"
        )
    model = str(payload.get("model") or "").strip()
    if not model:
        raise GatewayRequestError(400, "model_required", "model is required")
    messages = payload.get("messages")
    if (
        not isinstance(messages, list)
        or not messages
        or len(messages) > 256
        or not all(isinstance(message, dict) for message in messages)
    ):
        raise GatewayRequestError(
            400, "messages_invalid", "messages must be a non-empty list"
        )
    tools = payload.get("tools")
    if tools is not None and (not isinstance(tools, list) or len(tools) > 128):
        raise GatewayRequestError(400, "tools_invalid", "tools must be a list")

    from flaskr.api.llm import (
        count_llm_chat_input_tokens,
        resolve_llm_max_output_tokens,
    )

    with app.app_context():
        admit_creator_usage(
            app, creator_bid=creator_bid, usage_scene=BILL_USAGE_SCENE_PROD
        )
        if not has_complete_llm_rates(model):
            raise GatewayRequestError(
                400,
                "model_not_available",
                "The model does not have complete active credit rates",
            )
    try:
        max_output_tokens = resolve_llm_max_output_tokens(
            model, payload.get("max_tokens")
        )
        input_tokens = count_llm_chat_input_tokens(
            model, messages, tools=tools if isinstance(tools, list) else None
        )
    except AppError as error:
        raise GatewayRequestError(
            400, "model_not_available", str(error.message)
        ) from error

    _claim_gateway_request(app, creator_bid, request_id)
    provider_options = {
        key: value for key, value in payload.items() if key in _ALLOWED_PROVIDER_OPTIONS
    }
    provider_options["max_tokens"] = max_output_tokens
    return GatewayChatRequest(
        creator_bid=creator_bid,
        request_id=request_id,
        model=model,
        messages=messages,
        input_tokens=input_tokens,
        provider_options=provider_options,
    )


def _trace_for_request(gateway_request: GatewayChatRequest) -> object:
    from flaskr.api.langfuse import create_trace_with_root_span, get_langfuse_client

    _trace, span = create_trace_with_root_span(
        client=get_langfuse_client(),
        trace_payload={
            "user_id": gateway_request.creator_bid,
            "name": "model_gateway_chat_completion",
            "metadata": {
                "gateway_request_id": gateway_request.request_id,
                "model": gateway_request.model,
            },
        },
        root_span_payload={
            "name": "model_gateway_chat_completion",
            "input": gateway_request.messages,
        },
    )
    return span


def complete_gateway_chat_request(
    app: Flask, gateway_request: GatewayChatRequest
) -> dict[str, object]:
    """Return model output; the shared recorder enqueues usage settlement."""
    from flaskr.api.llm import complete_openai_chat_completion

    return complete_openai_chat_completion(
        app,
        user_id=gateway_request.creator_bid,
        span=_trace_for_request(gateway_request),
        model=gateway_request.model,
        messages=gateway_request.messages,
        request_id=gateway_request.request_id,
        fallback_input_tokens=gateway_request.input_tokens,
        **gateway_request.provider_options,
    )


def stream_gateway_chat_request(
    app: Flask, gateway_request: GatewayChatRequest
) -> Generator[dict[str, object], None, None]:
    """Stream model output and finalize usage through the shared recorder."""
    from flaskr.api.llm import stream_openai_chat_completion

    stream = stream_openai_chat_completion(
        app,
        user_id=gateway_request.creator_bid,
        span=_trace_for_request(gateway_request),
        model=gateway_request.model,
        messages=gateway_request.messages,
        request_id=gateway_request.request_id,
        fallback_input_tokens=gateway_request.input_tokens,
        **gateway_request.provider_options,
    )
    try:
        yield from stream
    finally:
        with contextlib.suppress(Exception):
            stream.close()
