from __future__ import annotations

from flaskr.service.billing import checkout, subscriptions, webhooks
from flaskr.service.order.payment_providers import (
    PaymentProvider,
    PaymentRequest,
    get_payment_provider,
)


def test_billing_modules_reuse_shared_payment_provider_adapter() -> None:
    assert checkout.PaymentRequest is PaymentRequest
    assert checkout.get_payment_provider is get_payment_provider
    assert subscriptions.get_payment_provider is get_payment_provider
    assert webhooks.get_payment_provider is get_payment_provider


def test_shared_payment_provider_base_exposes_billing_required_hooks() -> None:
    assert "create_payment" in PaymentProvider.__abstractmethods__
    assert callable(PaymentProvider.create_subscription)
    assert callable(PaymentProvider.cancel_subscription)
    assert callable(PaymentProvider.resume_subscription)
    assert callable(PaymentProvider.verify_webhook)
    assert callable(PaymentProvider.sync_reference)
