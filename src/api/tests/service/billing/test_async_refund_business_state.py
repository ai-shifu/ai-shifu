"""Keep asynchronous refunds pending until their verified success."""

from dataclasses import replace

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.billing import checkout
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditWallet,
)
from flaskr.service.order.payment_providers.base import PaymentRefundResult

from tests.service.billing.test_billing_refund_phases import _paid_order
from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    _notify,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.mark.parametrize("status", ["pending", "requires_action"])
@pytest.mark.parametrize("outcome", ["succeeded", "failed"])
def test_refund_awaits_verified_success_without_repeating_provider_io(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, status: str, outcome: str
) -> None:
    app = integration_app
    bid = _paid_order(app, monkeypatch, subscription=True)
    order = BillingOrder.query.filter_by(bill_order_bid=bid).one()
    sub = BillingSubscription.query.filter_by(
        subscription_bid=order.subscription_bid
    ).one()
    wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
    balance = wallet.available_credits
    calls = []

    def refund(*_args: object, **_kwargs: object) -> PaymentRefundResult:
        calls.append(True)
        return PaymentRefundResult("refund-awaiting", {"status": status}, status)

    monkeypatch.setattr(FixtureProvider, "refund_payment", refund)
    for _ in range(2):
        result = checkout.refund_billing_order(app, "creator-1", bid, {})
        assert result.status == status
        assert result.refund_reference_id == "refund-awaiting"
    dao.db.session.expire_all()
    assert len(calls) == 1
    assert order.status == BILLING_ORDER_STATUS_PAID
    assert sub.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert sub.cancel_at_period_end == 0
    assert wallet.available_credits == balance
    original = FixtureProvider.describe_notification.__func__

    def normalize(cls: type, notification: object) -> object:
        return replace(
            original(cls, notification),
            kind="refund",
            refund_status=outcome,
            refund_reference="refund-awaiting",
        )

    monkeypatch.setattr(
        FixtureProvider, "describe_notification", classmethod(normalize)
    )
    with app.test_client() as client:
        for _ in range(2):
            assert (
                _notify(
                    client,
                    "fixture-pay",
                    bid,
                    state="refunded" if outcome == "succeeded" else "unknown",
                ).status_code
                == 200
            )
    dao.db.session.expire_all()
    assert order.status == (
        BILLING_ORDER_STATUS_REFUNDED
        if outcome == "succeeded"
        else BILLING_ORDER_STATUS_PAID
    )
    assert sub.status == (
        BILLING_SUBSCRIPTION_STATUS_CANCELED
        if outcome == "succeeded"
        else BILLING_SUBSCRIPTION_STATUS_ACTIVE
    )
    assert wallet.available_credits == (0 if outcome == "succeeded" else balance)
    assert len(calls) == 1
    if outcome == "succeeded":
        assert (
            checkout.refund_billing_order(app, "creator-1", bid, {}).status
            == "refunded"
        )
        assert len(calls) == 1


@pytest.mark.parametrize("initial", ["pending", "requires_action"])
@pytest.mark.parametrize(
    "event_type",
    ["refund.created", "refund.updated", "charge.refund.updated", "refund.failed"],
)
@pytest.mark.parametrize(
    "status", ["pending", "requires_action", "failed", "canceled", "succeeded"]
)
def test_stripe_async_refund_events_preserve_business_until_success(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    initial: str,
    event_type: str,
    status: str,
) -> None:
    from flaskr.service.billing import webhooks
    from flaskr.service.order.models import StripeOrder
    from flaskr.service.order.payment_providers.base import PaymentNotificationResult
    from flaskr.service.order.payment_providers.stripe import StripeProvider

    from tests.service.billing.test_contract_identity import _case

    app = integration_app
    order, sub = _case(app, "stripe")
    bid = order.bill_order_bid
    calls = []

    def refund(*_args: object, **_kwargs: object) -> PaymentRefundResult:
        calls.append(True)
        return PaymentRefundResult(
            "re_awaiting", {"id": "re_awaiting", "status": initial}, initial
        )

    monkeypatch.setattr(StripeProvider, "refund_payment", refund)
    assert checkout.refund_billing_order(app, "creator-1", bid, {}).status == initial
    event = PaymentNotificationResult(
        bid,
        event_type,
        {
            "type": event_type,
            "data": {
                "object": {
                    "id": "re_awaiting",
                    "status": status,
                    "payment_intent": "pi_bound",
                    "metadata": {"bill_order_bid": bid},
                }
            },
        },
    )
    for _ in range(2):
        assert webhooks.apply_billing_stripe_notification(app, event).status_code == 200
    dao.db.session.expire_all()
    succeeded = status == "succeeded"
    assert order.status == (
        BILLING_ORDER_STATUS_REFUNDED if succeeded else BILLING_ORDER_STATUS_PAID
    )
    assert sub.status == (
        BILLING_SUBSCRIPTION_STATUS_CANCELED
        if succeeded
        else BILLING_SUBSCRIPTION_STATUS_ACTIVE
    )
    assert StripeOrder.query.filter_by(bill_order_bid=bid).one().status == (
        2 if succeeded else 1
    )
    assert len(calls) == 1
    if succeeded:
        # Delayed pending evidence cannot resurrect a completed refund.
        pending = replace(
            event,
            provider_payload={
                "type": "refund.updated",
                "data": {
                    "object": {
                        "id": "re_awaiting",
                        "status": "pending",
                        "metadata": {"bill_order_bid": bid},
                    }
                },
            },
        )
        webhooks.apply_billing_stripe_notification(app, pending)
        assert (
            checkout.refund_billing_order(app, "creator-1", bid, {}).status
            == "refunded"
        )
        assert len(calls) == 1


def test_refund_callback_can_finish_before_provider_response_without_waiting_for_refund_lock(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import webhooks
    from flaskr.service.order.payment_providers.base import PaymentNotificationResult
    from flaskr.service.order.payment_providers.stripe import StripeProvider

    from tests.service.billing.test_contract_identity import _case

    app = integration_app
    order, sub = _case(app, "stripe")
    bid = order.bill_order_bid

    def refund(*_args: object, **_kwargs: object) -> PaymentRefundResult:
        event = PaymentNotificationResult(
            bid,
            "refund.updated",
            {
                "type": "refund.updated",
                "data": {
                    "object": {
                        "id": "re_early",
                        "status": "succeeded",
                        "metadata": {"bill_order_bid": bid},
                    }
                },
            },
        )
        assert webhooks.apply_billing_stripe_notification(app, event).status_code == 200
        return PaymentRefundResult("re_early", {"status": "pending"}, "pending")

    monkeypatch.setattr(StripeProvider, "refund_payment", refund)
    result = checkout.refund_billing_order(app, "creator-1", bid, {})
    assert result.status == "refunded"
    assert result.refund_reference_id == "re_early"
    dao.db.session.expire_all()
    assert order.status == BILLING_ORDER_STATUS_REFUNDED
    assert sub.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
