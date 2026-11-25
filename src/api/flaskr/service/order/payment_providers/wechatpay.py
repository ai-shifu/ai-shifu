"""Integrate WeChat Pay payments with legacy orders."""

from __future__ import annotations

import base64
import datetime as dt
import json
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING
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
    PaymentCancellationResult,
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentProvider,
    PaymentRefundRequest,
    PaymentRefundResult,
    PaymentRequest,
    payment_request_expires_at,
)

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.rsa import (
        RSAPrivateKey,
        RSAPublicKey,
    )
    from flask import Flask


_PUBLIC_KEY_ID_PREFIX = "PUB_KEY_ID_"
_SIGNATURE_MAX_AGE_SECONDS = 300
# WeChat Pay rejects a time_expire closer than one minute away.
_MIN_TIME_EXPIRE_SECONDS = 60
_CHINA_TZ = dt.timezone(dt.timedelta(hours=8))


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
        """Create a one-time payment for a subscription request."""
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

    def cancel_payment(
        self,
        *,
        provider_reference: str,
        reference_type: str,
        app: Flask,
    ) -> PaymentCancellationResult:
        """Close an unpaid WeChat Pay transaction by merchant attempt ID."""
        if str(reference_type or "").lower() not in {"payment", "trade"}:
            message = f"Unsupported WeChat Pay reference type: {reference_type}"
            raise RuntimeError(message)
        path = f"/v3/pay/transactions/out-trade-no/{provider_reference}/close"
        try:
            payload = self._request(
                method="POST",
                path=path,
                body=json.dumps(
                    {"mchid": _required_config("WECHATPAY_MCH_ID")},
                    separators=(",", ":"),
                ),
                app=app,
            )
        except Exception:
            notification = self.sync_reference(
                provider_reference=provider_reference,
                reference_type=reference_type,
                app=app,
            )
            payload = dict(notification.provider_payload.get("trade") or {})
            if str(payload.get("trade_state") or "").upper() != "CLOSED":
                raise
        return PaymentCancellationResult(
            provider_reference=provider_reference,
            raw_response=payload,
            status="cancelled",
        )

    def refund_payment(
        self, *, request: PaymentRefundRequest, app: Flask
    ) -> PaymentRefundResult:
        """Raise because direct WeChat Pay refunds are unsupported."""
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

    def _build_transaction_body(self, request: PaymentRequest) -> dict[str, object]:
        notify_url = (
            str(get_config("WECHATPAY_WEBHOOK_URL", "") or "")
            or build_wechatpay_notify_url()
        )
        body: dict[str, object] = {
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
        time_expire = _time_expire(request)
        if time_expire:
            body["time_expire"] = time_expire
        return body

    def _request(
        self,
        *,
        method: str,
        path: str,
        body: str,
        app: Flask,
    ) -> dict[str, object]:
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

    def build_jsapi_params(self, *, prepay_id: str) -> dict[str, str]:
        """Build fresh client parameters for an existing JSAPI prepay ID."""
        if not prepay_id:
            message = "WeChat JSAPI payment requires prepay_id"
            raise RuntimeError(message)
        return self._build_jsapi_params(prepay_id=prepay_id)

    def _verify_notification_signature(
        self,
        *,
        headers: dict[str, str],
        raw_body: str,
    ) -> None:
        normalized_headers = {
            str(key).lower(): str(value) for key, value in (headers or {}).items()
        }
        timestamp = normalized_headers.get("wechatpay-timestamp", "").strip()
        nonce = normalized_headers.get("wechatpay-nonce", "")
        signature = normalized_headers.get("wechatpay-signature", "")
        serial = normalized_headers.get("wechatpay-serial", "").strip()
        if not timestamp or not nonce or not signature or not serial:
            error_message = "WeChat Pay signature headers missing"
            raise RuntimeError(error_message)
        _ensure_fresh_signature_timestamp(timestamp)
        public_key = _load_verification_public_key(serial)
        message = f"{timestamp}\n{nonce}\n{raw_body}\n".encode()
        public_key.verify(
            base64.b64decode(signature),
            message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

    def _decrypt_notification_resource(
        self,
        resource: dict[str, object],
    ) -> dict[str, object]:
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


def _load_private_key() -> RSAPrivateKey:
    pem = _load_pem("WECHATPAY_PRIVATE_KEY", "WECHATPAY_PRIVATE_KEY_PATH")
    return serialization.load_pem_private_key(pem, password=None)


def _ensure_fresh_signature_timestamp(timestamp: str) -> None:
    """Reject notifications whose signed timestamp is outside the replay window."""
    try:
        signed_at = int(timestamp)
    except ValueError:
        message = "WeChat Pay signature timestamp invalid"
        raise RuntimeError(message) from None
    if abs(time.time() - signed_at) > _SIGNATURE_MAX_AGE_SECONDS:
        message = "WeChat Pay signature timestamp expired"
        raise RuntimeError(message)


def _load_verification_public_key(serial: str) -> RSAPublicKey:
    """Return the WeChat Pay key that matches the notification serial header.

    Merchants verify either with the WeChat Pay public key (serial
    ``PUB_KEY_ID_...``) or with a platform certificate (serial = certificate
    serial number). A serial that matches neither configured key is rejected so
    a rotated or foreign key never verifies a payment.
    """
    if serial.upper().startswith(_PUBLIC_KEY_ID_PREFIX):
        expected_key_id = _required_config("WECHATPAY_PUBLIC_KEY_ID")
        if serial != expected_key_id:
            message = f"WeChat Pay public key ID mismatch: {serial}"
            raise RuntimeError(message)
        pem = _load_pem("WECHATPAY_PUBLIC_KEY", "WECHATPAY_PUBLIC_KEY_PATH")
        return serialization.load_pem_public_key(pem)

    certificate = _load_platform_certificate()
    if _normalize_serial(format(certificate.serial_number, "X")) != _normalize_serial(
        serial
    ):
        message = f"WeChat Pay platform certificate serial mismatch: {serial}"
        raise RuntimeError(message)
    return certificate.public_key()


def _load_platform_certificate() -> x509.Certificate:
    pem = _load_pem("WECHATPAY_PLATFORM_CERT", "WECHATPAY_PLATFORM_CERT_PATH")
    return x509.load_pem_x509_certificate(pem)


def _normalize_serial(serial: str) -> str:
    return serial.strip().upper().lstrip("0")


def _time_expire(request: PaymentRequest) -> str:
    """Format the order deadline as WeChat Pay's RFC 3339 ``time_expire``.

    Without it WeChat keeps the code payable after the order times out here.
    """
    expires_at = payment_request_expires_at(request)
    if expires_at is None:
        return ""
    earliest = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=_MIN_TIME_EXPIRE_SECONDS)
    deadline = max(expires_at, earliest).replace(microsecond=0)
    return deadline.astimezone(_CHINA_TZ).isoformat()


def _load_pem(inline_name: str, path_name: str) -> bytes:
    """Load PEM material inline first, then from the configured file path.

    Inline values may arrive from single-line environment variables whose
    newlines are escaped as a backslash plus ``n``; those are restored before
    parsing.
    """
    inline = str(get_config(inline_name, "") or "").strip()
    if inline:
        return inline.replace("\\n", "\n").encode("utf-8")
    return Path(_required_config(path_name)).read_bytes()


register_payment_provider(WechatPayProvider)
