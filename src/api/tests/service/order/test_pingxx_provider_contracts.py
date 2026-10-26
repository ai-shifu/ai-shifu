"""Verify Ping++ charge requests, context configuration, and signed callbacks."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from flask import Flask
from flaskr.service.order.payment_providers import pingxx
from flaskr.service.order.payment_providers.base import PaymentRequest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def pingxx_config(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    config = {
        "PINGXX_APP_ID": "app-test",
        "PINGXX_SECRET_KEY": "sk-test",
        "PINGXX_PRIVATE_KEY": "test-inline-key",
    }
    monkeypatch.setattr(
        pingxx, "get_config", lambda key, default=None: config.get(key, default)
    )
    return config


def _request(**overrides: object) -> PaymentRequest:
    return PaymentRequest(
        **(
            {
                "order_bid": "attempt-test",
                "user_bid": "user-test",
                "shifu_bid": "course-test",
                "amount": 199,
                "currency": "cny",
                "channel": "wx_pub_qr",
                "subject": "课程😀",
                "body": "详情𠀀",
                "client_ip": "127.0.0.1",
            }
            | overrides
        )
    )


@pytest.mark.parametrize("explicit_app", [False, True])
def test_charge_sanitizes_provider_text_without_mutating_input(
    explicit_app: bool, pingxx_config: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    del pingxx_config
    charge = {"id": "ch-test", "credential": {"wx_pub_qr": "weixin://test"}}
    client = SimpleNamespace(Charge=Mock(create=Mock(return_value=charge)))
    monkeypatch.setattr(pingxx, "_get_pingpp_client", lambda: client)
    extra = {
        "name": "😀学习",
        "nested": {"description": "𠀀详情", "empty": ""},
        "amount": 100,
        "nullable": None,
    }
    options = {"charge_extra": extra}
    if explicit_app:
        options["app_id"] = "custom-app"
    result = pingxx.PingxxProvider().create_payment(
        request=_request(extra=options), app=Flask(__name__)
    )
    params = client.Charge.create.call_args.kwargs
    assert params == {
        "order_no": "attempt-test",
        "app": {"id": "custom-app" if explicit_app else "app-test"},
        "channel": "wx_pub_qr",
        "amount": 199,
        "client_ip": "127.0.0.1",
        "currency": "cny",
        "subject": "课程",
        "body": "详情",
        "extra": {
            "name": "学习",
            "nested": {"description": "详情", "empty": ""},
            "amount": 100,
            "nullable": None,
        },
    }
    assert extra["name"] == "😀学习"
    assert extra["nested"]["description"] == "𠀀详情"
    assert result.provider_reference == "ch-test"
    assert result.extra["credential"] == charge["credential"]


def test_empty_sanitized_description_uses_stable_order_id(
    pingxx_config: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    del pingxx_config
    client = SimpleNamespace(Charge=Mock(create=Mock(return_value={"id": "ch-test"})))
    monkeypatch.setattr(pingxx, "_get_pingpp_client", lambda: client)
    result = pingxx.PingxxProvider().create_payment(
        request=_request(subject="😀", body="\ud800"), app=Flask(__name__)
    )
    assert client.Charge.create.call_args.kwargs["subject"] == "attempt-test"
    assert client.Charge.create.call_args.kwargs["body"] == "attempt-test"
    assert result.extra["credential"] is None


def test_client_configuration_switches_owner_without_stale_private_key(
    pingxx_config: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = SimpleNamespace()
    monkeypatch.setattr(pingxx, "_get_pingpp_client", lambda: client)
    provider = pingxx.PingxxProvider()
    assert provider.ensure_client(Flask(__name__)) is client
    assert client.api_key == "sk-test"
    assert client.private_key == "test-inline-key"
    assert client.private_key_path is None
    key_path = tmp_path / "merchant.pem"
    key_path.write_text("file-private-key")
    pingxx_config.update(
        PINGXX_PRIVATE_KEY="",
        PINGXX_PRIVATE_KEY_PATH=str(key_path),
        PINGXX_SECRET_KEY="sk-second-owner",
    )
    provider.ensure_client(Flask(__name__))
    assert client.api_key == "sk-second-owner"
    assert client.private_key is None
    assert client.private_key_path == str(key_path)
    pingxx_config["PINGXX_PRIVATE_KEY_PATH"] = str(tmp_path / "missing.pem")
    with pytest.raises(FileNotFoundError):
        provider.ensure_client(Flask(__name__))
    pingxx_config["PINGXX_PRIVATE_KEY_PATH"] = ""
    with pytest.raises(RuntimeError, match="private key is not configured"):
        provider.ensure_client(Flask(__name__))


@pytest.mark.parametrize("with_identifiers", [False, True])
def test_sync_returns_charge_evidence_with_reference_fallback(
    with_identifiers: bool,
    pingxx_config: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del pingxx_config
    charge = {"id": "ch-provider", "order_no": "order-test"} if with_identifiers else {}
    client = SimpleNamespace(Charge=Mock(retrieve=Mock(return_value=charge)))
    monkeypatch.setattr(pingxx, "_get_pingpp_client", lambda: client)
    result = pingxx.PingxxProvider().sync_payment_status(
        order_bid="unused-local-order",
        provider_reference="ch-requested",
        app=Flask(__name__),
    )
    assert result.order_bid == ("order-test" if with_identifiers else "")
    assert result.charge_id == ("ch-provider" if with_identifiers else "ch-requested")
    assert result.status == "manual_sync"
    assert result.provider_payload == {"charge": charge}
    client.Charge.retrieve.assert_called_once_with("ch-requested")


@pytest.mark.parametrize("operation", ["sync_reference", "cancel_payment"])
def test_invalid_reference_type_is_rejected_before_loading_client(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    load_client = Mock()
    monkeypatch.setattr(pingxx, "_get_pingpp_client", load_client)
    with pytest.raises(RuntimeError, match="Unsupported Pingxx reference type"):
        getattr(pingxx.PingxxProvider(), operation)(
            provider_reference="test",
            reference_type="subscription",
            app=Flask(__name__),
        )
    load_client.assert_not_called()


@pytest.mark.parametrize(
    ("status", "recover"),
    [
        ("reversed", True),
        ("closed", True),
        ("cancelled", True),
        ("canceled", True),
        ("paid", False),
    ],
)
def test_failed_reversal_requires_verified_terminal_charge(
    status: str,
    recover: bool,
    pingxx_config: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del pingxx_config
    failure = RuntimeError("reverse unavailable")
    client = SimpleNamespace(
        Charge=Mock(
            reverse=Mock(side_effect=failure),
            retrieve=Mock(return_value={"status": status}),
        )
    )
    monkeypatch.setattr(pingxx, "_get_pingpp_client", lambda: client)
    provider = pingxx.PingxxProvider()
    if recover:
        result = provider.cancel_payment(
            provider_reference="ch-test", reference_type="charge", app=Flask(__name__)
        )
        assert result.status == "cancelled"
        assert result.raw_response == {"status": status}
    else:
        with pytest.raises(RuntimeError, match="reverse unavailable") as raised:
            provider.cancel_payment(
                provider_reference="ch-test",
                reference_type="charge",
                app=Flask(__name__),
            )
        assert raised.value is failure


@pytest.mark.parametrize(
    "operation", ["create_subscription", "cancel_subscription", "resume_subscription"]
)
def test_subscription_operations_fail_explicitly(operation: str) -> None:
    kwargs = (
        {"request": _request()}
        if operation == "create_subscription"
        else {"subscription_bid": "local-sub", "provider_subscription_id": "sub-test"}
    )
    with pytest.raises(RuntimeError, match="Pingxx does not support subscriptions"):
        getattr(pingxx.PingxxProvider(), operation)(**kwargs, app=Flask(__name__))


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.parametrize("as_bytes", [False, True])
def test_signed_charge_webhook_is_verified_with_real_rsa(
    as_bytes: bool, signing_key: rsa.RSAPrivateKey, pingxx_config: dict[str, str]
) -> None:
    pingxx_config["PINGXX_WEBHOOK_PUBLIC_KEY"] = (
        signing_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        .decode()
    )
    event = {
        "type": "charge.succeeded",
        "data": {"object": {"id": "ch-test", "order_no": "order-test"}},
    }
    body = json.dumps(event)
    signature = signing_key.sign(body.encode(), padding.PKCS1v15(), hashes.SHA256())
    payload = {
        "headers": {"X-Pingplusplus-Signature": base64.b64encode(signature).decode()},
        "raw_body": body.encode() if as_bytes else body,
    }
    result = pingxx.PingxxProvider().handle_notification(
        payload=payload, app=Flask(__name__)
    )
    assert result.order_bid == "order-test"
    assert result.charge_id == "ch-test"
    assert result.status == "charge.succeeded"
    assert result.provider_payload == event


def test_tampered_charge_webhook_is_rejected(
    signing_key: rsa.RSAPrivateKey, pingxx_config: dict[str, str]
) -> None:
    pingxx_config["PINGXX_WEBHOOK_PUBLIC_KEY"] = (
        signing_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        .decode()
    )
    signature = signing_key.sign(b"{}", padding.PKCS1v15(), hashes.SHA256())
    provider = pingxx.PingxxProvider()
    with pytest.raises(InvalidSignature):
        provider.verify_webhook(
            headers={"x-pingplusplus-signature": base64.b64encode(signature).decode()},
            raw_body="{} ",
            app=Flask(__name__),
        )
    with pytest.raises(RuntimeError, match="signature header missing"):
        provider.verify_webhook(headers={}, raw_body="{}", app=Flask(__name__))


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"type": "charge.pending", "data": {"object": None}},
        {
            "type": "charge.succeeded",
            "data": {"object": {"id": "ch-test", "order_no": "order-test"}},
        },
    ],
)
def test_normalized_charge_events_keep_optional_identifiers(
    payload: dict, pingxx_config: dict[str, str]
) -> None:
    del pingxx_config
    provider = pingxx.PingxxProvider()
    result = provider.handle_notification(payload=payload, app=Flask(__name__))
    raw_result = provider.verify_webhook(
        headers={}, raw_body=json.dumps(payload) if payload else "", app=Flask(__name__)
    )
    assert raw_result == result
    charge = payload.get("data", {}).get("object") or {}
    assert result.order_bid == charge.get("order_no", "")
    assert result.charge_id == charge.get("id")
    assert result.provider_payload == payload


def test_cached_import_error_is_raised_without_reimport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = ImportError("provider package unavailable")
    monkeypatch.setattr(pingxx._pingpp_client_state, "client", None)
    monkeypatch.setattr(pingxx._pingpp_client_state, "import_error", error)
    with pytest.raises(ImportError, match="provider package unavailable") as raised:
        pingxx._get_pingpp_client()
    assert raised.value is error
