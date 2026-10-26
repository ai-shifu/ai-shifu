"""Verify Alipay requests, signed callbacks, and recovery without provider access."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING
from unittest.mock import Mock
from urllib.parse import urlencode

import pytest
import rsa as alipay_rsa
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from flask import Flask
from flaskr.service.order.payment_providers import alipay
from flaskr.service.order.payment_providers.base import (
    PaymentRefundRequest,
    PaymentRequest,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(scope="module")
def alipay_keys() -> tuple[rsa.RSAPrivateKey, str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        .decode()
    )
    return key, private, public


@pytest.fixture
def alipay_config(
    monkeypatch: pytest.MonkeyPatch, alipay_keys: tuple[rsa.RSAPrivateKey, str, str]
) -> dict[str, str]:
    config = {
        "ALIPAY_APP_ID": "alipay-app-test",
        "ALIPAY_APP_PRIVATE_KEY": alipay_keys[1],
        "ALIPAY_PUBLIC_KEY": alipay_keys[2],
        "ALIPAY_WEBHOOK_URL": "https://payments.example.test/alipay",
    }
    monkeypatch.setattr(
        alipay, "get_config", lambda key, default="": config.get(key, default)
    )
    return config


def _payment_request(**overrides: object) -> PaymentRequest:
    values = {
        "order_bid": "alipay-attempt-test",
        "user_bid": "user-test",
        "shifu_bid": "course-test",
        "amount": 12345,
        "channel": "alipay_qr",
        "currency": "CNY",
        "subject": "",
        "body": "",
        "client_ip": "127.0.0.1",
    }
    return PaymentRequest(**(values | overrides))


@pytest.mark.parametrize("response_kind", ["nested", "json", "sdk_object", "flat"])
def test_precreate_accepts_provider_response_shapes_and_builds_exact_request(
    response_kind: str, alipay_config: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {"code": "10000", "qr_code": "https://alipay.example.test/qr"}
    response: object = {"alipay_trade_precreate_response": payload}
    if response_kind == "json":
        response = json.dumps(response)
    elif response_kind == "sdk_object":
        response = Mock(to_dict=Mock(return_value=response))
    elif response_kind == "flat":
        response = payload
    client = Mock()
    client.execute.return_value = response
    provider = alipay.AlipayProvider()
    monkeypatch.setattr(provider, "_ensure_client", Mock(return_value=client))
    result = provider.create_subscription(
        request=_payment_request(extra={"timeout_express": "30m"}), app=Flask(__name__)
    )

    sent = client.execute.call_args.args[0]
    assert sent.biz_model.out_trade_no == "alipay-attempt-test"
    assert sent.biz_model.total_amount == "123.45"
    assert sent.biz_model.subject == "alipay-attempt-test"
    assert sent.biz_model.body == "alipay-attempt-test"
    assert sent.biz_model.timeout_express == "30m"
    assert sent.notify_url == alipay_config["ALIPAY_WEBHOOK_URL"]
    assert result.provider_reference == "alipay-attempt-test"
    assert result.raw_response == payload
    assert result.extra["credential"] == {"alipay_qr": payload["qr_code"]}
    assert result.extra["raw_request"]["total_amount"] == "123.45"


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (
            {"code": "40004", "sub_msg": "invalid merchant", "msg": "ignored"},
            "invalid merchant",
        ),
        ({"code": "40004", "msg": "provider unavailable"}, "provider unavailable"),
        ({"code": "40004"}, "Alipay precreate failed"),
        ({"code": "10000"}, "missing qr_code"),
        ([], "Invalid Alipay response"),
    ],
)
def test_precreate_rejects_provider_failures(
    response: object,
    error: str,
    alipay_config: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del alipay_config
    provider = alipay.AlipayProvider()
    monkeypatch.setattr(
        provider,
        "_ensure_client",
        Mock(return_value=Mock(execute=Mock(return_value=response))),
    )
    with pytest.raises(RuntimeError, match=error):
        provider.create_payment(request=_payment_request(), app=Flask(__name__))


def test_unsupported_channel_does_not_initialize_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = alipay.AlipayProvider()
    client = Mock()
    monkeypatch.setattr(provider, "_ensure_client", client)
    with pytest.raises(RuntimeError, match="Unsupported Alipay channel"):
        provider.create_payment(
            request=_payment_request(channel="wx_pub"), app=Flask(__name__)
        )
    client.assert_not_called()


def _signed_payload(key: rsa.RSAPrivateKey) -> dict[str, object]:
    payload = {
        "out_trade_no": "attempt-test",
        "trade_no": "transaction-test",
        "trade_status": "TRADE_SUCCESS",
        "charset": "utf-8",
        "subject": "课程",
    }
    signed = "&".join(f"{name}={value}" for name, value in sorted(payload.items()))
    signature = key.sign(signed.encode(), padding.PKCS1v15(), hashes.SHA256())
    return payload | {"sign": base64.b64encode(signature).decode(), "sign_type": "RSA2"}


@pytest.mark.parametrize("payload_kind", ["mapping", "raw_text", "raw_bytes"])
def test_signed_notification_uses_real_sdk_verification(
    payload_kind: str,
    alipay_keys: tuple[rsa.RSAPrivateKey, str, str],
    alipay_config: dict[str, str],
) -> None:
    del alipay_config
    payload = _signed_payload(alipay_keys[0])
    if payload_kind == "mapping":
        incoming = payload | {"ignored_none": None}
    else:
        body = urlencode(payload)
        incoming = {
            "raw_body": body.encode() if payload_kind == "raw_bytes" else body,
            "headers": None,
        }
    result = alipay.AlipayProvider().handle_notification(
        payload=incoming, app=Flask(__name__)
    )
    assert result.order_bid == "attempt-test"
    assert result.status == "TRADE_SUCCESS"
    assert result.charge_id == "transaction-test"
    assert result.provider_payload["subject"] == "课程"


def test_tampered_notification_fails_signature_verification(
    alipay_keys: tuple[rsa.RSAPrivateKey, str, str], alipay_config: dict[str, str]
) -> None:
    del alipay_config
    payload = _signed_payload(alipay_keys[0]) | {"out_trade_no": "wrong-attempt"}
    with pytest.raises(alipay_rsa.VerificationError):
        alipay.AlipayProvider().handle_notification(
            payload=payload, app=Flask(__name__)
        )


@pytest.mark.parametrize("raw", [False, True])
def test_missing_signature_cannot_be_normalized_as_a_payment(
    raw: bool, alipay_config: dict[str, str]
) -> None:
    del alipay_config
    provider = alipay.AlipayProvider()
    method = provider.verify_webhook if raw else provider.handle_notification
    kwargs = (
        {"headers": {}, "raw_body": b"out_trade_no=attempt-test"}
        if raw
        else {"payload": {"out_trade_no": "attempt-test"}}
    )
    with pytest.raises(RuntimeError, match="signature verification failed"):
        method(**kwargs, app=Flask(__name__))


def test_notification_parser_preserves_blank_values_and_last_duplicate() -> None:
    assert alipay._parse_form_payload("subject=&out_trade_no=old&out_trade_no=new") == {
        "subject": "",
        "out_trade_no": "new",
    }
    assert alipay._parse_form_payload("") == {}


@pytest.mark.parametrize(
    ("response", "expected_order", "expected_charge"),
    [
        (
            {"out_trade_no": "resolved-order", "trade_no": "tx-resolved"},
            "resolved-order",
            "tx-resolved",
        ),
        ({}, "attempt-test", None),
    ],
)
def test_manual_sync_normalizes_provider_trade(
    response: dict,
    expected_order: str,
    expected_charge: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = alipay.AlipayProvider()
    client = Mock(execute=Mock(return_value={"alipay_trade_query_response": response}))
    monkeypatch.setattr(provider, "_ensure_client", Mock(return_value=client))
    result = provider.sync_reference(
        provider_reference="attempt-test", reference_type=" TRADE ", app=Flask(__name__)
    )
    assert client.execute.call_args.args[0].biz_model.out_trade_no == "attempt-test"
    assert result.order_bid == expected_order
    assert result.charge_id == expected_charge
    assert result.status == "manual_sync"
    assert result.provider_payload == {"trade": response}


@pytest.mark.parametrize("operation", ["sync_reference", "cancel_payment"])
def test_unsupported_reference_type_never_calls_client(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = alipay.AlipayProvider()
    client = Mock()
    monkeypatch.setattr(provider, "_ensure_client", client)
    with pytest.raises(RuntimeError, match="Unsupported Alipay reference type"):
        getattr(provider, operation)(
            provider_reference="attempt-test",
            reference_type="subscription",
            app=Flask(__name__),
        )
    client.assert_not_called()


@pytest.mark.parametrize("close_exception", [False, True])
@pytest.mark.parametrize("closed", [False, True])
def test_close_failure_requires_a_verified_closed_trade(
    close_exception: bool, closed: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = alipay.AlipayProvider()
    failure = RuntimeError("close transport failed")
    close = (
        Mock(side_effect=failure)
        if close_exception
        else Mock(return_value={"code": "40004"})
    )
    monkeypatch.setattr(
        provider, "_ensure_client", Mock(return_value=Mock(execute=close))
    )
    trade = {"trade_status": "TRADE_CLOSED" if closed else "WAIT_BUYER_PAY"}
    monkeypatch.setattr(
        provider,
        "sync_reference",
        Mock(return_value=Mock(provider_payload={"trade": trade})),
    )
    if closed:
        result = provider.cancel_payment(
            provider_reference="attempt-test",
            reference_type="payment",
            app=Flask(__name__),
        )
        assert result.status == "cancelled"
        assert result.raw_response == trade
    else:
        with pytest.raises(
            RuntimeError,
            match="close transport failed"
            if close_exception
            else "Alipay trade close failed",
        ) as error:
            provider.cancel_payment(
                provider_reference="attempt-test",
                reference_type="payment",
                app=Flask(__name__),
            )
        if close_exception:
            assert error.value is failure


def test_sdk_client_uses_configured_keys_and_gateway(
    alipay_config: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = alipay.AlipayProvider()
    sdk = provider._load_sdk(Flask(__name__))
    constructor = Mock()
    sdk["DefaultAlipayClient"] = constructor
    monkeypatch.setattr(provider, "_load_sdk", Mock(return_value=sdk))
    alipay_config["ALIPAY_GATEWAY_URL"] = "https://sandbox.example.test/gateway.do"
    assert provider._ensure_client(Flask(__name__)) is constructor.return_value
    config = constructor.call_args.kwargs["alipay_client_config"]
    assert config.app_id == "alipay-app-test"
    assert config.app_private_key == alipay_config["ALIPAY_APP_PRIVATE_KEY"].strip()
    assert config.alipay_public_key == alipay_config["ALIPAY_PUBLIC_KEY"].strip()
    assert config.server_url == alipay_config["ALIPAY_GATEWAY_URL"]
    alipay_config["ALIPAY_APP_ID"] = " "
    with pytest.raises(RuntimeError, match="ALIPAY_APP_ID must be configured"):
        provider._ensure_client(Flask(__name__))


def test_key_loader_supports_files_and_reports_missing_material(
    tmp_path: Path, alipay_config: dict[str, str]
) -> None:
    key_path = tmp_path / "key.pem"
    key_path.write_text(" test-key-material \n")
    alipay_config["TEST_KEY_PATH"] = str(key_path)
    assert alipay._read_required_key("TEST_KEY_PATH") == "test-key-material"
    alipay_config["INLINE_TEST_KEY"] = " inline-material "
    assert (
        alipay._read_required_key("MISSING_PATH", "INLINE_TEST_KEY")
        == "inline-material"
    )
    with pytest.raises(RuntimeError, match="MISSING_PATH must be configured"):
        alipay._read_required_key("MISSING_PATH")
    alipay_config["MISSING_PATH"] = str(tmp_path / "missing.pem")
    with pytest.raises(FileNotFoundError):
        alipay._read_required_key("MISSING_PATH")


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(0, "0.00"), (1, "0.01"), (199, "1.99"), (100000001, "1000000.01")],
)
def test_minor_units_do_not_lose_precision(amount: int, expected: str) -> None:
    assert alipay._format_cny_amount(amount) == expected


def test_refund_is_explicitly_unsupported() -> None:
    with pytest.raises(RuntimeError, match="Alipay refunds are not supported"):
        alipay.AlipayProvider().refund_payment(
            request=PaymentRefundRequest(order_bid="order-test"), app=Flask(__name__)
        )
