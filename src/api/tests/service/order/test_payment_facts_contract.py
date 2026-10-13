"""Preserve protocol evidence and compatibility while sharing payment facts."""

from __future__ import annotations

import pytest
from flaskr.service.order.payment_providers.api import (
    PaymentNotificationResult,
    historical_billing_mode,
    legacy_native_amount,
    native_facts,
    notification_facts,
    payment_definition,
)
from flaskr.service.order.payment_providers.normalization import normalized_notification


def test_native_query_keeps_business_order_and_external_reference_separate() -> None:
    notification = PaymentNotificationResult(
        "business-order",
        "manual_sync",
        {
            "trade": {
                "out_trade_no": "external-attempt",
                "trade_status": "WAIT_BUYER_PAY",
            }
        },
    )
    facts = notification_facts("alipay", notification)
    assert notification.order_bid == "business-order"
    assert facts.provider_reference == "external-attempt"
    assert facts.state == "pending"
    assert facts.order_amount is None


@pytest.mark.parametrize(
    ("amount", "expected", "source"),
    [
        ({"total": 100}, 100, "order"),
        ({"total": 100, "payer_total": 80}, 80, "payer"),
        ({"total": 100, "payer_total": None}, None, "payer"),
        ({}, None, "order"),
    ],
)
def test_wechat_facts_keep_amount_sources_and_legacy_validation_distinct(
    amount: dict,
    expected: int | None,
    source: str,
) -> None:
    facts = native_facts("wechatpay", {"trade_state": "SUCCESS", "amount": amount})
    assert facts.order_amount == amount.get("total")
    assert facts.payer_amount == amount.get("payer_total")
    assert facts.validation_amount_source == source
    assert legacy_native_amount(facts) == expected


def test_malformed_amount_is_not_invented_and_is_rejected_at_validation() -> None:
    facts = native_facts(
        "alipay", {"trade_status": "TRADE_SUCCESS", "total_amount": "invalid"}
    )
    assert facts.state == "paid"
    assert facts.order_amount is None
    assert facts.invalid_validation_amount
    with pytest.raises(ValueError, match="Invalid reported payment amount"):
        legacy_native_amount(facts)


def test_stripe_contract_state_is_not_payment_evidence() -> None:
    result = normalized_notification(
        "stripe",
        order_bid="order",
        status="customer.subscription.updated",
        provider_payload={
            "id": "event",
            "created": 10,
            "data": {
                "object": {
                    "id": "sub_original",
                    "customer": "cus_original",
                    "status": "active",
                    "current_period_start": 10,
                    "current_period_end": 20,
                }
            },
        },
    )
    assert result.facts.state == "unknown"
    assert result.facts.order_amount is None
    assert result.subscription.provider_reference == "sub_original"
    assert result.subscription.customer_reference == "cus_original"
    assert result.subscription.period_end == 20


def test_stripe_checkout_payment_keeps_currency_amount_and_identity() -> None:
    result = normalized_notification(
        "stripe",
        order_bid="order",
        status="checkout.session.completed",
        provider_payload={
            "id": "event",
            "created": 10,
            "data": {
                "object": {
                    "id": "cs_original",
                    "payment_status": "paid",
                    "amount_total": 1234,
                    "currency": "usd",
                }
            },
        },
    )
    assert result.facts.state == "paid"
    assert result.facts.order_amount == 1234
    assert result.facts.currency == "USD"
    assert result.facts.event_id == "event"
    assert result.subscription is None


def test_declared_capabilities_preserve_current_subscription_and_optional_features() -> (
    None
):
    pingxx_jsapi = next(
        route
        for route in payment_definition("pingxx").routes
        if route.channel == "wx_pub"
    )
    assert pingxx_jsapi.action == "jsapi"
    assert not pingxx_jsapi.prefer_in_wechat
    stripe = payment_definition("stripe").capabilities
    assert stripe.subscription_create
    assert stripe.subscription_cancel
    assert stripe.subscription_resume
    assert stripe.refund
    assert stripe.catalog
    assert stripe.discounts
    for name in ("pingxx", "alipay", "wechatpay"):
        capabilities = payment_definition(name).capabilities
        assert capabilities.billing_mode == "platform_managed"
        assert not capabilities.subscription_create
        assert not capabilities.subscription_cancel
        assert not capabilities.subscription_resume


def test_historical_modes_do_not_require_an_active_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.order import payment_providers

    monkeypatch.setattr(payment_providers, "_PROVIDER_REGISTRY", {})
    assert historical_billing_mode("pingxx") == "platform_managed"
    assert historical_billing_mode("stripe") == "provider_managed"
    with pytest.raises(ValueError, match="Unsupported payment channel"):
        payment_definition("pingxx")


@pytest.mark.parametrize("provider", ["pingxx", "stripe"])
@pytest.mark.parametrize(
    "data", [None, [], "invalid", {"object": None}, {"object": []}]
)
def test_malformed_notification_envelope_is_not_payment_evidence(
    provider: str, data: object
) -> None:
    result = normalized_notification(
        provider,
        order_bid="order",
        status="notification",
        provider_payload={"data": data},
    )
    assert result.facts.state != "paid"
    assert result.facts.order_amount is None
    assert result.subscription is None
