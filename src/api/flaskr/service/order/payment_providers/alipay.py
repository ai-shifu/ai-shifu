from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs

from flask import Flask

from flaskr.common.public_urls import build_alipay_notify_url
from flaskr.service.config import get_config

from . import register_payment_provider
from .base import (
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentProvider,
    PaymentRefundRequest,
    PaymentRefundResult,
)
from .base import PaymentRequest


class AlipayProvider(PaymentProvider):
    """Direct Alipay OpenAPI provider implementation."""

    channel = "alipay"

    def __init__(self) -> None:
        self._client: Any | None = None

    def create_payment(
        self, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        if request.channel != "alipay_qr":
            raise RuntimeError(f"Unsupported Alipay channel: {request.channel}")

        client = self._ensure_client(app)
        sdk = self._load_sdk(app)
        biz_model = sdk["AlipayTradePrecreateModel"]()
        biz_model.out_trade_no = request.order_bid
        biz_model.total_amount = _format_cny_amount(request.amount)
        biz_model.subject = request.subject or request.order_bid
        biz_model.body = request.body or request.subject or request.order_bid
        biz_model.timeout_express = str(
            (request.extra or {}).get("timeout_express") or "15m"
        )

        precreate_request = sdk["AlipayTradePrecreateRequest"](biz_model=biz_model)
        notify_url = build_alipay_notify_url()
        precreate_request.notify_url = notify_url

        raw_response = client.execute(precreate_request)
        response_payload = _parse_alipay_response(
            raw_response,
            "alipay_trade_precreate_response",
        )
        code = str(response_payload.get("code") or "")
        if code and code != "10000":
            raise RuntimeError(
                response_payload.get("sub_msg")
                or response_payload.get("msg")
                or "Alipay precreate failed"
            )

        qr_code = str(response_payload.get("qr_code") or "")
        if not qr_code:
            raise RuntimeError("Alipay precreate response missing qr_code")

        provider_payload = {
            "request": {
                "out_trade_no": request.order_bid,
                "total_amount": biz_model.total_amount,
                "subject": biz_model.subject,
                "body": biz_model.body,
                "timeout_express": biz_model.timeout_express,
                "notify_url": notify_url,
            },
            "response": response_payload,
        }
        return PaymentCreationResult(
            provider_reference=request.order_bid,
            raw_response=response_payload,
            extra={
                "credential": {"alipay_qr": qr_code},
                "qr_url": qr_code,
                "raw_request": provider_payload["request"],
            },
        )

    def create_subscription(
        self, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        return self.create_payment(request=request, app=app)

    def verify_webhook(
        self, *, headers: Dict[str, str], raw_body: bytes | str, app: Flask
    ) -> PaymentNotificationResult:
        del headers
        payload = _parse_form_payload(raw_body)
        if not self._verify_notification_signature(payload, app):
            raise RuntimeError("Alipay notify signature verification failed")
        return self._notification_from_payload(payload)

    def handle_notification(
        self, *, payload: Dict[str, Any], app: Flask
    ) -> PaymentNotificationResult:
        normalized_payload = dict(payload or {})
        if "raw_body" in normalized_payload:
            return self.verify_webhook(
                headers=normalized_payload.get("headers", {}) or {},
                raw_body=normalized_payload.get("raw_body", ""),
                app=app,
            )
        if not self._verify_notification_signature(normalized_payload, app):
            raise RuntimeError("Alipay notify signature verification failed")
        return self._notification_from_payload(normalized_payload)

    def sync_reference(
        self, *, provider_reference: str, reference_type: str, app: Flask
    ) -> PaymentNotificationResult:
        normalized_reference_type = str(reference_type or "").strip().lower()
        if normalized_reference_type not in {"payment", "trade", "charge"}:
            raise RuntimeError(f"Unsupported Alipay reference type: {reference_type}")

        client = self._ensure_client(app)
        sdk = self._load_sdk(app)
        biz_model = sdk["AlipayTradeQueryModel"]()
        biz_model.out_trade_no = provider_reference
        query_request = sdk["AlipayTradeQueryRequest"](biz_model=biz_model)
        raw_response = client.execute(query_request)
        response_payload = _parse_alipay_response(
            raw_response,
            "alipay_trade_query_response",
        )
        return PaymentNotificationResult(
            order_bid=str(response_payload.get("out_trade_no") or provider_reference),
            status="manual_sync",
            provider_payload={"trade": response_payload},
            charge_id=str(response_payload.get("trade_no") or "") or None,
        )

    def refund_payment(
        self, *, request: PaymentRefundRequest, app: Flask
    ) -> PaymentRefundResult:
        del request, app
        raise RuntimeError("Alipay refunds are not supported")

    def _ensure_client(self, app: Flask) -> Any:
        if self._client is not None:
            return self._client
        sdk = self._load_sdk(app)
        app_id = str(get_config("ALIPAY_APP_ID", "") or "").strip()
        if not app_id:
            raise RuntimeError("ALIPAY_APP_ID must be configured for Alipay")
        private_key = _read_required_key("ALIPAY_APP_PRIVATE_KEY_PATH")
        alipay_public_key = _read_required_key("ALIPAY_PUBLIC_KEY_PATH")

        client_config = sdk["AlipayClientConfig"]()
        client_config.server_url = str(
            get_config("ALIPAY_GATEWAY_URL", "")
            or "https://openapi.alipay.com/gateway.do"
        )
        client_config.app_id = app_id
        client_config.app_private_key = private_key
        client_config.alipay_public_key = alipay_public_key
        self._client = sdk["DefaultAlipayClient"](
            alipay_client_config=client_config,
            logger=app.logger,
        )
        return self._client

    def _load_sdk(self, app: Flask) -> dict[str, Any]:
        try:
            from alipay.aop.api.AlipayClientConfig import AlipayClientConfig
            from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient
            from alipay.aop.api.domain.AlipayTradePrecreateModel import (
                AlipayTradePrecreateModel,
            )
            from alipay.aop.api.domain.AlipayTradeQueryModel import (
                AlipayTradeQueryModel,
            )
            from alipay.aop.api.request.AlipayTradePrecreateRequest import (
                AlipayTradePrecreateRequest,
            )
            from alipay.aop.api.request.AlipayTradeQueryRequest import (
                AlipayTradeQueryRequest,
            )
        except Exception as exc:  # pragma: no cover - depends on runtime package
            app.logger.error("Alipay SDK is not available: %s", exc)
            raise RuntimeError("alipay-sdk-python is required for Alipay") from exc

        return {
            "AlipayClientConfig": AlipayClientConfig,
            "DefaultAlipayClient": DefaultAlipayClient,
            "AlipayTradePrecreateModel": AlipayTradePrecreateModel,
            "AlipayTradeQueryModel": AlipayTradeQueryModel,
            "AlipayTradePrecreateRequest": AlipayTradePrecreateRequest,
            "AlipayTradeQueryRequest": AlipayTradeQueryRequest,
        }

    def _verify_notification_signature(
        self,
        payload: Dict[str, Any],
        app: Flask,
    ) -> bool:
        self._load_sdk(app)
        try:
            from alipay.aop.api.util.SignatureUtils import get_sign_content
            from alipay.aop.api.util.SignatureUtils import verify_with_rsa
        except Exception as exc:  # pragma: no cover - depends on runtime package
            app.logger.error("Alipay signature utility is not available: %s", exc)
            raise RuntimeError("Alipay signature utility is required") from exc

        public_key = _read_required_key("ALIPAY_PUBLIC_KEY_PATH")
        sign = str(payload.get("sign") or "")
        charset = str(payload.get("charset") or "utf-8")
        if not sign:
            return False
        signed_items = {
            str(key): value
            for key, value in payload.items()
            if key not in {"sign", "sign_type"} and value is not None
        }
        signed_content = get_sign_content(signed_items).encode(charset)
        return bool(verify_with_rsa(public_key, signed_content, sign))

    def _notification_from_payload(
        self,
        payload: Dict[str, Any],
    ) -> PaymentNotificationResult:
        return PaymentNotificationResult(
            order_bid=str(payload.get("out_trade_no") or ""),
            status=str(payload.get("trade_status") or ""),
            provider_payload=dict(payload),
            charge_id=str(payload.get("trade_no") or "") or None,
        )


def _read_required_key(config_name: str) -> str:
    key_path = str(get_config(config_name, "") or "").strip()
    if not key_path:
        raise RuntimeError(f"{config_name} must be configured")
    path = Path(key_path)
    if not path.exists():
        raise FileNotFoundError(key_path)
    return path.read_text(encoding="utf-8").strip()


def _format_cny_amount(amount: int) -> str:
    yuan = (Decimal(int(amount or 0)) / Decimal(100)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    return format(yuan, "f")


def _parse_alipay_response(raw_response: Any, response_key: str) -> Dict[str, Any]:
    if hasattr(raw_response, "to_dict"):
        raw_response = raw_response.to_dict()
    if isinstance(raw_response, str):
        raw_response = json.loads(raw_response)
    if not isinstance(raw_response, dict):
        raise RuntimeError("Invalid Alipay response")
    nested = raw_response.get(response_key)
    if isinstance(nested, dict):
        return nested
    return raw_response


def _parse_form_payload(raw_body: bytes | str) -> Dict[str, Any]:
    if isinstance(raw_body, bytes):
        raw_body = raw_body.decode("utf-8")
    raw_body = str(raw_body or "")
    parsed = parse_qs(raw_body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


register_payment_provider(AlipayProvider)
