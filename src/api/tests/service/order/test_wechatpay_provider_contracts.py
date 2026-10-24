"""Exercise native WeChat payment transport and cryptographic boundaries offline."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from cryptography import x509
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.x509.oid import NameOID
from flask import Flask
from flaskr.service.order.payment_providers import wechatpay
from flaskr.service.order.payment_providers.base import (
    PaymentRefundRequest,
    PaymentRequest,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(scope="module")
def merchant_material() -> tuple[rsa.RSAPrivateKey, str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "payment.test")])
    issued = datetime(2025, 1, 1, tzinfo=UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(issued)
        .not_valid_after(issued + timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )
    return (
        key,
        private_pem,
        certificate.public_bytes(serialization.Encoding.PEM).decode(),
    )


@pytest.fixture
def wechat_config(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    config = {
        "WECHATPAY_APP_ID": "wx-test-app",
        "WECHATPAY_MCH_ID": "merchant-test",
        "WECHATPAY_MERCHANT_SERIAL_NO": "serial-test",
        "WECHATPAY_WEBHOOK_URL": "https://payments.example.test/wechat",
        "WECHATPAY_API_V3_KEY": "0123456789abcdef0123456789abcdef",
    }
    monkeypatch.setattr(
        wechatpay, "get_config", lambda key, default="": config.get(key, default)
    )
    return config


def _payment_request(channel: str = "wx_pub_qr", **overrides: object) -> PaymentRequest:
    values = {
        "order_bid": "attempt-test",
        "user_bid": "user-test",
        "shifu_bid": "course-test",
        "amount": 12345,
        "currency": "cny",
        "subject": "Course enrollment",
        "body": "Course enrollment",
        "client_ip": "127.0.0.1",
        "channel": channel,
    }
    return PaymentRequest(**(values | overrides))


@pytest.mark.parametrize("channel", ["wx_pub_qr", "wx_pub"])
def test_create_payment_sends_exact_amount_and_returns_client_credentials(
    channel: str,
    wechat_config: dict[str, str],
    merchant_material: tuple[rsa.RSAPrivateKey, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wechat_config["WECHATPAY_PRIVATE_KEY"] = merchant_material[1]
    provider = wechatpay.WechatPayProvider()
    request_call = Mock(
        return_value={"code_url": "weixin://test-code", "prepay_id": "prepay-test"}
    )
    monkeypatch.setattr(provider, "_request", request_call)
    request = _payment_request(
        channel, subject="课" * 130, extra={"open_id": " open-test "}
    )

    result = provider.create_subscription(request=request, app=Flask(__name__))

    sent = request_call.call_args.kwargs
    assert sent["method"] == "POST"
    assert (
        sent["path"]
        == f"/v3/pay/transactions/{'native' if channel == 'wx_pub_qr' else 'jsapi'}"
    )
    body = json.loads(sent["body"])
    assert body["amount"] == {"total": 12345, "currency": "CNY"}
    assert body["out_trade_no"] == "attempt-test"
    assert body["description"] == "课" * 127
    assert body["notify_url"] == wechat_config["WECHATPAY_WEBHOOK_URL"]
    assert result.provider_reference == "attempt-test"
    assert result.extra["raw_request"] == body
    if channel == "wx_pub_qr":
        assert result.extra["credential"] == {"wx_pub_qr": "weixin://test-code"}
        assert result.extra["qr_url"] == "weixin://test-code"
    else:
        assert body["payer"] == {"openid": "open-test"}
        assert result.extra["mode"] == "jsapi"
        assert result.extra["prepay_id"] == "prepay-test"
        params = result.extra["jsapi_params"]
        signed = f"{params['appId']}\n{params['timeStamp']}\n{params['nonceStr']}\nprepay_id=prepay-test\n"
        merchant_material[0].public_key().verify(
            base64.b64decode(params["paySign"]),
            signed.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )


@pytest.mark.parametrize(
    ("channel", "extra", "error"),
    [
        ("unsupported", {}, "Unsupported WeChat Pay channel"),
        ("wx_pub", {}, "requires open_id"),
        ("wx_pub", {"open_id": "   "}, "requires open_id"),
    ],
)
def test_invalid_payment_request_never_calls_provider(
    channel: str, extra: dict, error: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = wechatpay.WechatPayProvider()
    request_call = Mock()
    monkeypatch.setattr(provider, "_request", request_call)
    with pytest.raises(RuntimeError, match=error):
        provider.create_payment(
            request=_payment_request(channel, extra=extra), app=Flask(__name__)
        )
    request_call.assert_not_called()


@pytest.mark.parametrize(
    ("channel", "error"),
    [("wx_pub_qr", "missing code_url"), ("wx_pub", "missing prepay_id")],
)
def test_incomplete_provider_response_is_rejected(
    channel: str,
    error: str,
    wechat_config: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del wechat_config
    provider = wechatpay.WechatPayProvider()
    monkeypatch.setattr(provider, "_request", Mock(return_value={}))
    with pytest.raises(RuntimeError, match=error):
        provider.create_payment(
            request=_payment_request(channel, extra={"open_id": "open-test"}),
            app=Flask(__name__),
        )


@pytest.mark.parametrize(
    ("status", "response_text", "expected"),
    [
        (200, '{"transaction_id":"tx-test"}', {"transaction_id": "tx-test"}),
        (204, "", {}),
    ],
)
def test_http_transport_signs_exact_path_and_body(
    status: int,
    response_text: str,
    expected: dict,
    wechat_config: dict[str, str],
    merchant_material: tuple[rsa.RSAPrivateKey, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wechat_config["WECHATPAY_PRIVATE_KEY"] = merchant_material[1]
    wechat_config["WECHATPAY_BASE_URL"] = "https://pay.example.test/"
    monkeypatch.setattr(wechatpay.time, "time", lambda: 1700000000)
    monkeypatch.setattr(wechatpay.secrets, "token_hex", lambda _size: "nonce-test")
    response = Mock(status_code=status, text=response_text)
    response.json.return_value = expected
    transport = Mock(return_value=response)
    monkeypatch.setattr(wechatpay.requests, "request", transport)
    path = "/v3/pay/transactions/native"
    body = '{"description":"课程"}'

    result = wechatpay.WechatPayProvider()._request(
        method="POST", path=path, body=body, app=Flask(__name__)
    )

    assert result == expected
    args, kwargs = transport.call_args
    assert args == ("POST", f"https://pay.example.test{path}")
    assert kwargs["data"] == body.encode()
    assert kwargs["timeout"] == 10
    authorization = kwargs["headers"]["Authorization"]
    scheme, value = authorization.split(" ", 1)
    assert scheme == "WECHATPAY2-SHA256-RSA2048"
    fields = dict(part.strip().split("=", 1) for part in value.split(","))
    fields = {key: value.strip('"') for key, value in fields.items()}
    assert fields["mchid"] == "merchant-test"
    assert fields["serial_no"] == "serial-test"
    merchant_material[0].public_key().verify(
        base64.b64decode(fields["signature"]),
        f"POST\n{path}\n1700000000\nnonce-test\n{body}\n".encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    if not response_text:
        response.json.assert_not_called()


@pytest.mark.parametrize("response_text", ["declined by provider", ""])
def test_http_failure_never_parses_a_success_result(
    response_text: str, wechat_config: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    del wechat_config
    provider = wechatpay.WechatPayProvider()
    monkeypatch.setattr(provider, "_sign_request", Mock(return_value="signature"))
    response = Mock(status_code=400, text=response_text)
    transport = Mock(return_value=response)
    monkeypatch.setattr(wechatpay.requests, "request", transport)
    with pytest.raises(
        RuntimeError, match=response_text or "WeChat Pay request failed"
    ):
        provider._request(method="GET", path="/v3/test", body="", app=Flask(__name__))
    assert transport.call_args.kwargs["data"] is None
    response.json.assert_not_called()


def _signed_notification(
    key: rsa.RSAPrivateKey, api_key: str, resource_payload: dict
) -> tuple[dict[str, str], str]:
    nonce = "resource1234"
    associated_data = "transaction"
    encrypted = AESGCM(api_key.encode()).encrypt(
        nonce.encode(), json.dumps(resource_payload).encode(), associated_data.encode()
    )
    body = json.dumps(
        {
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {
                "algorithm": "AEAD_AES_256_GCM",
                "nonce": nonce,
                "associated_data": associated_data,
                "ciphertext": base64.b64encode(encrypted).decode(),
            },
        }
    )
    signature = key.sign(
        f"1700000000\nnotification-test\n{body}\n".encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return {
        "Wechatpay-Timestamp": "1700000000",
        "Wechatpay-Nonce": "notification-test",
        "Wechatpay-Signature": base64.b64encode(signature).decode(),
    }, body


@pytest.mark.parametrize("as_bytes", [False, True])
@pytest.mark.parametrize(
    "resource",
    [
        {
            "out_trade_no": "attempt-test",
            "trade_state": "SUCCESS",
            "transaction_id": "transaction-test",
        },
        {},
    ],
)
def test_signed_encrypted_webhook_round_trip(
    as_bytes: bool,
    resource: dict,
    merchant_material: tuple[rsa.RSAPrivateKey, str, str],
    wechat_config: dict[str, str],
) -> None:
    wechat_config["WECHATPAY_PLATFORM_CERT"] = merchant_material[2]
    headers, body = _signed_notification(
        merchant_material[0], wechat_config["WECHATPAY_API_V3_KEY"], resource
    )
    result = wechatpay.WechatPayProvider().handle_notification(
        payload={"headers": headers, "raw_body": body.encode() if as_bytes else body},
        app=Flask(__name__),
    )
    assert result.order_bid == resource.get("out_trade_no", "")
    assert result.status == resource.get("trade_state", "TRANSACTION.SUCCESS")
    assert result.charge_id == resource.get("transaction_id")
    assert result.provider_payload["resource"] == resource


def test_tampered_webhook_is_rejected_before_decryption(
    merchant_material: tuple[rsa.RSAPrivateKey, str, str],
    wechat_config: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wechat_config["WECHATPAY_PLATFORM_CERT"] = merchant_material[2]
    headers, body = _signed_notification(
        merchant_material[0], wechat_config["WECHATPAY_API_V3_KEY"], {}
    )
    provider = wechatpay.WechatPayProvider()
    decrypt = Mock()
    monkeypatch.setattr(provider, "_decrypt_notification_resource", decrypt)
    with pytest.raises(InvalidSignature):
        provider.verify_webhook(
            headers=headers, raw_body=body + " ", app=Flask(__name__)
        )
    decrypt.assert_not_called()


@pytest.mark.parametrize(
    "missing_header", ["Wechatpay-Timestamp", "Wechatpay-Nonce", "Wechatpay-Signature"]
)
def test_unsigned_webhook_is_rejected(missing_header: str) -> None:
    headers = {
        "Wechatpay-Timestamp": "123",
        "Wechatpay-Nonce": "nonce",
        "Wechatpay-Signature": "signature",
    }
    headers.pop(missing_header)
    with pytest.raises(RuntimeError, match="signature headers missing"):
        wechatpay.WechatPayProvider().verify_webhook(
            headers=headers, raw_body="{}", app=Flask(__name__)
        )


@pytest.mark.parametrize(
    ("resource", "error"),
    [
        ({}, "resource missing"),
        ({"algorithm": "unsafe"}, "Unsupported WeChat Pay algorithm"),
    ],
)
def test_unusable_encryption_envelope_is_rejected(resource: dict, error: str) -> None:
    with pytest.raises(RuntimeError, match=error):
        wechatpay.WechatPayProvider()._decrypt_notification_resource(resource)


def test_resource_encryption_authentication_rejects_wrong_key(
    merchant_material: tuple[rsa.RSAPrivateKey, str, str], wechat_config: dict[str, str]
) -> None:
    _, body = _signed_notification(
        merchant_material[0], wechat_config["WECHATPAY_API_V3_KEY"], {}
    )
    wechat_config["WECHATPAY_API_V3_KEY"] = "abcdef0123456789abcdef0123456789"
    with pytest.raises(InvalidTag):
        wechatpay.WechatPayProvider()._decrypt_notification_resource(
            json.loads(body)["resource"]
        )


def test_keys_can_be_loaded_from_files(
    tmp_path: Path,
    merchant_material: tuple[rsa.RSAPrivateKey, str, str],
    wechat_config: dict[str, str],
) -> None:
    private_path = tmp_path / "private.pem"
    certificate_path = tmp_path / "certificate.pem"
    private_path.write_text(merchant_material[1])
    certificate_path.write_text(merchant_material[2])
    wechat_config["WECHATPAY_PRIVATE_KEY_PATH"] = str(private_path)
    wechat_config["WECHATPAY_PLATFORM_CERT_PATH"] = str(certificate_path)
    assert (
        wechatpay._load_private_key().private_numbers()
        == merchant_material[0].private_numbers()
    )
    assert (
        wechatpay._load_public_key_from_certificate().public_numbers()
        == merchant_material[0].public_key().public_numbers()
    )


def test_missing_configuration_fails_before_provider_io(
    wechat_config: dict[str, str],
) -> None:
    wechat_config.clear()
    with pytest.raises(RuntimeError, match="WECHATPAY_APP_ID must be configured"):
        wechatpay._wechatpay_app_id()
    with pytest.raises(RuntimeError, match="WECHATPAY_MCH_ID must be configured"):
        wechatpay._required_config("WECHATPAY_MCH_ID")
    wechat_config["WECHAT_APP_ID"] = " shared-app "
    assert wechatpay._wechatpay_app_id() == "shared-app"
    assert wechatpay._wechatpay_base_url() == "https://api.mch.weixin.qq.com"


def test_existing_prepay_id_gets_a_fresh_verifiable_signature(
    merchant_material: tuple[rsa.RSAPrivateKey, str, str],
    wechat_config: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wechat_config["WECHATPAY_PRIVATE_KEY"] = merchant_material[1]
    monkeypatch.setattr(wechatpay.time, "time", lambda: 1700000123)
    monkeypatch.setattr(wechatpay.secrets, "token_hex", lambda _size: "fresh-nonce")
    provider = wechatpay.WechatPayProvider()
    params = provider.build_jsapi_params(prepay_id="prepay-existing")
    assert params["signType"] == "RSA"
    merchant_material[0].public_key().verify(
        base64.b64decode(params["paySign"]),
        b"wx-test-app\n1700000123\nfresh-nonce\nprepay_id=prepay-existing\n",
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    with pytest.raises(RuntimeError, match="requires prepay_id"):
        provider.build_jsapi_params(prepay_id="")


@pytest.mark.parametrize("with_identifiers", [False, True])
def test_trade_sync_queries_merchant_and_preserves_provider_identifiers(
    with_identifiers: bool,
    wechat_config: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wechat_config["WECHATPAY_MCH_ID"] = "merchant with spaces"
    provider = wechatpay.WechatPayProvider()
    payload = (
        {"out_trade_no": "resolved-attempt", "transaction_id": "tx-test"}
        if with_identifiers
        else {}
    )
    request_call = Mock(return_value=payload)
    monkeypatch.setattr(provider, "_request", request_call)
    result = provider.sync_reference(
        provider_reference="attempt-test",
        reference_type=" CHARGE ",
        app=Flask(__name__),
    )
    assert (
        request_call.call_args.kwargs["path"]
        == "/v3/pay/transactions/out-trade-no/attempt-test?mchid=merchant+with+spaces"
    )
    assert request_call.call_args.kwargs["body"] == ""
    assert request_call.call_args.kwargs["method"] == "GET"
    assert result.order_bid == (
        "resolved-attempt" if with_identifiers else "attempt-test"
    )
    assert result.charge_id == ("tx-test" if with_identifiers else None)
    assert result.status == "manual_sync"
    assert result.provider_payload == {"trade": payload}


@pytest.mark.parametrize("operation", ["sync_reference", "cancel_payment"])
def test_unsupported_trade_reference_never_calls_provider(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = wechatpay.WechatPayProvider()
    request_call = Mock()
    monkeypatch.setattr(provider, "_request", request_call)
    with pytest.raises(RuntimeError, match="Unsupported WeChat Pay reference type"):
        getattr(provider, operation)(
            provider_reference="attempt-test",
            reference_type="subscription",
            app=Flask(__name__),
        )
    request_call.assert_not_called()


def test_failed_close_of_a_live_trade_preserves_original_error(
    wechat_config: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    del wechat_config
    provider = wechatpay.WechatPayProvider()
    failure = RuntimeError("close unavailable")
    monkeypatch.setattr(provider, "_request", Mock(side_effect=failure))
    monkeypatch.setattr(
        provider,
        "sync_reference",
        Mock(return_value=Mock(provider_payload={"trade": {"trade_state": "SUCCESS"}})),
    )
    with pytest.raises(RuntimeError, match="close unavailable") as raised:
        provider.cancel_payment(
            provider_reference="attempt-test",
            reference_type="trade",
            app=Flask(__name__),
        )
    assert raised.value is failure


def test_native_refund_fails_explicitly() -> None:
    with pytest.raises(RuntimeError, match="WeChat Pay refunds are not supported"):
        wechatpay.WechatPayProvider().refund_payment(
            request=PaymentRefundRequest(order_bid="order-test"), app=Flask(__name__)
        )
