"""Close registered payments consistently before replacement or repricing."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.service.billing import checkout, provider_recovery
from flaskr.service.billing.consts import BILLING_ORDER_STATUS_CANCELED
from flaskr.service.billing.models import BillingOrder
from flaskr.service.common.models import AppError
from flaskr.service.order import funs, payment_providers
from flaskr.service.order.consts import ORDER_STATUS_INIT, ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.payment_providers.base import PaymentCancellationResult

from tests.service.billing.billing_write_routes_test_helpers import (
    add_active_subscription,
)
from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    FixtureSnapshot,
    _learner_sync_case,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.mark.parametrize("consumer", ["learner", "billing", "recovery"])
@pytest.mark.parametrize("query", [False, True])
@pytest.mark.parametrize(
    "status",
    [
        "cancelled",
        "canceled",
        "closed",
        "expired",
        " CANCELED ",
        "pending",
        "failed",
        "unknown",
        "completed",
        "",
    ],
)
def test_registered_closure_outcomes(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    consumer: str,
    query: bool,
    status: str,
) -> None:
    app = integration_app
    accepted = status.strip().lower() in {"cancelled", "canceled", "closed", "expired"}
    monkeypatch.setattr(
        FixtureProvider,
        "definition",
        replace(
            FixtureProvider.definition,
            capabilities=replace(FixtureProvider.definition.capabilities, query=query),
        ),
    )
    monkeypatch.setitem(
        payment_providers.HISTORICAL_DEFINITIONS,
        "fixture-pay",
        FixtureProvider.definition,
    )
    if consumer == "learner":
        order, snapshot, _notifications = _learner_sync_case(app, monkeypatch)
        bid, reference = order.order_bid, snapshot.provider_attempt_id
    else:
        add_active_subscription(app)
        created = checkout.create_billing_topup_checkout(
            app,
            "creator-1",
            {
                "product_bid": "bill-product-topup-small",
                "payment_option": "fixture-pay:fixture_qr",
            },
        )
        bid = created.bill_order_bid
        order = BillingOrder.query.filter_by(bill_order_bid=bid).one()
        reference = order.provider_reference_id
        snapshot = FixtureSnapshot.query.filter_by(bill_order_bid=bid).one()
    before_status = order.status

    def close(**kwargs: object) -> PaymentCancellationResult:
        assert kwargs["provider_reference"] == reference
        if accepted:
            FixtureProvider.attempts[reference]["state"] = "canceled"
        return PaymentCancellationResult(reference, {"state": status}, status)

    cancel = Mock(side_effect=close)
    monkeypatch.setattr(FixtureProvider, "cancel_payment", cancel)

    def execute() -> None:
        if consumer == "learner":
            with funs.payment_lifecycle_lock(bid):
                assert funs.cancel_pending_payment_for_repricing(
                    app, bid, expected_user="creator-1"
                )
        elif consumer == "billing":
            checkout._close_manual_payment_before_replacement(app, "creator-1", bid)
        else:
            provider_recovery.reconcile_checkout_before_replacement(
                app,
                provider_name="fixture-pay",
                bill_order_bid=bid,
                reference=reference,
                client=FixtureProvider(),
            )

    if accepted:
        execute()
        if consumer != "recovery":
            assert snapshot.status == 3
            assert order.status == (
                ORDER_STATUS_INIT
                if consumer == "learner"
                else BILLING_ORDER_STATUS_CANCELED
            )
            # The closed attempt cannot be resumed or reused as a payable action.
            if consumer == "learner":
                replacement = funs.generate_charge(
                    app,
                    bid,
                    "fixture_qr",
                    "127.0.0.1",
                    payment_channel="fixture-pay",
                    expected_user="creator-1",
                )
                assert replacement is not None
                assert order.status == ORDER_STATUS_TO_BE_PAID
                assert FixtureSnapshot.query.filter_by(order_bid=bid).count() == 2
            else:
                replacement = checkout.create_billing_topup_checkout(
                    app,
                    "creator-1",
                    {
                        "product_bid": "bill-product-topup-small",
                        "payment_option": "fixture-pay:fixture_qr",
                    },
                )
                assert replacement.bill_order_bid != bid
                assert order.status == BILLING_ORDER_STATUS_CANCELED
    else:
        with pytest.raises(AppError):
            execute()
        assert snapshot.status == 0
        assert order.status == before_status
    cancel.assert_called_once()
