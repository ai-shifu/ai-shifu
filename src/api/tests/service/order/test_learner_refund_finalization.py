"""Keep fresh refund evidence authoritative across the final transaction gap."""

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
from flaskr.dao import uow
from flaskr.service.config import config_overrides
from flaskr.service.order import funs
from flaskr.service.order.consts import ORDER_STATUS_REFUND, ORDER_STATUS_SUCCESS
from flaskr.service.order.payment_providers.base import PaymentRefundResult
from flaskr.service.order.payment_providers.stripe import StripeProvider
from flaskr.util.datetime import now_utc

from tests.service.order.test_order_payment_lifecycle_contracts import _order, _snapshot
from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    _learner_sync_case,
    _notify,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.mark.parametrize("integration_app", ["file"], indirect=True)
@pytest.mark.parametrize("provider_name", ["stripe", "fixture-pay"])
@pytest.mark.parametrize(
    ("rpc_status", "callback_status", "timing", "expected"),
    [
        ("pending", "succeeded", "before_receipt", "succeeded"),
        ("pending", "succeeded", "between_transactions", "succeeded"),
        ("pending", "succeeded", "after_finalization", "succeeded"),
        ("requires_action", "succeeded", "between_transactions", "succeeded"),
        ("pending", "failed", "between_transactions", "failed"),
        ("pending", "canceled", "between_transactions", "canceled"),
        ("succeeded", "pending", "between_transactions", "succeeded"),
        ("failed", "pending", "between_transactions", "failed"),
        ("succeeded", "failed", "between_transactions", "failed"),
        ("pending", "requires_action", "between_transactions", "requires_action"),
    ],
)
def test_finalization_reconciles_fresh_refund_evidence(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    provider_name: str,
    rpc_status: str,
    callback_status: str,
    timing: str,
    expected: str,
) -> None:
    app = integration_app
    if provider_name == "stripe":
        adapter = StripeProvider
        order = _order(status=ORDER_STATUS_SUCCESS)
        snapshot = _snapshot(order, status=1)
        # Real SDK signature verification remains enabled; no network is used.
        monkeypatch.setattr(
            StripeProvider, "_client_options", lambda _self, _app: (stripe, {})
        )
    else:
        adapter = FixtureProvider
        order, snapshot, _notifications = _learner_sync_case(app, monkeypatch)
        with app.test_client() as client:
            assert (
                _notify(client, provider_name, snapshot.provider_attempt_id).status_code
                == 200
            )
        monkeypatch.setattr(
            adapter,
            "definition",
            replace(
                adapter.definition,
                capabilities=replace(adapter.definition.capabilities, refund=True),
            ),
        )
        original_notification = FixtureProvider._notification

        def notification(self: FixtureProvider, payload: dict) -> object:
            # Parsing belongs to the fixture adapter; use the actual shared
            # default event interpreter and actual signed callback route.
            return replace(
                original_notification(self, payload),
                refund_reference=payload.get("refund_reference", ""),
                refund_status=payload.get("refund_status"),
            )

        monkeypatch.setattr(FixtureProvider, "_notification", notification)
    bid = order.order_bid
    snapshot_model = type(snapshot)
    requests, observed = [], []
    delivered = False
    callback_payload = None
    secret = "whsec_local_refund_finalization"

    def operation() -> dict:
        with app.app_context():
            raw = snapshot_model.query.filter_by(order_bid=bid).one()
            return json.loads(raw.metadata_json)["refund_operation"]

    def notify() -> None:
        nonlocal delivered, callback_payload
        delivered = True
        timestamp = int(now_utc().replace(tzinfo=UTC).timestamp())
        if provider_name == "stripe":
            callback_payload = {
                "id": "evt_finalization",
                "object": "event",
                "created": timestamp,
                "type": "refund.updated",
                "data": {
                    "object": {
                        "id": "re_current",
                        "object": "refund",
                        "status": callback_status,
                        "payment_intent": snapshot.payment_intent_id,
                        "charge": snapshot.latest_charge_id,
                        "metadata": {
                            "order_bid": bid,
                            "stripe_order_bid": snapshot.stripe_order_bid,
                        },
                    }
                },
            }
            body = json.dumps(callback_payload).encode()
            signature = hmac.new(
                secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256
            ).hexdigest()
            with app.app_context():
                result, status = funs.handle_stripe_webhook(
                    app, body, f"t={timestamp},v1={signature}"
                )
                assert status == 200, result
        else:
            callback_payload = {
                **FixtureProvider.attempts[snapshot.provider_attempt_id],
                "state": "refunded" if callback_status == "succeeded" else "unknown",
                "refund_reference": "re_current",
                "refund_status": callback_status,
            }
            body = json.dumps(callback_payload).encode()
            signature = hmac.new(b"fixture-key", body, hashlib.sha256).hexdigest()
            with app.test_client() as client:
                assert (
                    client.post(
                        f"/api/callback/payments/{provider_name}",
                        data=body,
                        headers={"X-Fixture-Signature": signature},
                    ).status_code
                    == 200
                )
        observed.append(operation())
        assert observed[-1]["status"] == callback_status

    def refund(_self: object, *, request: object, app: Flask) -> PaymentRefundResult:
        del app
        requests.append(deepcopy(request))
        assert len(requests) == 1, (
            "Finalized receipts must not cause another refund RPC"
        )
        if timing == "before_receipt":
            notify()
        return PaymentRefundResult(
            "re_current", {"source": "rpc", "status": rpc_status}, rpc_status
        )

    monkeypatch.setattr(adapter, "refund_payment", refund)
    original_check = funs._PaymentLifecycleLease.check_owned

    def check_owned(lease: object) -> None:
        original_check(lease)
        if (
            timing == "between_transactions"
            and not delivered
            and requests
            and not uow.in_unit_of_work()
        ):
            assert not dao.db.session().in_transaction()
            saved = operation()
            assert saved["response"]["status"] == rpc_status
            notify()

    monkeypatch.setattr(funs._PaymentLifecycleLease, "check_owned", check_owned)
    with config_overrides({"STRIPE_WEBHOOK_SECRET": secret}):
        result = funs.refund_order_payment(app, bid)
        if timing == "after_finalization":
            assert result["status"] == rpc_status
            notify()
        else:
            assert result["status"] == expected
        assert delivered
        assert result["refund_id"] == "re_current"
        dao.db.session.expire_all()
        current = operation()
        assert current["status"] == expected
        assert current["provider_reference"] == "re_current"
        assert current["response"]["status"] == expected
        assert current["response"]["provider_reference"] == "re_current"
        callback_wins = expected == callback_status
        assert current["response"]["raw_response"] == (
            callback_payload
            if callback_wins
            else {"source": "rpc", "status": rpc_status}
        )
        assert order.status == (
            ORDER_STATUS_REFUND if expected == "succeeded" else ORDER_STATUS_SUCCESS
        )
        assert snapshot.status == {"succeeded": 2, "failed": 4, "canceled": 4}.get(
            expected, 1
        )
        assert (
            funs.get_payment_details(app, bid, order.user_bid)["status"]
            == snapshot.status
        )
        if expected not in {"failed", "canceled"}:
            for _ in range(2):
                assert funs.refund_order_payment(app, bid)["status"] == expected
        assert len(requests) == 1
