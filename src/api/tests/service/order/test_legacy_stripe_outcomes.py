"""Verify independent legacy Stripe outcomes without issuing merchant requests."""

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import subscriptions, webhooks
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
)
from flaskr.service.billing.models import CreditLedgerEntry, CreditWallet
from flaskr.service.common.models import AppError
from flaskr.service.order import funs
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import StripeOrder
from flaskr.service.order.payment_providers.base import PaymentNotificationResult
from flaskr.service.order.payment_providers.stripe import StripeProvider

from tests.service.billing.test_contract_identity import _case
from tests.service.billing.test_subscription_command_outcomes import _run_command
from tests.service.order.test_learner_stripe_refund_retry_identity import _notify
from tests.service.order.test_order_payment_lifecycle_contracts import _order, _snapshot
from tests.service.order.test_payment_contract_extension import integration_app

__all__ = ["integration_app"]


@pytest.mark.parametrize("domain", ["learner", "billing"])
@pytest.mark.parametrize(
    "state", ["pending", "requires_action", "failed", "canceled", "unknown", ""]
)
def test_unrequested_refund_creation_requires_verified_success(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, domain: str, state: str
) -> None:
    app = integration_app
    provider = Mock()
    if domain == "learner":
        order = _order(status=ORDER_STATUS_SUCCESS)
        snapshot = _snapshot(order, status=1)
        monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
        for _ in range(2):
            response = _notify(
                app,
                provider,
                snapshot,
                "re_external",
                state=state,
                event_type="refund.created",
            )
            assert response["status"] == "acknowledged"
            assert order.status == ORDER_STATUS_SUCCESS
            assert funs.get_payment_details(app, order.order_bid)["status"] == 1
            assert snapshot.status == 1
            assert "refund_operation" not in json.loads(snapshot.metadata_json)
    else:
        order, sub = _case(app, "stripe")
        wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
        before = (sub.status, sub.cancel_at_period_end, wallet.available_credits)
        monkeypatch.setattr(StripeProvider, "refund_payment", provider.refund_payment)
        notice = PaymentNotificationResult(
            order.bill_order_bid,
            "refund.created",
            {
                "type": "refund.created",
                "data": {
                    "object": {
                        "id": "re_external",
                        "status": state,
                        "metadata": {"bill_order_bid": order.bill_order_bid},
                    }
                },
            },
        )
        for _ in range(2):
            assert (
                webhooks.apply_billing_stripe_notification(app, notice).status
                == "acknowledged"
            )
            dao.db.session.expire_all()
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert (
                StripeOrder.query.filter_by(bill_order_bid=order.bill_order_bid)
                .one()
                .status
                == 1
            )
            assert not order.metadata_json.get("refund_operation")
            assert (
                sub.status,
                sub.cancel_at_period_end,
                wallet.available_credits,
            ) == before
    provider.refund_payment.assert_not_called()


@pytest.mark.parametrize(
    ("action", "flag"), [("resume", "missing"), ("cancel", "string")]
)
def test_stripe_command_decoder_requires_the_actual_boolean_flag(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, action: str, flag: str
) -> None:
    _run_command(
        integration_app, monkeypatch, "stripe", action, "active", flag, reject=True
    )


@pytest.mark.parametrize("action", ["cancel", "resume"])
@pytest.mark.parametrize("identity", ["missing", "empty", "null", "foreign"])
def test_stripe_command_decoder_requires_returned_contract_identity(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, action: str, identity: str
) -> None:
    app = integration_app
    _order_row, sub = _case(app, "stripe")
    if action == "resume":
        with unit_of_work():
            sub.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
            sub.cancel_at_period_end = 1
    before = (
        sub.status,
        sub.cancel_at_period_end,
        deepcopy(sub.metadata_json),
        sub.last_renewed_at,
        sub.current_period_end_at,
    )
    ledger_before = CreditLedgerEntry.query.count()
    payload = {"status": "active", "cancel_at_period_end": action == "cancel"}
    if identity != "missing":
        payload["id"] = {"empty": "", "null": None, "foreign": "sub_foreign"}[identity]
    modify = Mock(return_value=SimpleNamespace(to_dict=lambda: payload))
    sdk = SimpleNamespace(Subscription=SimpleNamespace(modify=modify))
    monkeypatch.setattr(StripeProvider, "_client_options", lambda *_a: (sdk, {}))
    execute = getattr(subscriptions, f"{action}_billing_subscription")
    with pytest.raises(AppError):
        execute(app, "creator-1", {"subscription_bid": sub.subscription_bid})
    modify.assert_called_once_with(
        "sub_current",
        cancel_at_period_end=action == "cancel",
        metadata={"subscription_bid": sub.subscription_bid},
    )
    dao.db.session.expire_all()
    assert (
        sub.status,
        sub.cancel_at_period_end,
        sub.metadata_json,
        sub.last_renewed_at,
        sub.current_period_end_at,
    ) == before
    assert CreditLedgerEntry.query.count() == ledger_before
