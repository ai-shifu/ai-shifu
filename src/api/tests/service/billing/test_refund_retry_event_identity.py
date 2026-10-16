"""Do not let rejected refund events claim a replacement billing operation."""

from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.billing import checkout, webhooks
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
)
from flaskr.service.billing.models import CreditWallet
from flaskr.service.common.models import AppError
from flaskr.service.order.models import StripeOrder
from flaskr.service.order.payment_providers.base import (
    PaymentNotificationResult,
    PaymentRefundResult,
)
from flaskr.service.order.payment_providers.stripe import StripeProvider

from tests.service.billing.test_contract_identity import _case
from tests.service.order.test_payment_contract_extension import integration_app

__all__ = ["integration_app"]


@pytest.mark.parametrize("terminal", ["failed", "canceled"])
@pytest.mark.parametrize("source", ["response", "callback"])
@pytest.mark.parametrize("lost", [False, True])
@pytest.mark.parametrize("late_status", ["rejected", "succeeded"])
def test_old_billing_refund_event_cannot_claim_an_inflight_replacement(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    terminal: str,
    source: str,
    lost: bool,
    late_status: str,
) -> None:
    app = integration_app
    order, sub = _case(app, "stripe")
    bid = order.bill_order_bid
    wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
    balance = wallet.available_credits
    assert balance > 0
    requests, external = [], {}
    old = PaymentNotificationResult(
        bid,
        "refund.failed",
        {
            "type": "refund.failed",
            "data": {
                "object": {
                    "id": "re_old",
                    "status": terminal,
                    "metadata": {"bill_order_bid": bid},
                }
            },
        },
    )

    def refund(*_args: object, **kwargs: object) -> PaymentRefundResult:
        request = kwargs["request"]
        requests.append(request)
        if len(requests) == 1:
            status = terminal if source == "response" else "pending"
            return PaymentRefundResult("re_old", {"status": status}, status)
        result = external.setdefault(
            request.metadata["idempotency_key"],
            PaymentRefundResult("re_new", {"status": "succeeded"}, "succeeded"),
        )
        late = deepcopy(old)
        late.provider_payload["data"]["object"]["status"] = (
            terminal if late_status == "rejected" else "succeeded"
        )
        if late_status == "succeeded":
            late.status = late.provider_payload["type"] = "refund.updated"
        before = deepcopy(order.metadata_json["refund_operation"])
        for _ in range(2):
            assert (
                webhooks.apply_billing_stripe_notification(app, late).status_code == 200
            )
            dao.db.session.expire_all()
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert order.refunded_at is None
            assert sub.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert sub.cancel_at_period_end == 0
            assert wallet.available_credits == balance
            assert order.metadata_json["refund_operation"] == before
            assert StripeOrder.query.filter_by(bill_order_bid=bid).one().status == 1
        if lost and len(requests) == 2:
            message = "Injected lost replacement billing refund response"
            raise RuntimeError(message)
        return result

    monkeypatch.setattr(StripeProvider, "refund_payment", refund)
    if source == "response":
        with pytest.raises(AppError):
            checkout.refund_billing_order(app, "creator-1", bid, {})
    else:
        assert (
            checkout.refund_billing_order(app, "creator-1", bid, {}).status == "pending"
        )
        webhooks.apply_billing_stripe_notification(app, old)
    if lost:
        with pytest.raises(RuntimeError, match="Injected lost"):
            checkout.refund_billing_order(app, "creator-1", bid, {})
    result = checkout.refund_billing_order(app, "creator-1", bid, {})
    assert result.status == "refunded"
    assert result.refund_reference_id == "re_new"
    assert (
        requests[0].metadata["idempotency_key"]
        != requests[1].metadata["idempotency_key"]
    )
    assert len(external) == 1
    if lost:
        assert requests[1] == requests[2]
    count = len(requests)
    assert checkout.refund_billing_order(app, "creator-1", bid, {}).status == "refunded"
    assert len(requests) == count
    dao.db.session.expire_all()
    assert order.status == BILLING_ORDER_STATUS_REFUNDED
    assert sub.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
    assert wallet.available_credits == 0


@pytest.mark.parametrize("rejected_reference", ["re_old", "re_unrelated"])
@pytest.mark.parametrize(
    "event_type", ["refund.created", "refund.updated", "charge.refund.updated"]
)
def test_mismatched_success_cannot_settle_a_known_pending_replacement(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    rejected_reference: str,
    event_type: str,
) -> None:
    app = integration_app
    order, sub = _case(app, "stripe")
    bid = order.bill_order_bid
    wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
    balance = wallet.available_credits
    assert balance > 0
    refund = Mock(
        side_effect=[
            PaymentRefundResult("re_old", {}, "failed"),
            PaymentRefundResult("re_new", {}, "pending"),
        ]
    )
    monkeypatch.setattr(StripeProvider, "refund_payment", refund)
    with pytest.raises(AppError):
        checkout.refund_billing_order(app, "creator-1", bid, {})
    assert checkout.refund_billing_order(app, "creator-1", bid, {}).status == "pending"
    before = deepcopy(order.metadata_json["refund_operation"])
    event = PaymentNotificationResult(
        bid,
        event_type,
        {
            "type": event_type,
            "data": {
                "object": {
                    "id": rejected_reference,
                    "status": "succeeded",
                    "metadata": {"bill_order_bid": bid},
                }
            },
        },
    )
    for _ in range(2):
        assert webhooks.apply_billing_stripe_notification(app, event).status_code == 200
        dao.db.session.expire_all()
        assert order.status == BILLING_ORDER_STATUS_PAID
        assert order.refunded_at is None
        assert order.metadata_json["refund_operation"] == before
        assert sub.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert wallet.available_credits == balance
        assert StripeOrder.query.filter_by(bill_order_bid=bid).one().status == 1
    current_payload = deepcopy(event.provider_payload)
    current_payload["data"]["object"]["id"] = "re_new"
    current = replace(event, provider_payload=current_payload)
    persist = webhooks.persist_provider_notification

    def fail_after_snapshot(*args: object, **kwargs: object) -> None:
        persist(*args, **kwargs)
        message = "Injected refund callback snapshot failure"
        raise RuntimeError(message)

    with monkeypatch.context() as patch:
        patch.setattr(webhooks, "persist_provider_notification", fail_after_snapshot)
        with pytest.raises(RuntimeError, match="snapshot failure"):
            webhooks.apply_billing_stripe_notification(app, current)
    dao.db.session.expire_all()
    assert order.status == BILLING_ORDER_STATUS_PAID
    assert order.refunded_at is None
    assert order.metadata_json["refund_operation"] == before
    assert sub.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert sub.cancel_at_period_end == 0
    assert wallet.available_credits == balance
    assert StripeOrder.query.filter_by(bill_order_bid=bid).one().status == 1
    assert webhooks.apply_billing_stripe_notification(app, current).status == "refunded"
    assert webhooks.apply_billing_stripe_notification(app, current).status_code == 200
    dao.db.session.expire_all()
    assert order.status == BILLING_ORDER_STATUS_REFUNDED
    assert sub.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
    assert wallet.available_credits == 0
    assert (
        order.metadata_json["refund_operation"]["response"]["provider_reference"]
        == "re_new"
    )
    assert StripeOrder.query.filter_by(bill_order_bid=bid).one().status == 2
    assert checkout.refund_billing_order(app, "creator-1", bid, {}).status == "refunded"
    assert refund.call_count == 2


@pytest.mark.parametrize("terminal", ["failed", "canceled"])
@pytest.mark.parametrize("progress", ["pending", "requires_action", "unknown"])
@pytest.mark.parametrize(
    "event_type", ["refund.created", "refund.updated", "charge.refund.updated"]
)
@pytest.mark.parametrize("source", ["response", "callback"])
def test_terminal_billing_refund_failure_survives_delayed_progress_and_can_retry(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    terminal: str,
    progress: str,
    event_type: str,
    source: str,
) -> None:
    app = integration_app
    order, _sub = _case(app, "stripe")
    bid = order.bill_order_bid
    requests = []

    def refund(*_args: object, **kwargs: object) -> PaymentRefundResult:
        requests.append(kwargs["request"])
        if len(requests) == 1:
            status = terminal if source == "response" else "pending"
            return PaymentRefundResult("re_rejected", {"status": status}, status)
        return PaymentRefundResult(
            "re_replacement", {"status": "succeeded"}, "succeeded"
        )

    monkeypatch.setattr(StripeProvider, "refund_payment", refund)

    def notification(kind: str, status: str) -> PaymentNotificationResult:
        return PaymentNotificationResult(
            bid,
            kind,
            {
                "type": kind,
                "data": {
                    "object": {
                        "id": "re_rejected",
                        "status": status,
                        "metadata": {"bill_order_bid": bid},
                    }
                },
            },
        )

    if source == "response":
        with pytest.raises(AppError):
            checkout.refund_billing_order(app, "creator-1", bid, {})
    else:
        assert (
            checkout.refund_billing_order(app, "creator-1", bid, {}).status == "pending"
        )
        webhooks.apply_billing_stripe_notification(
            app, notification("refund.failed", terminal)
        )
    dao.db.session.expire_all()
    before = deepcopy(order.metadata_json["refund_operation"])
    assert before["status"] == "provider_failed"
    for _ in range(2):
        assert (
            webhooks.apply_billing_stripe_notification(
                app, notification(event_type, progress)
            ).status_code
            == 200
        )
    dao.db.session.expire_all()
    assert order.metadata_json["refund_operation"] == before
    assert checkout.refund_billing_order(app, "creator-1", bid, {}).status == "refunded"
    assert len(requests) == 2
    assert (
        requests[0].metadata["idempotency_key"]
        != requests[1].metadata["idempotency_key"]
    )
    assert (
        checkout.refund_billing_order(app, "creator-1", bid, {}).refund_reference_id
        == "re_replacement"
    )
    assert len(requests) == 2


@pytest.mark.parametrize(
    ("event_type", "state"),
    [
        ("refund.updated", "succeeded"),
        ("refund.created", "pending"),
        ("refund.created", "unknown"),
    ],
)
def test_unrequested_billing_refund_projects_only_confirmed_success(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, event_type: str, state: str
) -> None:
    app = integration_app
    order, sub = _case(app, "stripe")
    bid = order.bill_order_bid
    wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
    before = (sub.status, sub.cancel_at_period_end, wallet.available_credits)
    refund = Mock()
    monkeypatch.setattr(StripeProvider, "refund_payment", refund)
    event = PaymentNotificationResult(
        bid,
        event_type,
        {
            "type": event_type,
            "data": {
                "object": {
                    "id": "re_external",
                    "status": state,
                    "metadata": {"bill_order_bid": bid},
                }
            },
        },
    )
    assert webhooks.apply_billing_stripe_notification(app, event).status == (
        "refunded" if state == "succeeded" else "acknowledged"
    )
    assert webhooks.apply_billing_stripe_notification(app, event).status_code == 200
    dao.db.session.expire_all()
    assert order.status == (
        BILLING_ORDER_STATUS_REFUNDED
        if state == "succeeded"
        else BILLING_ORDER_STATUS_PAID
    )
    assert StripeOrder.query.filter_by(bill_order_bid=bid).one().status == (
        2 if state == "succeeded" else 1
    )
    assert not order.metadata_json.get("refund_operation")
    assert (sub.status, sub.cancel_at_period_end, wallet.available_credits) == before
    refund.assert_not_called()
