"""Exercise billing provider I/O against concurrently committed business state."""

import threading
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao import uow
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import checkout, provider_snapshots, subscriptions
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
)
from flaskr.service.common.models import AppError
from flaskr.service.order import raw_snapshots
from flaskr.util.datetime import now_utc

from tests.service.billing.billing_write_routes_test_helpers import (
    add_active_subscription,
)
from tests.service.order.test_payment_contract_extension import (
    HostedFixtureProvider,
    _notify,
    integration_app,
)

__all__ = ["integration_app"]


def _create_topup(app: Flask) -> str:
    add_active_subscription(app)
    with app.test_request_context(base_url="https://fixture.test"):
        return checkout.create_billing_topup_checkout(
            app,
            "creator-1",
            {
                "product_bid": "bill-product-topup-small",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).bill_order_bid


@pytest.mark.parametrize("integration_app", ["file"], indirect=True)
@pytest.mark.parametrize("state", ["pending", "failed", "canceled", "paid"])
def test_billing_query_cannot_overwrite_a_payment_callback(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    app = integration_app
    bid = _create_topup(app)
    errors = []

    def query(
        self: HostedFixtureProvider, *, provider_reference: str, **_kwargs: object
    ) -> object:
        assert not uow.in_unit_of_work()
        assert not dao.db.session().in_transaction()
        stale = {**deepcopy(self.attempts[provider_reference]), "state": state}

        def callback() -> None:
            try:
                with app.test_client() as client:
                    assert _notify(client, "fixture-hosted", bid).status_code == 200
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=callback, daemon=True)
        worker.start()
        worker.join(5)
        assert not worker.is_alive()
        assert errors == []
        return self._notification(stale)

    monkeypatch.setattr(HostedFixtureProvider, "sync_reference", query)
    result = checkout.sync_billing_order(app, "creator-1", bid, {})
    assert result.status == "paid"
    dao.db.session.expire_all()
    order = BillingOrder.query.filter_by(bill_order_bid=bid).one()
    assert order.status == BILLING_ORDER_STATUS_PAID
    assert order.metadata_json["latest_source"] == "webhook"
    assert CreditLedgerEntry.query.filter_by(source_bid=bid).count() == 1


@pytest.mark.parametrize("change", ["reference", "provider", "amount", "currency"])
def test_billing_query_revalidates_its_bound_attempt_and_terms(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    app = integration_app
    bid = _create_topup(app)

    def query(
        self: HostedFixtureProvider, *, provider_reference: str, **_kwargs: object
    ) -> object:
        stale = {**self.attempts[provider_reference], "state": "paid"}
        with app.app_context(), unit_of_work():
            current = BillingOrder.query.filter_by(bill_order_bid=bid).one()
            attribute, value = {
                "reference": ("provider_reference_id", "replacement-reference"),
                "provider": ("payment_provider", "fixture-pay"),
                "amount": ("payable_amount", current.payable_amount + 1),
                "currency": ("currency", "USD"),
            }[change]
            setattr(current, attribute, value)
        return self._notification(stale)

    monkeypatch.setattr(HostedFixtureProvider, "sync_reference", query)
    with pytest.raises(AppError):
        checkout.sync_billing_order(app, "creator-1", bid, {})
    dao.db.session.expire_all()
    assert (
        BillingOrder.query.filter_by(bill_order_bid=bid).one().status
        != BILLING_ORDER_STATUS_PAID
    )
    assert CreditLedgerEntry.query.filter_by(source_bid=bid).count() == 0


@pytest.mark.parametrize("operation", ["cancel", "resume"])
def test_billing_query_preserves_a_concurrent_subscription_management_action(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    app = integration_app
    now = int(now_utc().replace(tzinfo=UTC).timestamp())
    contract = {
        "provider_reference": "managed-contract",
        "status": "active",
        "cancel_at_period_end": operation == "resume",
        "period_start": now - 60,
        "period_end": now + 86400,
    }
    with app.test_client() as client:
        created = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).get_json(force=True)
        assert created["code"] == 0, created
        bid = created["data"]["bill_order_bid"]
        assert (
            _notify(client, "fixture-hosted", bid, contract=contract).status_code == 200
        )
    order = BillingOrder.query.filter_by(bill_order_bid=bid).one()
    subscription_bid = order.subscription_bid
    grants = CreditLedgerEntry.query.filter_by(source_bid=bid).count()

    def query(
        self: HostedFixtureProvider, *, provider_reference: str, **_kwargs: object
    ) -> object:
        assert not uow.in_unit_of_work()
        stale = {
            **deepcopy(self.attempts[provider_reference]),
            "state": "paid",
            "contract": contract,
        }
        manage = (
            subscriptions.cancel_billing_subscription
            if operation == "cancel"
            else subscriptions.resume_billing_subscription
        )
        with app.app_context():
            manage(app, "creator-1", {"subscription_bid": subscription_bid})
        return self._notification(stale)

    monkeypatch.setattr(HostedFixtureProvider, "sync_reference", query)
    assert checkout.sync_billing_order(app, "creator-1", bid, {}).status == "paid"
    dao.db.session.expire_all()
    subscription = BillingSubscription.query.filter_by(
        subscription_bid=subscription_bid
    ).one()
    assert subscription.status == (
        BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
        if operation == "cancel"
        else BILLING_SUBSCRIPTION_STATUS_ACTIVE
    )
    assert bool(subscription.cancel_at_period_end) == (operation == "cancel")
    assert CreditLedgerEntry.query.filter_by(source_bid=bid).count() == grants


@pytest.mark.parametrize("integration_app", ["file"], indirect=True)
@pytest.mark.parametrize("custom_writer", [False, True])
def test_late_hosted_checkout_receipt_survives_a_callback_without_native_storage(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, custom_writer: bool
) -> None:
    app = integration_app
    monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_MODELS, "fixture-hosted")
    monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_BID_ATTRS, "fixture-hosted")
    observed, errors = [], []
    if custom_writer:
        monkeypatch.setattr(provider_snapshots, "_CHECKOUT_WRITERS", {})

        def writer(order: BillingOrder, result: object, **kwargs: object) -> None:
            observed.append(
                (order.bill_order_bid, asdict(result), kwargs["raw_snapshot_status"])
            )

        provider_snapshots.register_checkout_writer("fixture-hosted", writer)
    original = HostedFixtureProvider.create_payment

    def create(self: HostedFixtureProvider, **kwargs: object) -> object:
        result = original(self, **kwargs)
        bid = kwargs["request"].order_bid

        def callback() -> None:
            try:
                with app.test_client() as client:
                    assert _notify(client, "fixture-hosted", bid).status_code == 200
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=callback, daemon=True)
        worker.start()
        worker.join(5)
        assert not worker.is_alive()
        assert errors == []
        return replace(result, provider_reference=f"late-gateway-{bid}")

    monkeypatch.setattr(HostedFixtureProvider, "create_payment", create)
    with pytest.raises(AppError):
        _create_topup(app)
    dao.db.session.expire_all()
    order = BillingOrder.query.filter_by(payment_provider="fixture-hosted").one()
    assert order.status == BILLING_ORDER_STATUS_PAID
    assert order.provider_reference_id == order.bill_order_bid
    assert (
        CreditLedgerEntry.query.filter_by(source_bid=order.bill_order_bid).count() == 1
    )
    if custom_writer:
        assert (
            observed[0][1]["provider_reference"]
            == f"late-gateway-{order.bill_order_bid}"
        )
        assert observed[0][2] == 0
    else:
        receipt = order.metadata_json["provider_checkout_attempts"][0]
        assert (
            receipt["result"]["provider_reference"]
            == f"late-gateway-{order.bill_order_bid}"
        )
        assert receipt["result"]["action"]["type"] == "redirect"
        assert receipt["result"]["raw_response"] == {"link": "https://fixture.test/pay"}
        assert receipt["status"] == 0
