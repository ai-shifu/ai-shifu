"""Integrate WeChat Pay payments with legacy orders."""

from __future__ import annotations

import base64
import json
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flaskr.common.public_urls import build_wechatpay_notify_url
from flaskr.service.config import get_config

from . import register_payment_provider
from .base import (
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentProvider,
    PaymentRefundRequest,
    PaymentRefundResult,
    PaymentRequest,
)

if TYPE_CHECKING:
    from flask import Flask


class WechatPayProvider(PaymentProvider):
    """Direct WeChat Pay API v3 provider implementation."""

    channel = "wechatpay"

    def create_payment(
        self, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        """Create a payment through this provider."""
        if request.channel == "wx_pub_qr":
            return self._create_native_payment(request=request, app=app)
        if request.channel == "wx_pub":
            return self._create_jsapi_payment(request=request, app=app)
        message = f"Unsupported WeChat Pay channel: {request.channel}"
        raise RuntimeError(message)

    def create_subscription(
        self, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        """Create a recurring subscription through this provider."""
        return self.create_payment(request=request, app=app)

    def verify_webhook(
        self, *, headers: dict[str, str], raw_body: bytes | str, app: Flask
    ) -> PaymentNotificationResult:
        """Verify and decode a provider webhook payload."""
        _ = app
        raw_body_text = (
            raw_body.decode("utf-8") if isinstance(raw_body, bytes) else str(raw_body)
        )
        self._verify_notification_signature(
            headers=headers,
            raw_body=raw_body_text,
        )
        event = json.loads(raw_body_text or "{}")
        resource = self._decrypt_notification_resource(event.get("resource") or {})
        return PaymentNotificationResult(
            order_bid=str(resource.get("out_trade_no") or ""),
            status=str(resource.get("trade_state") or event.get("event_type") or ""),
            provider_payload={
                "event": event,
                "resource": resource,
            },
            charge_id=str(resource.get("transaction_id") or "") or None,
        )

    def sync_reference(
        self, *, provider_reference: str, reference_type: str, app: Flask
    ) -> PaymentNotificationResult:
        """Synchronize local state from a provider reference."""
        normalized_reference_type = str(reference_type or "").strip().lower()
        if normalized_reference_type not in {"payment", "trade", "charge"}:
            message = f"Unsupported WeChat Pay reference type: {reference_type}"
            raise RuntimeError(message)

        mch_id = _required_config("WECHATPAY_MCH_ID")
        path = f"/v3/pay/transactions/out-trade-no/{provider_reference}"
        query = urlencode({"mchid": mch_id})
        response_payload = self._request(
            method="GET",
            path=f"{path}?{query}",
            body="",
            app=app,
        )
        return PaymentNotificationResult(
            order_bid=str(response_payload.get("out_trade_no") or provider_reference),
            status="manual_sync",
            provider_payload={"trade": response_payload},
            charge_id=str(response_payload.get("transaction_id") or "") or None,
        )

    def refund_payment(
        self, *, request: PaymentRefundRequest, app: Flask
    ) -> PaymentRefundResult:
        """Refund a payment through this provider."""
        del request, app
        message = "WeChat Pay refunds are not supported"
        raise RuntimeError(message)

    def _create_native_payment(
        self, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        body = self._build_transaction_body(request)
        response_payload = self._request(
            method="POST",
            path="/v3/pay/transactions/native",
            body=json.dumps(body, ensure_ascii=False, separators=(",", ":")),
            app=app,
        )
        code_url = str(response_payload.get("code_url") or "")
        if not code_url:
            message = "WeChat Native response missing code_url"
            raise RuntimeError(message)
        return PaymentCreationResult(
            provider_reference=request.order_bid,
            raw_response=response_payload,
            extra={
                "credential": {"wx_pub_qr": code_url},
                "qr_url": code_url,
                "raw_request": body,
            },
        )

    def _create_jsapi_payment(
        self, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        open_id = str((request.extra or {}).get("open_id") or "").strip()
        if not open_id:
            message = "WeChat JSAPI payment requires open_id"
            raise RuntimeError(message)
        body = self._build_transaction_body(request)
        body["payer"] = {"openid": open_id}
        response_payload = self._request(
            method="POST",
            path="/v3/pay/transactions/jsapi",
            body=json.dumps(body, ensure_ascii=False, separators=(",", ":")),
            app=app,
        )
        prepay_id = str(response_payload.get("prepay_id") or "")
        if not prepay_id:
            message = "WeChat JSAPI response missing prepay_id"
            raise RuntimeError(message)
        jsapi_params = self._build_jsapi_params(prepay_id=prepay_id)
        return PaymentCreationResult(
            provider_reference=request.order_bid,
            raw_response=response_payload,
            extra={
                "mode": "jsapi",
                "prepay_id": prepay_id,
                "jsapi_params": jsapi_params,
                "raw_request": body,
            },
        )

    def _build_transaction_body(self, request: PaymentRequest) -> dict[str, Any]:
        notify_url = (
            str(get_config("WECHATPAY_WEBHOOK_URL", "") or "")
            or build_wechatpay_notify_url()
        )
        return {
            "appid": _wechatpay_app_id(),
            "mchid": _required_config("WECHATPAY_MCH_ID"),
            "description": (request.subject or request.order_bid)[:127],
            "out_trade_no": request.order_bid,
            "notify_url": notify_url,
            "amount": {
                "total": int(request.amount or 0),
                "currency": str(request.currency or "CNY").upper(),
            },
        }

    def _request(
        self,
        *,
        method: str,
        path: str,
        body: str,
        app: Flask,
    ) -> dict[str, Any]:
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        signature = self._sign_request(
            method=method,
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        )
        authorization = (
            "WECHATPAY2-SHA256-RSA2048 "
            f'mchid="{_required_config("WECHATPAY_MCH_ID")}",'
            f'nonce_str="{nonce}",'
            f'signature="{signature}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{_required_config("WECHATPAY_MERCHANT_SERIAL_NO")}"'
        )
        headers = {
            "Accept": "application/json",
            "Authorization": authorization,
            "Content-Type": "application/json",
            "User-Agent": "ai-shifu-wechatpay/1.0",
        }
        response = requests.request(
            method,
            f"{_wechatpay_base_url()}{path}",
            data=body.encode("utf-8") if body else None,
            headers=headers,
            timeout=10,
        )
        if response.status_code >= 400:
            app.logger.error(
                "WeChat Pay request failed status=%s body=%s",
                response.status_code,
                response.text,
            )
            raise RuntimeError(response.text or "WeChat Pay request failed")
        if not response.text:
            return {}
        return response.json()

    def _sign_request(
        self,
        *,
        method: str,
        path: str,
        timestamp: str,
        nonce: str,
        body: str,
    ) -> str:
        message = f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{body}\n"
        return _sign_with_merchant_key(message)

    def _build_jsapi_params(self, *, prepay_id: str) -> dict[str, str]:
        app_id = _wechatpay_app_id()
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        package = f"prepay_id={prepay_id}"
        pay_sign = _sign_with_merchant_key(
            f"{app_id}\n{timestamp}\n{nonce}\n{package}\n"
        )
        return {
            "appId": app_id,
            "timeStamp": timestamp,
            "nonceStr": nonce,
            "package": package,
            "signType": "RSA",
            "paySign": pay_sign,
        }

    def _verify_notification_signature(
        self,
        *,
        headers: dict[str, str],
        raw_body: str,
    ) -> None:
        normalized_headers = {
            str(key).lower(): str(value) for key, value in (headers or {}).items()
        }
        timestamp = normalized_headers.get("wechatpay-timestamp", "")
        nonce = normalized_headers.get("wechatpay-nonce", "")
        signature = normalized_headers.get("wechatpay-signature", "")
        if not timestamp or not nonce or not signature:
            error_message = "WeChat Pay signature headers missing"
            raise RuntimeError(error_message)
        public_key = _load_public_key_from_certificate()
        message = f"{timestamp}\n{nonce}\n{raw_body}\n".encode()
        public_key.verify(
            base64.b64decode(signature),
            message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

    def _decrypt_notification_resource(
        self,
        resource: dict[str, Any],
    ) -> dict[str, Any]:
        if not resource:
            error_message = "WeChat Pay notification resource missing"
            raise RuntimeError(error_message)
        algorithm = str(resource.get("algorithm") or "")
        if algorithm and algorithm != "AEAD_AES_256_GCM":
            message = f"Unsupported WeChat Pay algorithm: {algorithm}"
            raise RuntimeError(message)
        api_v3_key = _required_config("WECHATPAY_API_V3_KEY").encode("utf-8")
        aesgcm = AESGCM(api_v3_key)
        plaintext = aesgcm.decrypt(
            str(resource.get("nonce") or "").encode("utf-8"),
            base64.b64decode(str(resource.get("ciphertext") or "")),
            str(resource.get("associated_data") or "").encode("utf-8"),
        )
        return json.loads(plaintext.decode("utf-8"))


def _wechatpay_app_id() -> str:
    value = str(
        get_config("WECHATPAY_APP_ID", "") or get_config("WECHAT_APP_ID", "") or ""
    ).strip()
    if not value:
        message = "WECHATPAY_APP_ID must be configured for WeChat Pay"
        raise RuntimeError(message)
    return value


def _required_config(name: str) -> str:
    value = str(get_config(name, "") or "").strip()
    if not value:
        message = f"{name} must be configured"
        raise RuntimeError(message)
    return value


def _wechatpay_base_url() -> str:
    return str(
        get_config("WECHATPAY_BASE_URL", "https://api.mch.weixin.qq.com")
        or "https://api.mch.weixin.qq.com"
    ).rstrip("/")


def _sign_with_merchant_key(message: str) -> str:
    private_key = _load_private_key()
    signature = private_key.sign(
        message.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def _load_private_key() -> object:
    inline = str(get_config("WECHATPAY_PRIVATE_KEY", "") or "").strip()
    pem = (
        inline.encode("utf-8")
        if inline
        else Path(_required_config("WECHATPAY_PRIVATE_KEY_PATH")).read_bytes()
    )
    return serialization.load_pem_private_key(pem, password=None)


def _load_public_key_from_certificate() -> object:
    inline = str(get_config("WECHATPAY_PLATFORM_CERT", "") or "").strip()
    pem = (
        inline.encode("utf-8")
        if inline
        else Path(_required_config("WECHATPAY_PLATFORM_CERT_PATH")).read_bytes()
    )
    cert = x509.load_pem_x509_certificate(pem)
    return cert.public_key()


register_payment_provider(WechatPayProvider)
