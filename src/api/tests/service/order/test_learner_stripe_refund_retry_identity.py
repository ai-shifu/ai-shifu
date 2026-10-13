"""Keep learner payment details consistent when archived Stripe refunds replay."""

import json
from copy import deepcopy
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.service.order import funs
from flaskr.service.order.consts import ORDER_STATUS_REFUND, ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order, StripeOrder
from flaskr.service.order.payment_providers.base import (
    PaymentNotificationResult,
    PaymentRefundResult,
)

from tests.service.order.test_order_payment_lifecycle_contracts import _order, _snapshot


def _notify(
    app: Flask,
    provider: Mock,
    snapshot: StripeOrder,
    reference: str,
    *,
    state: str = "succeeded",
    event_type: str = "refund.updated",
) -> dict:
    provider.verify_webhook.return_value = PaymentNotificationResult(
        snapshot.order_bid,
        event_type,
        {
            "type": event_type,
            "data": {
                "object": {
                    "id": reference,
                    "status": state,
                    "payment_intent": snapshot.payment_intent_id,
                    "charge": snapshot.latest_charge_id,
                    "metadata": {
                        "order_bid": snapshot.order_bid,
                        "stripe_order_bid": snapshot.stripe_order_bid,
                    },
                }
            },
        },
    )
    result, http_status = funs.handle_stripe_webhook(
        app, b"verified-refund", "signature"
    )
    assert http_status == 200
    db.session.expire_all()
    return result


def _assert_current(
    app: Flask, order: Order, snapshot: StripeOrder, *, refunded: bool
) -> None:
    db.session.expire_all()
    assert order.status == (ORDER_STATUS_REFUND if refunded else ORDER_STATUS_SUCCESS)
    assert funs.get_payment_details(app, order.order_bid, order.user_bid)["status"] == (
        snapshot.status
    )
    if refunded:
        assert snapshot.status == 2
        operation = json.loads(snapshot.metadata_json)["refund_operation"]
        assert operation["status"] == "succeeded"
        assert operation["provider_reference"] == "re_new"


@pytest.mark.parametrize("terminal", ["failed", "canceled"])
@pytest.mark.parametrize("source", ["response", "callback"])
@pytest.mark.parametrize("lost", [False, True])
def test_archived_success_cannot_claim_inflight_learner_refund_retry(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    terminal: str,
    source: str,
    lost: bool,
) -> None:
    with app.app_context():
        order = _order(status=ORDER_STATUS_SUCCESS)
        snapshot = _snapshot(order, status=1)
        bid = order.order_bid
        provider = Mock()
        monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
        requests, external = [], {}

        def refund(*, request: object, app: Flask) -> PaymentRefundResult:
            requests.append(request)
            if len(requests) == 1:
                status = terminal if source == "response" else "pending"
                return PaymentRefundResult("re_old", {"status": status}, status)
            result = external.setdefault(
                request.metadata["idempotency_key"],
                PaymentRefundResult("re_new", {"status": "succeeded"}, "succeeded"),
            )
            before = deepcopy(json.loads(snapshot.metadata_json))
            before_status = snapshot.status
            for _ in range(2):
                response = _notify(app, provider, snapshot, "re_old")
                assert response["status"] == "acknowledged"
                _assert_current(app, order, snapshot, refunded=False)
                assert snapshot.status == before_status
                assert json.loads(snapshot.metadata_json) == before
            if lost and len(requests) == 2:
                message = "Injected lost replacement learner refund response"
                raise RuntimeError(message)
            return result

        provider.refund_payment.side_effect = refund
        funs.refund_order_payment(app, bid)
        if source == "callback":
            _notify(app, provider, snapshot, "re_old", state=terminal)
        if lost:
            with pytest.raises(RuntimeError, match="Injected lost replacement"):
                funs.refund_order_payment(app, bid)
        result = funs.refund_order_payment(app, bid)
        assert result["refund_id"] == "re_new"
        assert result["status"] == "succeeded"
        _assert_current(app, order, snapshot, refunded=True)
        assert (
            requests[0].metadata["idempotency_key"]
            != requests[1].metadata["idempotency_key"]
        )
        assert len(external) == 1
        if lost:
            assert requests[1] == requests[2]
        count = provider.refund_payment.call_count
        assert funs.refund_order_payment(app, bid)["refund_id"] == "re_new"
        assert provider.refund_payment.call_count == count


@pytest.mark.parametrize("rejected_reference", ["re_old", "re_unrelated"])
@pytest.mark.parametrize(
    "event_type", ["refund.created", "refund.updated", "charge.refund.updated"]
)
def test_rejected_success_preserves_payment_details_and_current_pending_refund(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    rejected_reference: str,
    event_type: str,
) -> None:
    with app.app_context():
        order = _order(status=ORDER_STATUS_SUCCESS)
        snapshot = _snapshot(order, status=1)
        provider = Mock(
            refund_payment=Mock(
                side_effect=[
                    PaymentRefundResult("re_old", {}, "pending"),
                    PaymentRefundResult("re_new", {}, "pending"),
                ]
            )
        )
        monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
        funs.refund_order_payment(app, order.order_bid)
        _notify(app, provider, snapshot, "re_old", state="failed")
        assert funs.refund_order_payment(app, order.order_bid)["status"] == "pending"
        before = deepcopy(json.loads(snapshot.metadata_json))
        for _ in range(2):
            response = _notify(
                app, provider, snapshot, rejected_reference, event_type=event_type
            )
            assert response["status"] == "acknowledged"
            _assert_current(app, order, snapshot, refunded=False)
            assert snapshot.status == 1
            assert json.loads(snapshot.metadata_json) == before
        for _ in range(2):
            response = _notify(app, provider, snapshot, "re_new", event_type=event_type)
            assert response["status"] == "refunded"
            _assert_current(app, order, snapshot, refunded=True)
        # A paid replay cannot restore access or replace the current refund receipt.
        provider.verify_webhook.return_value = PaymentNotificationResult(
            order.order_bid,
            "payment_intent.succeeded",
            {
                "data": {
                    "object": {
                        "id": snapshot.payment_intent_id,
                        "amount": snapshot.amount,
                        "metadata": {"order_bid": order.order_bid},
                    }
                }
            },
        )
        funs.handle_stripe_webhook(app, b"verified-payment-replay", "signature")
        _assert_current(app, order, snapshot, refunded=True)
        assert funs.refund_order_payment(app, order.order_bid)["refund_id"] == "re_new"
        assert provider.refund_payment.call_count == 2


def test_current_refund_callback_rolls_back_all_learner_projections_on_lock_loss(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        order = _order(status=ORDER_STATUS_SUCCESS)
        snapshot = _snapshot(order, status=1)
        provider = Mock(
            refund_payment=Mock(
                return_value=PaymentRefundResult("re_new", {}, "pending")
            )
        )
        monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
        funs.refund_order_payment(app, order.order_bid)
        before = deepcopy(json.loads(snapshot.metadata_json))
        with monkeypatch.context() as patch:
            patch.setattr(
                funs,
                "_assert_payment_lifecycle_lock_owned",
                Mock(side_effect=RuntimeError("Injected learner callback lock loss")),
            )
            with pytest.raises(
                RuntimeError, match="Injected learner callback lock loss"
            ):
                _notify(app, provider, snapshot, "re_new")
        _assert_current(app, order, snapshot, refunded=False)
        assert snapshot.status == 1
        assert json.loads(snapshot.metadata_json) == before
        for _ in range(2):
            assert _notify(app, provider, snapshot, "re_new")["status"] == "refunded"
            _assert_current(app, order, snapshot, refunded=True)
        assert provider.refund_payment.call_count == 1


@pytest.mark.parametrize(
    ("event_type", "state"),
    [
        ("refund.updated", "succeeded"),
        ("charge.refunded", "succeeded"),
        ("refund.created", "pending"),
        ("refund.created", "unknown"),
    ],
)
def test_legacy_unrequested_learner_refund_retains_snapshot_only_projection(
    app: Flask, monkeypatch: pytest.MonkeyPatch, event_type: str, state: str
) -> None:
    with app.app_context():
        order = _order(status=ORDER_STATUS_SUCCESS)
        snapshot = _snapshot(order, status=1)
        provider = Mock()
        monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
        reference = "ch-test" if event_type == "charge.refunded" else "re_external"
        for _ in range(2):
            response = _notify(
                app, provider, snapshot, reference, event_type=event_type, state=state
            )
            assert response["status"] == "refunded"
            assert order.status == ORDER_STATUS_SUCCESS
            assert funs.get_payment_details(app, order.order_bid)["status"] == 2
            assert snapshot.status == 2
            assert "refund_operation" not in json.loads(snapshot.metadata_json)
        provider.refund_payment.assert_not_called()
