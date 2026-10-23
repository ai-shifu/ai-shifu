"""An early progress callback cannot hide a definitive direct refund response."""

from dataclasses import replace

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.billing import checkout, webhooks
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_REFUNDED,
)
from flaskr.service.common.models import AppError
from flaskr.service.order import funs
from flaskr.service.order.consts import ORDER_STATUS_REFUND, ORDER_STATUS_SUCCESS
from flaskr.service.order.payment_providers.base import (
    PaymentNotificationResult,
    PaymentRefundResult,
)
from flaskr.service.order.payment_providers.stripe import StripeProvider

from tests.service.billing.test_contract_identity import _case
from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    _learner_sync_case,
    _notify,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.mark.parametrize("domain", ["billing", "learner"])
@pytest.mark.parametrize("progress", ["pending", "requires_action"])
@pytest.mark.parametrize("terminal", ["succeeded", "failed", "canceled"])
def test_definitive_rpc_receipt_advances_a_matching_progress_callback(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    domain: str,
    progress: str,
    terminal: str,
) -> None:
    app = integration_app
    if domain == "billing":
        order, _sub = _case(app, "stripe")
        bid = order.bill_order_bid
        adapter = StripeProvider

        def callback() -> None:
            event = PaymentNotificationResult(
                bid,
                "refund.created",
                {
                    "type": "refund.created",
                    "data": {
                        "object": {
                            "id": "re_precedence",
                            "status": progress,
                            "metadata": {"bill_order_bid": bid},
                        }
                    },
                },
            )
            assert (
                webhooks.apply_billing_stripe_notification(app, event).status_code
                == 200
            )

        def execute() -> object:
            return checkout.refund_billing_order(app, "creator-1", bid, {})
    else:
        order, snapshot, _notifications = _learner_sync_case(app, monkeypatch)
        bid, reference = order.order_bid, snapshot.provider_attempt_id
        with app.test_client() as client:
            assert _notify(client, "fixture-pay", reference).status_code == 200
        adapter = FixtureProvider
        monkeypatch.setattr(
            adapter,
            "definition",
            replace(
                adapter.definition,
                capabilities=replace(adapter.definition.capabilities, refund=True),
            ),
        )
        original = adapter.describe_notification.__func__

        def describe(cls: type, notification: object) -> object:
            return replace(
                original(cls, notification),
                kind="refund",
                refund_status=progress,
                refund_reference="re_precedence",
            )

        monkeypatch.setattr(adapter, "describe_notification", classmethod(describe))

        def callback() -> None:
            with app.test_client() as client:
                assert (
                    _notify(
                        client, "fixture-pay", reference, state="unknown"
                    ).status_code
                    == 200
                )

        def execute() -> object:
            return funs.refund_order_payment(app, bid)

    calls = []

    def refund(*_args: object, **_kwargs: object) -> PaymentRefundResult:
        calls.append(True)
        callback()
        return PaymentRefundResult("re_precedence", {"status": terminal}, terminal)

    monkeypatch.setattr(adapter, "refund_payment", refund)
    if domain == "billing":
        if terminal == "succeeded":
            assert execute().status == "refunded"
            assert execute().status == "refunded"
        else:
            with pytest.raises(AppError):
                execute()
    else:
        assert execute()["status"] == terminal
        if terminal == "succeeded":
            assert execute()["status"] == terminal
    dao.db.session.expire_all()
    if domain == "billing":
        assert order.status == (
            BILLING_ORDER_STATUS_REFUNDED
            if terminal == "succeeded"
            else BILLING_ORDER_STATUS_PAID
        )
        operation = order.metadata_json["refund_operation"]
        assert operation["response"]["status"] == terminal
    else:
        assert order.status == (
            ORDER_STATUS_REFUND if terminal == "succeeded" else ORDER_STATUS_SUCCESS
        )
    assert len(calls) == 1
