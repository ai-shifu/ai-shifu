"""Verify scoped callback authentication, routing and integration isolation."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.route import callback
from flaskr.service.order.models import AlipayOrder, Order, PingxxOrder, WechatPayOrder
from flaskr.service.order.payment_providers.base import PaymentNotificationResult

from tests.service.billing.test_billing_callbacks import (
    billing_callback_app,
)

__all__ = ["billing_callback_app"]


@pytest.fixture
def services(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    context = SimpleNamespace(
        provider="alipay", creator_bid="owner", integration_bid="integration"
    )
    resolve = Mock(return_value=context)
    notification = PaymentNotificationResult(
        order_bid="attempt", status="SUCCESS", charge_id="charge", provider_payload={}
    )
    provider = Mock()
    provider.verify_webhook.return_value = notification
    provider.handle_notification.return_value = notification
    billing = Mock(return_value=SimpleNamespace(matched=False))
    legacy = Mock(return_value=True)
    integration = Mock()
    monkeypatch.setattr(callback, "resolve_provider_credential_context", resolve)
    monkeypatch.setattr(
        callback, "build_provider_config_overrides", Mock(return_value={})
    )
    monkeypatch.setattr(callback, "get_payment_provider", Mock(return_value=provider))
    monkeypatch.setattr(callback, "apply_billing_native_notification", billing)
    monkeypatch.setattr(callback, "success_buy_record_from_native", legacy)
    monkeypatch.setattr(callback, "_require_matching_integration", integration)
    return SimpleNamespace(
        context=context,
        resolve=resolve,
        provider=provider,
        notification=notification,
        billing=billing,
        legacy=legacy,
        integration=integration,
    )


@pytest.mark.parametrize("context_provider", [None, "stripe"])
def test_invalid_callback_token_or_provider_never_verifies_payload(
    billing_callback_app: Flask, services: SimpleNamespace, context_provider: str | None
) -> None:
    services.resolve.return_value = (
        SimpleNamespace(provider=context_provider) if context_provider else None
    )
    response = billing_callback_app.test_client().post(
        "/api/order/webhooks/alipay/token", data=b"untrusted"
    )
    assert response.status_code == 400
    assert response.get_json() == {"code": "FAIL", "message": "invalid callback"}
    services.provider.verify_webhook.assert_not_called()
    services.billing.assert_not_called()


@pytest.mark.parametrize("provider_name", ["alipay", "wechatpay"])
@pytest.mark.parametrize("billing_matched", [False, True])
def test_scoped_native_callback_routes_once_after_matching_integration(
    billing_callback_app: Flask,
    services: SimpleNamespace,
    provider_name: str,
    billing_matched: bool,
) -> None:
    services.context.provider = provider_name
    services.billing.return_value.matched = billing_matched
    response = billing_callback_app.test_client().post(
        f"/api/order/webhooks/{provider_name}/token",
        data=b"signed body",
        headers={"X-Signature": "signature"},
    )
    assert response.status_code == 200
    if provider_name == "alipay":
        assert response.get_data(as_text=True) == "success"
        assert response.mimetype == "text/plain"
    else:
        assert response.get_json()["code"] == "SUCCESS"
    services.resolve.assert_called_once_with(
        billing_callback_app, provider=provider_name, callback_token="token"
    )
    services.integration.assert_called_once_with(
        provider_name, "attempt", "owner", "integration"
    )
    kwargs = services.provider.verify_webhook.call_args.kwargs
    assert kwargs["raw_body"] == b"signed body"
    assert kwargs["headers"]["X-Signature"] == "signature"
    services.billing.assert_called_once_with(
        billing_callback_app, provider_name, services.notification
    )
    if billing_matched:
        services.legacy.assert_not_called()
    else:
        services.legacy.assert_called_once_with(
            billing_callback_app, provider_name, services.notification
        )


@pytest.mark.parametrize("provider_name", ["alipay", "wechatpay", "pingxx"])
@pytest.mark.parametrize("failure_phase", ["verification", "integration"])
def test_scoped_failure_hides_details_and_does_not_apply_payment(
    billing_callback_app: Flask,
    services: SimpleNamespace,
    provider_name: str,
    failure_phase: str,
) -> None:
    services.context.provider = provider_name
    target = (
        services.provider.verify_webhook
        if failure_phase == "verification"
        else services.integration
    )
    target.side_effect = RuntimeError("private signing material")
    response = billing_callback_app.test_client().post(
        f"/api/order/webhooks/{provider_name}/token", data=b"body"
    )
    assert "private" not in response.get_data(as_text=True)
    if provider_name == "alipay":
        assert response.status_code == 200
        assert response.get_data(as_text=True) == "failure"
    else:
        assert response.status_code == 400
        assert response.get_json() == {"code": "FAIL", "message": "processing error"}
    services.billing.assert_not_called()
    services.legacy.assert_not_called()


@pytest.mark.parametrize("status", ["charge.succeeded", "refund.succeeded"])
@pytest.mark.parametrize("billing_matched", [False, True])
def test_scoped_pingxx_only_applies_successful_charge(
    billing_callback_app: Flask,
    services: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    billing_matched: bool,
) -> None:
    services.context.provider = "pingxx"
    services.notification.status = status
    services.notification.provider_payload = {"type": status}
    billing = Mock(return_value=SimpleNamespace(matched=billing_matched))
    legacy = Mock()
    monkeypatch.setattr(callback, "handle_billing_pingxx_webhook", billing)
    monkeypatch.setattr(callback, "success_buy_record_from_pingxx", legacy)
    response = billing_callback_app.test_client().post(
        "/api/order/webhooks/pingxx/token"
    )
    assert response.get_data(as_text=True) == "pingxx callback success"
    assert billing.call_count == (status == "charge.succeeded")
    if status == "charge.succeeded" and not billing_matched:
        legacy.assert_called_once_with(billing_callback_app, "charge", {"type": status})
    else:
        legacy.assert_not_called()


def test_scoped_stripe_forwards_raw_bytes_signature_and_expected_integration(
    billing_callback_app: Flask,
    services: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services.context.provider = "stripe"
    handler = Mock(return_value=({"accepted": False}, 409))
    monkeypatch.setattr(callback, "handle_stripe_webhook", handler)
    response = billing_callback_app.test_client().post(
        "/api/order/webhooks/stripe/token",
        data=b'{"signed": true}',
        headers={"Stripe-Signature": "signature"},
    )
    assert response.status_code == 409
    assert response.get_json() == {"accepted": False}
    handler.assert_called_once_with(
        billing_callback_app,
        b'{"signed": true}',
        "signature",
        expected_integration_bid="integration",
    )
    services.provider.verify_webhook.assert_not_called()


@pytest.mark.parametrize("provider_name", ["alipay", "wechatpay"])
def test_legacy_notification_acknowledges_unmatched_payment(
    billing_callback_app: Flask,
    services: SimpleNamespace,
    provider_name: str,
) -> None:
    services.legacy.return_value = False
    response = billing_callback_app.test_client().post(
        f"/api/callback/{provider_name}-notify"
    )
    assert response.status_code == 200
    if provider_name == "alipay":
        assert response.get_data(as_text=True) == "success"
    else:
        assert response.get_json()["code"] == "SUCCESS"


def test_legacy_alipay_verification_failure_returns_retry_response(
    billing_callback_app: Flask,
    services: SimpleNamespace,
) -> None:
    services.provider.handle_notification.side_effect = ValueError("bad signature")
    response = billing_callback_app.test_client().post("/api/callback/alipay-notify")
    assert response.get_data(as_text=True) == "failure"
    services.billing.assert_not_called()


@pytest.mark.parametrize("provider_name", ["pingxx", "alipay", "wechatpay"])
@pytest.mark.parametrize("mismatch", ["none", "creator", "integration", "missing"])
def test_matching_integration_uses_latest_order_snapshot_and_exact_owner(
    billing_callback_app: Flask,
    provider_name: str,
    mismatch: str,
) -> None:
    token = uuid4().hex
    order_bid = uuid4().hex
    with billing_callback_app.app_context():
        db.session.add(
            Order(
                order_bid=order_bid,
                creator_bid="owner",
                payment_integration_bid="integration",
            )
        )
        model = {
            "pingxx": PingxxOrder,
            "alipay": AlipayOrder,
            "wechatpay": WechatPayOrder,
        }[provider_name]
        identifier = (
            "transaction_no" if provider_name == "pingxx" else "provider_attempt_id"
        )
        for domain, bid in [
            ("order", "old-order"),
            ("order", order_bid),
            ("billing", "foreign"),
        ]:
            db.session.add(
                model(
                    **{
                        identifier: token,
                        "biz_domain": domain,
                        "order_bid": bid,
                        f"{provider_name}_order_bid": uuid4().hex,
                    },
                    **(
                        {"extra": "{}", "charge_object": "{}"}
                        if provider_name == "pingxx"
                        else {}
                    ),
                )
            )
        db.session.commit()
        args = (
            provider_name,
            "absent" if mismatch == "missing" else token,
            "foreign" if mismatch == "creator" else "owner",
            "foreign" if mismatch == "integration" else "integration",
        )
        if mismatch == "none":
            callback._require_matching_integration(*args)
        else:
            with pytest.raises(RuntimeError, match="does not match"):
                callback._require_matching_integration(*args)
