"""A Stripe checkout session must carry the evidence that identifies its order.

A payment-mode session has no PaymentIntent until the buyer starts paying, so
a sync that runs before that can only read metadata from the session itself.
Writing the evidence onto the PaymentIntent alone leaves an abandoned checkout
with nothing to match against.
"""

from __future__ import annotations

from typing import Any

from flask import Flask
from flaskr.service.order.payment_providers.base import PaymentRequest
from flaskr.service.order.payment_providers.stripe import StripeProvider


def _install_fake_stripe(
    monkeypatch: object, captured_session: dict[str, Any]
) -> StripeProvider:
    class FakeSession:
        @staticmethod
        def create(**kwargs: object) -> object:
            captured_session.update(kwargs)
            return type(
                "SessionResponse",
                (),
                {
                    "to_dict": lambda _self: {
                        "id": "cs_metadata",
                        "url": "https://stripe.test/checkout",
                        "payment_intent": "",
                    }
                },
            )()

    class FakeCheckout:
        Session = FakeSession

    class FakeStripe:
        checkout = FakeCheckout

    provider = StripeProvider()
    monkeypatch.setattr(provider, "_client_options", lambda _app: (FakeStripe, {}))
    return provider


def _checkout_request(extra: dict[str, Any]) -> PaymentRequest:
    return PaymentRequest(
        order_bid="bill-order-metadata",
        user_bid="creator-metadata",
        shifu_bid="",
        amount=2900,
        channel="checkout_session",
        currency="USD",
        subject="Credits",
        body="Credits",
        client_ip="127.0.0.1",
        extra={
            "mode": "checkout_session",
            "success_url": "https://app.test/success",
            "cancel_url": "https://app.test/cancel",
            "line_items": [{"price_data": {}, "quantity": 1}],
            **extra,
        },
    )


def test_a_payment_session_carries_the_order_evidence(monkeypatch: object) -> None:
    captured_session: dict[str, Any] = {}
    provider = _install_fake_stripe(monkeypatch, captured_session)

    provider.create_payment(
        request=_checkout_request(
            {"metadata": {"bill_order_bid": "bill-order-metadata"}}
        ),
        app=Flask(__name__),
    )

    assert captured_session["metadata"]["bill_order_bid"] == "bill-order-metadata"
    assert captured_session["metadata"]["order_bid"] == "bill-order-metadata"
    # The PaymentIntent keeps its own copy for everything that reads it later.
    assert (
        captured_session["payment_intent_data"]["metadata"]["bill_order_bid"]
        == "bill-order-metadata"
    )


def test_a_subscription_session_carries_the_order_evidence(
    monkeypatch: object,
) -> None:
    captured_session: dict[str, Any] = {}
    provider = _install_fake_stripe(monkeypatch, captured_session)

    provider.create_payment(
        request=_checkout_request(
            {
                "metadata": {"bill_order_bid": "bill-order-metadata"},
                "session_params": {"mode": "subscription"},
            }
        ),
        app=Flask(__name__),
    )

    assert captured_session["metadata"]["bill_order_bid"] == "bill-order-metadata"
    assert (
        captured_session["subscription_data"]["metadata"]["bill_order_bid"]
        == "bill-order-metadata"
    )


def test_caller_session_metadata_never_overwrites_the_order_evidence(
    monkeypatch: object,
) -> None:
    captured_session: dict[str, Any] = {}
    provider = _install_fake_stripe(monkeypatch, captured_session)

    provider.create_payment(
        request=_checkout_request(
            {
                "metadata": {"bill_order_bid": "bill-order-metadata"},
                "session_params": {
                    "metadata": {"bill_order_bid": "spoofed", "campaign": "spring"}
                },
            }
        ),
        app=Flask(__name__),
    )

    assert captured_session["metadata"]["bill_order_bid"] == "bill-order-metadata"
    assert captured_session["metadata"]["campaign"] == "spring"
