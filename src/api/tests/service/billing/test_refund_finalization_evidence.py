"""Keep billing refunds consistent with committed evidence and real SDK payloads."""

import hashlib
import hmac
import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC

import pytest
import stripe
from flask import Flask
from flaskr import dao
from flaskr.common import cache_provider
from flaskr.dao import uow
from flaskr.service.billing import checkout, webhooks
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
)
from flaskr.service.common.models import AppError
from flaskr.service.config import config_overrides
from flaskr.service.order.payment_providers.base import PaymentRefundResult
from flaskr.service.order.payment_providers.stripe import StripeProvider
from flaskr.util.datetime import now_utc

from tests.service.billing.test_contract_identity import _case
from tests.service.order.test_payment_contract_extension import (
    HostedFixtureProvider,
    integration_app,
)

__all__ = ["integration_app"]

_SECRET = "whsec_local_billing_refund"


def _stripe_payload(bid: str, status: str) -> dict:
    return {
        "id": "evt_billing_refund",
        "object": "event",
        "created": int(now_utc().replace(tzinfo=UTC).timestamp()),
        "livemode": False,
        "pending_webhooks": 1,
        "type": "refund.failed" if status == "failed" else "refund.updated",
        "data": {
            "object": {
                "id": "re_current",
                "object": "refund",
                "status": status,
                "metadata": {"bill_order_bid": bid},
                "destination_details": {
                    "type": "card",
                    "card": {"reference_status": "available", "reference": "123"},
                },
            }
        },
    }


def _stripe_notify(app: Flask, payload: dict) -> None:
    body = json.dumps(payload).encode()
    timestamp = payload["created"]
    signature = hmac.new(
        _SECRET.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    with app.app_context():
        result = webhooks.handle_billing_stripe_webhook(
            app, body, f"t={timestamp},v1={signature}"
        )
        assert result.status_code == 200, result


@pytest.mark.parametrize("integration_app", ["file"], indirect=True)
@pytest.mark.parametrize("provider_name", ["stripe", "fixture-hosted"])
@pytest.mark.parametrize(
    ("rpc_status", "callback_status", "timing", "expected"),
    [
        ("succeeded", "failed", "between_transactions", "failed"),
        ("succeeded", "canceled", "between_transactions", "canceled"),
        ("succeeded", "failed", "before_receipt", "failed"),
        ("pending", "succeeded", "between_transactions", "succeeded"),
        ("requires_action", "succeeded", "between_transactions", "succeeded"),
        ("pending", "failed", "between_transactions", "failed"),
        ("pending", "canceled", "between_transactions", "canceled"),
        ("pending", "requires_action", "between_transactions", "requires_action"),
        ("succeeded", "pending", "between_transactions", "succeeded"),
        ("failed", "pending", "between_transactions", "failed"),
        ("pending", "succeeded", "before_receipt", "succeeded"),
        ("pending", "succeeded", "after_finalization", "succeeded"),
    ],
)
def test_billing_finalization_uses_freshly_committed_refund_evidence(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    provider_name: str,
    rpc_status: str,
    callback_status: str,
    timing: str,
    expected: str,
) -> None:
    app = integration_app
    adapter = StripeProvider if provider_name == "stripe" else HostedFixtureProvider
    if provider_name == "stripe":
        # Keep the pinned SDK's actual Event/StripeObject types and verifier.
        monkeypatch.setattr(
            adapter, "_client_options", lambda _self, _app: (stripe, {})
        )
    else:
        monkeypatch.setattr(
            adapter,
            "definition",
            replace(
                adapter.definition,
                capabilities=replace(adapter.definition.capabilities, refund=True),
            ),
        )
        original_notification = adapter._notification

        def notification(self: HostedFixtureProvider, payload: dict) -> object:
            # The fixture parses its own wire format; retain the shared default
            # refund interpreter and the real signed generic callback route.
            result = original_notification(self, payload)
            return replace(
                result,
                order_bid=payload["order_bid"],
                refund_reference=payload["refund_reference"],
                refund_status=payload["refund_status"],
            )

        monkeypatch.setattr(adapter, "_notification", notification)
    order, _sub = _case(app, provider_name)
    bid = order.bill_order_bid
    grant_count = CreditLedgerEntry.query.filter_by(source_bid=bid).count()
    requests = []
    delivered = False
    callback_payload = None

    def current() -> tuple:
        # A separate ORM session sees only committed state, across all phases.
        with app.app_context():
            saved = BillingOrder.query.filter_by(bill_order_bid=bid).one()
            plan = BillingSubscription.query.filter_by(
                subscription_bid=saved.subscription_bid
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            return (
                deepcopy(saved.metadata_json.get("refund_operation", {})),
                saved.status,
                plan.status,
                plan.cancel_at_period_end,
                wallet.available_credits,
            )

    starting_credits = current()[-1]
    assert starting_credits > 0

    def notify() -> None:
        nonlocal delivered, callback_payload
        delivered = True
        if provider_name == "stripe":
            callback_payload = _stripe_payload(bid, callback_status)
            _stripe_notify(app, callback_payload)
        else:
            callback_payload = {
                "reference": "cs_bound",
                "order_bid": bid,
                "state": "unknown",
                "refund_reference": "re_current",
                "refund_status": callback_status,
            }
            body = json.dumps(callback_payload).encode()
            signature = hmac.new(b"fixture-key", body, hashlib.sha256).hexdigest()
            with app.test_client() as client:
                response = client.post(
                    "/api/callback/payments/fixture-hosted",
                    data=body,
                    headers={"X-Fixture-Signature": signature},
                )
                assert response.status_code == 200, response.get_data(as_text=True)
        if timing == "between_transactions" and callback_status in {
            "failed",
            "canceled",
        }:
            saved, state, plan, cancel, balance = current()
            assert saved["response"]["status"] == callback_status
            assert state == BILLING_ORDER_STATUS_PAID
            assert plan == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert cancel == 0
            assert balance == starting_credits

    def refund(_self: object, *, request: object, app: Flask) -> PaymentRefundResult:
        del app
        assert not uow.in_unit_of_work()
        requests.append(deepcopy(request))
        assert len(requests) == 1, (
            "Saved successful/pending refunds must not repeat RPC"
        )
        if timing == "before_receipt":
            notify()
        return PaymentRefundResult(
            "re_current", {"source": "rpc", "status": rpc_status}, rpc_status
        )

    monkeypatch.setattr(adapter, "refund_payment", refund)
    original_check = cache_provider.RenewableLockLease.check_owned

    def check_owned(lease: cache_provider.RenewableLockLease) -> None:
        original_check(lease)
        if (
            timing == "between_transactions"
            and not delivered
            and requests
            and not uow.in_unit_of_work()
        ):
            assert not dao.db.session().in_transaction()
            assert current()[0]["response"]["status"] == rpc_status
            notify()

    monkeypatch.setattr(cache_provider.RenewableLockLease, "check_owned", check_owned)
    with config_overrides({"STRIPE_WEBHOOK_SECRET": _SECRET}):
        if expected in {"failed", "canceled"}:
            with pytest.raises(AppError):
                checkout.refund_billing_order(app, "creator-1", bid, {})
        else:
            result = checkout.refund_billing_order(app, "creator-1", bid, {})
            assert result.status == (
                rpc_status
                if timing == "after_finalization"
                else "refunded"
                if expected == "succeeded"
                else expected
            )
            assert result.refund_reference_id == "re_current"
        if timing == "after_finalization":
            notify()
        assert delivered
        saved, state, plan, cancel, balance = current()
        assert saved["response"]["status"] == expected
        assert saved["response"]["provider_reference"] == "re_current"
        assert saved["response"]["raw_response"] == (
            callback_payload
            if expected == callback_status
            else {"source": "rpc", "status": rpc_status}
        )
        success = expected == "succeeded"
        assert saved["status"] == (
            "completed"
            if success
            else "provider_failed"
            if expected in {"failed", "canceled"}
            else "awaiting_confirmation"
        )
        assert state == (
            BILLING_ORDER_STATUS_REFUNDED if success else BILLING_ORDER_STATUS_PAID
        )
        assert plan == (
            BILLING_SUBSCRIPTION_STATUS_CANCELED
            if success
            else BILLING_SUBSCRIPTION_STATUS_ACTIVE
        )
        assert cancel == int(success)
        assert balance == (0 if success else starting_credits)
        if expected not in {"failed", "canceled"}:
            for _ in range(2):
                retried = checkout.refund_billing_order(app, "creator-1", bid, {})
                assert retried.status == ("refunded" if success else expected)
        assert len(requests) == 1
        dao.db.session.expire_all()
        assert CreditLedgerEntry.query.filter_by(source_bid=bid).count() == grant_count
        json.dumps(BillingOrder.query.filter_by(bill_order_bid=bid).one().metadata_json)


@pytest.mark.parametrize("status", ["pending", "failed", "succeeded"])
def test_signed_stripe_refund_payload_is_persisted_without_sdk_objects(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    app = integration_app
    order, _sub = _case(app, "stripe")
    bid = order.bill_order_bid
    monkeypatch.setattr(
        StripeProvider,
        "refund_payment",
        lambda *_args, **_kwargs: PaymentRefundResult("re_current", {}, "pending"),
    )
    assert checkout.refund_billing_order(app, "creator-1", bid, {}).status == "pending"
    monkeypatch.setattr(
        StripeProvider, "_client_options", lambda _self, _app: (stripe, {})
    )
    payload = _stripe_payload(bid, status)
    with config_overrides({"STRIPE_WEBHOOK_SECRET": _SECRET}):
        for _ in range(2):
            _stripe_notify(app, payload)
    dao.db.session.expire_all()
    response = order.metadata_json["refund_operation"]["response"]
    assert response["status"] == status
    assert response["raw_response"] == payload
    assert json.loads(json.dumps(response["raw_response"])) == payload
