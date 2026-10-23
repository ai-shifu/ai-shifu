"""Bind verified callbacks to the current payment rather than only its price."""

import json
import threading
from copy import deepcopy
from dataclasses import replace
from datetime import UTC

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import checkout
from flaskr.service.billing.consts import BILLING_ORDER_STATUS_PAID
from flaskr.service.billing.models import BillingOrder, CreditLedgerEntry
from flaskr.service.common.models import AppError
from flaskr.service.order import funs, raw_snapshots
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.util.datetime import now_utc

from tests.service.billing.billing_write_routes_test_helpers import (
    add_active_subscription,
)
from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    FixtureSnapshot,
    HostedFixtureProvider,
    _creation_case,
    _learner_sync_case,
    _notify,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.mark.parametrize("domain", ["learner", "billing-native", "billing-hosted"])
@pytest.mark.parametrize("state", ["paid", "failed", "canceled", "refunded"])
@pytest.mark.parametrize("reported", ["current", "foreign", "missing"])
def test_callback_reference_must_belong_to_the_current_attempt(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    domain: str,
    state: str,
    reported: str,
) -> None:
    app = integration_app
    provider = HostedFixtureProvider if domain == "billing-hosted" else FixtureProvider
    if domain == "billing-hosted":
        monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_MODELS, provider.channel)
        monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_BID_ATTRS, provider.channel)
    original = provider.create_payment

    def create(self: FixtureProvider, **kwargs: object) -> object:
        result = original(self, **kwargs)
        merchant = kwargs["request"].order_bid
        gateway = f"gateway-{merchant}"
        payload = self.attempts[merchant]
        payload["trade"] = {**payload, "reference": gateway}
        self.attempts[gateway] = payload
        return replace(result, provider_reference=gateway)

    monkeypatch.setattr(provider, "create_payment", create)
    notifications = []
    if domain == "learner":
        order, snapshot, notifications = _learner_sync_case(app, monkeypatch)
        merchant = snapshot.alipay_order_bid
        bid = order.order_bid
    else:
        add_active_subscription(app)
        with app.test_client() as client:
            created = client.post(
                "/api/billing/topups/checkout",
                json={
                    "product_bid": "bill-product-topup-small",
                    "payment_option": f"{provider.channel}:{provider.definition.default_channel}",
                },
            ).get_json(force=True)
        assert created["code"] == 0, created
        merchant = bid = created["data"]["bill_order_bid"]
        order = BillingOrder.query.filter_by(bill_order_bid=bid).one()
        snapshot = FixtureSnapshot.query.filter_by(bill_order_bid=bid).first()
    payload = FixtureProvider.attempts[merchant]
    with app.test_client() as client:
        if state == "refunded":
            payload["trade"]["state"] = "paid"
            assert _notify(client, provider.channel, merchant).status_code == 200
        dao.db.session.expire_all()
        before = (
            order.status,
            deepcopy(order.metadata_json) if domain != "learner" else None,
            len(notifications),
            CreditLedgerEntry.query.filter_by(source_bid=bid).count(),
        )
        snapshot_before = (
            (
                snapshot.status,
                snapshot.provider_attempt_id,
                snapshot.metadata_json,
                snapshot.raw_notification,
            )
            if snapshot
            else None
        )
        payload["trade"].update(
            state=state,
            reference={
                "current": f"gateway-{merchant}",
                "foreign": "another-same-priced-payment",
                "missing": None,
            }[reported],
        )
        for _ in range(2):
            response = _notify(client, provider.channel, merchant, state=state)
            assert response.status_code == (400 if reported == "foreign" else 200)
        dao.db.session.expire_all()
        if reported == "foreign":
            assert (
                order.status,
                deepcopy(order.metadata_json) if domain != "learner" else None,
                len(notifications),
                CreditLedgerEntry.query.filter_by(source_bid=bid).count(),
            ) == before
            if snapshot:
                assert (
                    snapshot.status,
                    snapshot.provider_attempt_id,
                    snapshot.metadata_json,
                    snapshot.raw_notification,
                ) == snapshot_before
        elif domain == "learner":
            assert (
                snapshot.status
                == {"paid": 1, "failed": 4, "canceled": 3, "refunded": 2}[state]
            )
            assert len(notifications) == int(state in {"paid", "refunded"})
        else:
            assert CreditLedgerEntry.query.filter_by(source_bid=bid).count() == int(
                state in {"paid", "refunded"}
            )
        if domain == "learner":
            assert snapshot.provider_attempt_id == f"gateway-{merchant}"
        else:
            assert order.provider_reference_id == f"gateway-{merchant}"


@pytest.mark.parametrize("integration_app", ["file"], indirect=True)
@pytest.mark.parametrize("domain", ["learner", "billing", "hosted"])
@pytest.mark.parametrize("identity", ["gateway", "merchant"])
@pytest.mark.parametrize("conflicting_response", [False, True, None])
@pytest.mark.parametrize("early_state", ["paid", "pending"])
def test_first_verified_callback_can_bind_an_unpersisted_gateway_reference(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    domain: str,
    identity: str,
    conflicting_response: bool | None,
    early_state: str,
) -> None:
    app = integration_app
    errors, observed, references = [], [], []
    provider = HostedFixtureProvider if domain == "hosted" else FixtureProvider
    if domain == "hosted":
        monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_MODELS, provider.channel)
        monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_BID_ATTRS, provider.channel)
    if domain == "learner":
        _creation_case(monkeypatch)
    else:
        add_active_subscription(app)
    original = provider.create_payment

    def create(self: FixtureProvider, **kwargs: object) -> object:
        result = original(self, **kwargs)
        merchant = kwargs["request"].order_bid
        references.append(merchant)
        gateway = f"early-gateway-{merchant}" if identity == "gateway" else merchant
        self.attempts[merchant]["trade"] = {
            **self.attempts[merchant],
            "state": early_state,
            "reference": gateway,
        }
        self.attempts[gateway] = self.attempts[merchant]

        def callback() -> None:
            try:
                with app.test_client() as client:
                    observed.append(
                        _notify(
                            client, self.channel, merchant, state=early_state
                        ).status_code
                    )
                    self.attempts[merchant]["trade"]["reference"] = (
                        "foreign-after-binding"
                    )
                    observed.append(
                        _notify(
                            client, self.channel, merchant, state=early_state
                        ).status_code
                    )
                    self.attempts[merchant]["trade"]["reference"] = gateway
                    observed.append(
                        _notify(
                            client, self.channel, merchant, state=early_state
                        ).status_code
                    )
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=callback, daemon=True)
        worker.start()
        worker.join(5)
        assert not worker.is_alive()
        return replace(
            result,
            provider_reference=""
            if conflicting_response is None
            else "conflicting-late-payment"
            if conflicting_response
            else gateway,
        )

    monkeypatch.setattr(provider, "create_payment", create)
    if domain == "learner":
        result = funs.generate_charge(
            app,
            "creation-order",
            "fixture_qr",
            "127.0.0.1",
            payment_channel="fixture-pay",
            expected_user="creator-1",
        )
        if early_state == "paid":
            assert result.__json__()["status"] == ORDER_STATUS_SUCCESS
        snapshot = FixtureSnapshot.query.filter_by(order_bid="creation-order").one()
        expected = (
            f"early-gateway-{snapshot.alipay_order_bid}"
            if identity == "gateway"
            else snapshot.alipay_order_bid
        )
        assert snapshot.provider_attempt_id == expected
        if conflicting_response:
            assert (
                json.loads(snapshot.metadata_json)["conflicting_creation_result"][
                    "provider_reference"
                ]
                == "conflicting-late-payment"
            )
            assert result.payment_action.type == "none"
    else:
        with app.test_request_context(base_url="https://fixture.test"):

            def create_checkout() -> object:
                return checkout.create_billing_topup_checkout(
                    app,
                    "creator-1",
                    {
                        "product_bid": "bill-product-topup-small",
                        "payment_option": f"{provider.channel}:{provider.definition.default_channel}",
                    },
                )

            if early_state == "paid" or conflicting_response:
                with pytest.raises(AppError):
                    create_checkout()
            else:
                assert create_checkout().status == "pending"
        order = BillingOrder.query.filter_by(payment_provider=provider.channel).one()
        assert order.status == (
            BILLING_ORDER_STATUS_PAID
            if early_state == "paid"
            else checkout.BILLING_ORDER_STATUS_PENDING
        )
        expected = (
            f"early-gateway-{order.bill_order_bid}"
            if identity == "gateway"
            else order.bill_order_bid
        )
        assert order.provider_reference_id == expected
        if domain == "billing-native":
            snapshot = FixtureSnapshot.query.filter_by(
                bill_order_bid=order.bill_order_bid
            ).one()
            assert snapshot.provider_attempt_id == expected
            assert snapshot.status == (1 if early_state == "paid" else 0)
            assert (
                json.loads(snapshot.raw_notification)["trade"]["state"] == early_state
            )
        if conflicting_response:
            assert (
                order.metadata_json["provider_checkout_attempts"][0]["result"][
                    "provider_reference"
                ]
                == "conflicting-late-payment"
            )
            assert (order.metadata_json.get("payment_action") or {}).get("type") in {
                None,
                "none",
            }
    assert errors == []
    assert observed == [200, 400, 200]
    if early_state == "pending":
        if domain == "learner":
            assert (
                funs.sync_native_payment_order(
                    app, "creation-order", expected_user="creator-1"
                )["status"]
                == 0
            )
        else:
            assert (
                checkout.sync_billing_order(
                    app, "creator-1", order.bill_order_bid, {}
                ).status
                == "pending"
            )
        merchant = references[0]
        FixtureProvider.attempts[merchant]["trade"]["state"] = "paid"
        with app.test_client() as client:
            for _ in range(2):
                assert _notify(client, provider.channel, merchant).status_code == 200
        dao.db.session.expire_all()
        if domain == "learner":
            assert (
                funs.Order.query.filter_by(order_bid="creation-order").one().status
                == ORDER_STATUS_SUCCESS
            )
        else:
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert order.provider_reference_id == expected
            assert (
                CreditLedgerEntry.query.filter_by(
                    source_bid=order.bill_order_bid
                ).count()
                == 1
            )


def test_learner_callback_cannot_fulfill_an_order_that_uses_a_different_provider(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = integration_app
    order, snapshot, notifications = _learner_sync_case(app, monkeypatch)
    with unit_of_work():
        order.payment_channel = "fixture-hosted"
    with app.test_client() as client:
        assert (
            _notify(client, "fixture-pay", snapshot.provider_attempt_id).status_code
            == 200
        )
    dao.db.session.expire_all()
    assert order.status != ORDER_STATUS_SUCCESS
    assert notifications == []
    assert snapshot.status == 1


def test_a_contract_only_callback_cannot_repoint_a_paid_checkout(
    integration_app: Flask,
) -> None:
    with integration_app.test_client() as client:
        created = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).get_json(force=True)
        assert created["code"] == 0, created
        bid = created["data"]["bill_order_bid"]
        assert _notify(client, "fixture-hosted", bid).status_code == 200
        before = CreditLedgerEntry.query.filter_by(source_bid=bid).count()
        FixtureProvider.attempts[bid]["trade"] = {
            "state": "unknown",
            "reference": "new-contract-reference",
        }
        now = int(now_utc().replace(tzinfo=UTC).timestamp())
        assert (
            _notify(
                client,
                "fixture-hosted",
                bid,
                state="unknown",
                contract={
                    "provider_reference": "new-contract-reference",
                    "status": "active",
                    "period_start": now,
                    "period_end": now + 86400,
                },
            ).status_code
            == 200
        )
    order = BillingOrder.query.filter_by(bill_order_bid=bid).one()
    assert order.status == BILLING_ORDER_STATUS_PAID
    assert order.provider_reference_id == bid
    assert CreditLedgerEntry.query.filter_by(source_bid=bid).count() == before


@pytest.mark.parametrize("reported", ["cs_early", ""])
def test_early_stripe_paid_callback_retains_raw_evidence_and_refund_reference(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    reported: str,
) -> None:
    from flaskr.service.billing import webhooks
    from flaskr.service.billing.provider_snapshots import refund_metadata
    from flaskr.service.order.models import StripeOrder
    from flaskr.service.order.payment_providers.base import (
        PaymentCreationResult,
        PaymentNotificationResult,
    )
    from flaskr.service.order.payment_providers.stripe import StripeProvider

    app = integration_app
    from flaskr.service.billing.consts import BILLING_ORDER_TYPE_TOPUP
    from flaskr.service.order.payment_providers.base import PaymentRequest

    from tests.service.billing.test_contract_identity import _case

    order, _sub = _case(app, "stripe", upgrade=True)
    with unit_of_work():
        order.provider_reference_id = ""
        order.order_type = BILLING_ORDER_TYPE_TOPUP
        order.subscription_bid = ""
        order.product_bid = "bill-product-topup-small"
    bid = order.bill_order_bid
    request = checkout._ProviderCheckoutRequest(
        bid,
        PaymentRequest(
            bid,
            "creator-1",
            "bill-product-topup-small",
            9900,
            "checkout_session",
            "cny",
            "credits",
            "credits",
            "127.0.0.1",
        ),
        subject="credits",
        payment_provider="stripe",
        payment_mode="payment",
        reused_existing_order=False,
        provider_price_metadata={},
    )
    bids = []

    def create(*_args: object, **kwargs: object) -> PaymentCreationResult:
        bid = kwargs["request"].order_bid
        bids.append(bid)
        obj = {
            "id": "cs_early",
            "payment_status": "paid",
            "amount_total": 9900,
            "currency": "cny",
            "payment_intent": "pi_early",
            "metadata": {"bill_order_bid": bid},
        }
        event = PaymentNotificationResult(
            bid,
            "checkout.session.completed",
            {"type": "checkout.session.completed", "data": {"object": obj}},
        )
        assert webhooks.apply_billing_stripe_notification(app, event).status_code == 200
        return PaymentCreationResult(
            provider_reference=reported,
            raw_response={"id": "cs_early", "payment_status": "unpaid"},
            checkout_session_id="cs_early",
        )

    monkeypatch.setattr(StripeProvider, "create_payment", create)
    with (
        app.test_request_context(base_url="https://fixture.test"),
        pytest.raises(AppError),
    ):
        checkout._run_provider_checkout(app, request)
    dao.db.session.expire_all()
    order = BillingOrder.query.filter_by(bill_order_bid=bids[0]).one()
    snapshot = StripeOrder.query.filter_by(bill_order_bid=bids[0]).one()
    assert order.status == BILLING_ORDER_STATUS_PAID
    assert order.provider_reference_id == "cs_early"
    assert snapshot.status == 1
    assert json.loads(snapshot.checkout_session_object)["payment_status"] == "paid"
    assert refund_metadata(order)["payment_intent_id"] == "pi_early"
    assert order.metadata_json["provider_checkout_attempts"][0]["status"] == 1
