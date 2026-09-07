"""Expose the AI-Shifu account-backed OpenAI-compatible model gateway."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from flask import Flask, Response, jsonify, request, stream_with_context
from werkzeug.exceptions import RequestEntityTooLarge

from flaskr.common.public_urls import build_public_url
from flaskr.i18n import _
from flaskr.service.billing.charges import has_complete_llm_rates
from flaskr.service.billing.models import CreditWallet
from flaskr.service.billing.primitives import credit_decimal_to_number
from flaskr.service.billing.wallets import calculate_credit_wallet_snapshot_values
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user.common import validate_user

from .common import bypass_token_validation, make_common_response
from .model_gateway_runtime import (
    GatewayRequestError,
    complete_gateway_chat_request,
    prepare_gateway_chat_request,
    stream_gateway_chat_request,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from flaskr.service.common.dtos import UserInfo

_DEFAULT_MODEL_ALIAS = "ai-shifu-default"


def _bearer_token() -> str:
    authorization = str(request.headers.get("Authorization") or "").strip()
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token.strip():
        raise GatewayRequestError(
            401,
            "invalid_token",
            "Authorization Bearer token is required",
        )
    return token.strip()


def _gateway_user(app: Flask) -> UserInfo:
    try:
        return validate_user(app, _bearer_token())
    except (AppError, GatewayRequestError) as error:
        if isinstance(error, GatewayRequestError):
            raise
        raise GatewayRequestError(
            401, "invalid_token", "The access token is invalid"
        ) from error


def _validate_gateway_client(app: Flask) -> None:
    """Require an explicitly admitted client ID before model or credit work."""
    client_id = request.headers.get("X-AI-Shifu-Client-ID", "").strip()
    if not client_id:
        raise GatewayRequestError(
            400, "missing_client_id", "X-AI-Shifu-Client-ID header is required"
        )
    allowed_clients = app.config.get("MODEL_GATEWAY_CLIENT_ALLOWLIST", [])
    if not isinstance(allowed_clients, list) or client_id not in allowed_clients:
        raise GatewayRequestError(
            403,
            "client_not_allowed",
            "The client is not allowed to access gateway models",
        )


def _account_payload(app: Flask, user: UserInfo) -> dict[str, object]:
    with app.app_context():
        wallet = (
            CreditWallet.query.filter(
                CreditWallet.deleted == 0,
                CreditWallet.creator_bid == str(user.user_id or ""),
            )
            .order_by(CreditWallet.id.desc())
            .first()
        )
        if wallet is None:
            raise GatewayRequestError(
                402,
                "insufficient_credits",
                "The account does not have an available credit wallet",
            )
        available, reserved = calculate_credit_wallet_snapshot_values(wallet)
    return {
        "user": {
            "user_id": str(user.user_id or ""),
            "name": str(user.name or ""),
            "language": str(user.language or ""),
        },
        "wallet": {
            "available_credits": credit_decimal_to_number(available),
            "reserved_credits": credit_decimal_to_number(reserved),
        },
        "billing_url": build_public_url("/admin/billing"),
    }


def _gateway_models(app: Flask) -> list[dict[str, object]]:
    from flaskr.api.llm import get_current_models

    rated = [
        model
        for model in get_current_models(app)
        if model.get("credit_multiplier") is not None
        and has_complete_llm_rates(str(model.get("model") or ""))
    ]
    data = [
        {
            "id": model["model"],
            "object": "model",
            "owned_by": "ai-shifu",
            "display_name": model.get("display_name") or model["model"],
            "credit_multiplier": model.get("credit_multiplier"),
        }
        for model in rated
    ]
    default = next((model for model in rated if model.get("is_default")), None)
    if default is not None:
        data.insert(
            0,
            {
                "id": _DEFAULT_MODEL_ALIAS,
                "object": "model",
                "owned_by": "ai-shifu",
                "display_name": "AI-Shifu Default",
                "credit_multiplier": default.get("credit_multiplier"),
                "resolved_model": default.get("model"),
            },
        )
    return data


def _resolve_model_alias(app: Flask, payload: dict[str, object]) -> dict[str, object]:
    if str(payload.get("model") or "").strip() != _DEFAULT_MODEL_ALIAS:
        return payload
    default = next(
        (
            model
            for model in _gateway_models(app)
            if model.get("id") == _DEFAULT_MODEL_ALIAS
        ),
        None,
    )
    resolved = str((default or {}).get("resolved_model") or "")
    if not resolved:
        raise GatewayRequestError(
            400,
            "model_not_available",
            "No rated default model is available",
        )
    return {**payload, "model": resolved}


def _error_response(error: GatewayRequestError) -> tuple[Response, int]:
    body: dict[str, object] = {
        "error": {
            "type": "invalid_request_error"
            if error.status_code < 500
            else "server_error",
            "code": error.code,
            "message": error.message,
        }
    }
    if error.status_code == 402:
        body["error"]["billing_url"] = build_public_url("/admin/billing")
    return jsonify(body), error.status_code


def _app_error(error: AppError) -> GatewayRequestError:
    if error.code == ERROR_CODE.get("server.billing.creditInsufficient"):
        return GatewayRequestError(402, "insufficient_credits", str(error.message))
    if error.code == ERROR_CODE.get("server.billing.subscriptionInactive"):
        return GatewayRequestError(402, "subscription_inactive", str(error.message))
    return GatewayRequestError(400, "invalid_request", str(error.message))


def register_model_gateway_handler(
    app: Flask,
    path_prefix: str = "/api/gateway",
) -> Flask:
    """Register account and OpenAI-compatible gateway routes."""

    @app.route(path_prefix + "/account", methods=["GET"])
    @bypass_token_validation
    def model_gateway_account() -> tuple[Response, int] | str:
        """Return the current account and credit snapshot."""
        try:
            return make_common_response(_account_payload(app, _gateway_user(app)))
        except GatewayRequestError as error:
            return _error_response(error)

    @app.route(path_prefix + "/v1/models", methods=["GET"])
    @bypass_token_validation
    def model_gateway_models() -> tuple[Response, int] | Response:
        """Return models with complete active AI-Shifu credit rates."""
        try:
            _gateway_user(app)
            _validate_gateway_client(app)
            return jsonify({"object": "list", "data": _gateway_models(app)})
        except GatewayRequestError as error:
            return _error_response(error)

    @app.route(path_prefix + "/v1/chat/completions", methods=["POST"])
    @bypass_token_validation
    def model_gateway_chat() -> tuple[Response, int] | Response:
        """Run a chat completion with shared admission and asynchronous billing."""
        try:
            user = _gateway_user(app)
            _validate_gateway_client(app)
            request.max_content_length = min(
                request.max_content_length or 1024 * 1024, 1024 * 1024
            )
            raw_payload = request.get_json(silent=True)
            payload = raw_payload if isinstance(raw_payload, dict) else {}
            payload = _resolve_model_alias(app, payload)
            gateway_request = prepare_gateway_chat_request(
                app,
                creator_bid=str(user.user_id or ""),
                idempotency_key=str(request.headers.get("Idempotency-Key") or ""),
                payload=payload,
            )
        except RequestEntityTooLarge:
            return _error_response(
                GatewayRequestError(
                    413, "request_too_large", "Request body exceeds the gateway limit"
                )
            )
        except GatewayRequestError as error:
            return _error_response(error)
        except AppError as error:
            return _error_response(_app_error(error))

        if not payload.get("stream", False):
            try:
                response_payload = complete_gateway_chat_request(app, gateway_request)
            except AppError as error:
                return _error_response(_app_error(error))
            except Exception:
                app.logger.exception(
                    "model gateway completion failed request_id=%s",
                    gateway_request.request_id,
                )
                return _error_response(
                    GatewayRequestError(
                        502, "provider_error", "The model request failed"
                    )
                )
            return jsonify(response_payload)

        @stream_with_context
        def events() -> Generator[str, None, None]:
            try:
                for chunk in stream_gateway_chat_request(app, gateway_request):
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            except Exception:
                app.logger.exception(
                    "model gateway stream failed request_id=%s",
                    gateway_request.request_id,
                )
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "error": {
                                "type": "server_error",
                                "code": "provider_error",
                                "message": _("server.modelGateway.provider_error"),
                            }
                        }
                    )
                    + "\n\n"
                )
            yield "data: [DONE]\n\n"

        return Response(
            events(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-AI-Shifu-Request-ID": gateway_request.request_id,
            },
        )

    return app
