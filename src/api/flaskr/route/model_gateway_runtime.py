"""Coordinate strictly metered OpenAI-compatible model gateway requests."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from flaskr.service.billing.operation_credits import (
    capture_metered_operation_credits,
    capture_reserved_operation_credits,
    estimate_llm_operation_credits,
    release_reserved_operation_credits,
    reserve_operation_credits,
)
from flaskr.service.common.models import AppError
from flaskr.util.uuid import generate_id

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


class GatewayRequestError(Exception):
    """Represent a model gateway error with an HTTP contract."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        """Store the HTTP status, stable code, and safe client message."""
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(slots=True, frozen=True)
class GatewayChatReservation:
    """Carry one request's credit hold into its provider lifecycle."""

    creator_bid: str
    request_id: str
    model: str
    messages: list[dict[str, object]]
    input_tokens: int
    max_output_tokens: int
    reservation_bid: str
    usage_bid: str
    provider_options: dict[str, object]


def prepare_gateway_chat_request(
    app: Flask,
    *,
    creator_bid: str,
    idempotency_key: str,
    payload: dict[str, object],
) -> GatewayChatReservation:
    """Validate, rate, and reserve one model gateway request."""
    request_id = str(idempotency_key or "").strip()
    if not request_id or len(request_id) > _IDEMPOTENCY_KEY_MAX_LENGTH:
        raise GatewayRequestError(
            400, "idempotency_key_required", "Idempotency-Key is required"
        )

    model = str(payload.get("model") or "").strip()
    if not model:
        raise GatewayRequestError(400, "model_required", "model is required")
    messages = payload.get("messages")
    if (
        not isinstance(messages, list)
        or not messages
        or not all(isinstance(message, dict) for message in messages)
    ):
        raise GatewayRequestError(
            400, "messages_invalid", "messages must be a non-empty list"
        )
    tools = payload.get("tools")
    if tools is not None and not isinstance(tools, list):
        raise GatewayRequestError(400, "tools_invalid", "tools must be a list")

    from flaskr.api.llm import (
        count_llm_chat_input_tokens,
        resolve_llm_max_output_tokens,
    )

    try:
        max_output_tokens = resolve_llm_max_output_tokens(
            model,
            payload.get("max_tokens"),
        )
        input_tokens = count_llm_chat_input_tokens(
            model,
            messages,
            tools=tools if isinstance(tools, list) else None,
        )
    except AppError as error:
        raise GatewayRequestError(
            400, "model_not_available", str(error.message)
        ) from error

    estimate = estimate_llm_operation_credits(
        app,
        model=model,
        input_tokens=input_tokens,
        max_output_tokens=max_output_tokens,
    )
    if estimate.status != "rated" or estimate.consumed_credits <= 0:
        raise GatewayRequestError(
            400,
            "model_not_available",
            "The model does not have complete active credit rates",
        )

    reservation = reserve_operation_credits(
        app,
        creator_bid=creator_bid,
        amount=estimate.consumed_credits,
        operation_type="model_gateway_llm",
        operation_bid=request_id,
        metadata={
            "model": model,
            "input_tokens": input_tokens,
            "max_output_tokens": max_output_tokens,
        },
    )
    if reservation.status != "reserved":
        raise GatewayRequestError(
            409,
            "idempotency_conflict",
            "Idempotency-Key has already been used",
        )

    provider_options = {
        key: value for key, value in payload.items() if key in _ALLOWED_PROVIDER_OPTIONS
    }
    provider_options["max_tokens"] = max_output_tokens
    return GatewayChatReservation(
        creator_bid=creator_bid,
        request_id=request_id,
        model=model,
        messages=messages,
        input_tokens=input_tokens,
        max_output_tokens=max_output_tokens,
        reservation_bid=reservation.reservation_bid,
        usage_bid=generate_id(app),
        provider_options=provider_options,
    )


def _trace_for_request(reservation: GatewayChatReservation) -> object:
    from flaskr.api.langfuse import create_trace_with_root_span, get_langfuse_client

    _trace, span = create_trace_with_root_span(
        client=get_langfuse_client(),
        trace_payload={
            "user_id": reservation.creator_bid,
            "name": "model_gateway_chat_completion",
            "metadata": {
                "gateway_request_id": reservation.request_id,
                "model": reservation.model,
            },
        },
        root_span_payload={
            "name": "model_gateway_chat_completion",
            "input": reservation.messages,
        },
    )
    return span


def _capture_completed(app: Flask, reservation: GatewayChatReservation) -> None:
    try:
        capture_metered_operation_credits(
            app,
            reservation_bid=reservation.reservation_bid,
            usage_bid=reservation.usage_bid,
            metadata={"gateway_request_id": reservation.request_id},
        )
    except AppError:
        capture_reserved_operation_credits(
            app,
            reservation_bid=reservation.reservation_bid,
            usage_bid=reservation.usage_bid,
            metadata={
                "gateway_request_id": reservation.request_id,
                "estimated_usage": True,
                "reason": "exact_capture_failed",
            },
        )


def complete_gateway_chat_request(
    app: Flask,
    reservation: GatewayChatReservation,
) -> dict[str, object]:
    """Run one non-streaming request and resolve its credit hold."""
    from flaskr.api.llm import complete_openai_chat_completion

    try:
        payload = complete_openai_chat_completion(
            app,
            user_id=reservation.creator_bid,
            span=_trace_for_request(reservation),
            usage_bid=reservation.usage_bid,
            model=reservation.model,
            messages=reservation.messages,
            request_id=reservation.request_id,
            fallback_input_tokens=reservation.input_tokens,
            usage_metadata={
                "reservation_bid": reservation.reservation_bid,
                "gateway_request_id": reservation.request_id,
                "metering_mode": "strict",
            },
            **reservation.provider_options,
        )
    except Exception:
        release_reserved_operation_credits(
            app,
            reservation_bid=reservation.reservation_bid,
            reason="provider_failed_before_response",
        )
        raise
    _capture_completed(app, reservation)
    return payload


def stream_gateway_chat_request(
    app: Flask,
    reservation: GatewayChatReservation,
) -> Generator[dict[str, object], None, None]:
    """Stream one request and always resolve its credit hold exactly once."""
    from flaskr.api.llm import stream_openai_chat_completion

    stream = None
    output_started = False
    completed = False
    try:
        stream = stream_openai_chat_completion(
            app,
            user_id=reservation.creator_bid,
            span=_trace_for_request(reservation),
            usage_bid=reservation.usage_bid,
            model=reservation.model,
            messages=reservation.messages,
            request_id=reservation.request_id,
            fallback_input_tokens=reservation.input_tokens,
            usage_metadata={
                "reservation_bid": reservation.reservation_bid,
                "gateway_request_id": reservation.request_id,
                "metering_mode": "strict",
            },
            **reservation.provider_options,
        )
        for chunk in stream:
            output_started = output_started or _chunk_has_output(chunk)
            yield chunk
        completed = True
    finally:
        if stream is not None:
            with contextlib.suppress(Exception):
                stream.close()
        if completed or output_started:
            _capture_completed(app, reservation)
        else:
            release_reserved_operation_credits(
                app,
                reservation_bid=reservation.reservation_bid,
                reason="stream_failed_before_output",
            )


def _chunk_has_output(chunk: dict[str, object]) -> bool:
    choices = chunk.get("choices")
    if not isinstance(choices, list):
        return False
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta")
        if isinstance(delta, dict) and (
            delta.get("content") or delta.get("tool_calls")
        ):
            return True
    return False
