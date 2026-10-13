"""Reject foreign contract state while preserving admitted paid upgrade handoffs."""

from copy import deepcopy
from datetime import UTC, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import checkout, webhooks
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
)
from flaskr.service.order.payment_providers.base import PaymentNotificationResult
from flaskr.service.order.payment_providers.contracts import (
    PaymentFacts,
    SubscriptionFacts,
)
from flaskr.util.datetime import now_utc

from tests.service.order.test_payment_contract_extension import integration_app

__all__ = ["integration_app"]


def _case(
    app: Flask, provider: str, *, upgrade: bool = False, empty: bool = False
) -> tuple:
    now = now_utc()
    with unit_of_work():
        sub = BillingSubscription(
            subscription_bid="bound-subscription",
            creator_bid="creator-1",
            product_bid="bill-product-plan-monthly",
            billing_provider=provider,
            provider_subscription_id="" if empty else "sub_current",
            provider_customer_id="customer-current",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=now - timedelta(days=1),
            current_period_end_at=now + timedelta(days=20),
            metadata_json={},
            cancel_at_period_end=0,
        )
        order = BillingOrder(
            bill_order_bid="bound-order",
            creator_bid="creator-1",
            product_bid="bill-product-plan-monthly",
            subscription_bid=sub.subscription_bid,
            payment_provider=provider,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE
            if upgrade
            else BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            status=BILLING_ORDER_STATUS_PENDING,
            currency="CNY",
            payable_amount=9900,
            paid_amount=0 if upgrade else 9900,
            provider_reference_id="cs_bound",
            channel="checkout_session" if provider == "stripe" else "fixture_checkout",
            metadata_json={},
        )
        dao.db.session.add_all([sub, order])
    if not upgrade:
        webhooks.apply_billing_provider_notification(
            app,
            provider,
            _notification(
                provider, "" if empty else "sub_current", "active", payment=True
            ),
        )
    return order, sub


def _notification(
    provider: str,
    reference: str,
    state: str,
    *,
    payment: bool = False,
    source: str = "webhook",
) -> PaymentNotificationResult:
    now = int(now_utc().replace(tzinfo=UTC).timestamp())
    if provider == "stripe":
        obj = {
            "id": "cs_bound" if payment else reference,
            "status": state,
            "created": now,
            "metadata": {
                "bill_order_bid": "bound-order",
                "creator_bid": "creator-1",
                "product_bid": "bill-product-plan-monthly",
            },
            "subscription": reference,
            "customer": "customer-current",
            "payment_status": "paid",
            "amount_total": 9900,
            "currency": "cny",
            "current_period_start": now,
            "current_period_end": now + 30 * 86400,
        }
        event_type = (
            "checkout.session.completed" if payment else "customer.subscription.updated"
        )
        payload = (
            {"checkout_session": obj, "payment_intent": {}}
            if source == "query"
            else {"type": event_type, "data": {"object": obj}}
        )
        return PaymentNotificationResult("bound-order", event_type, payload)
    return PaymentNotificationResult(
        "bound-order",
        "fixture.contract",
        {"receipt": "verified-contract"},
        facts=PaymentFacts(
            state="paid" if payment else "unknown",
            provider_reference="cs_bound" if payment else None,
            order_amount=9900 if payment else None,
            currency="CNY" if payment else None,
        ),
        subscription=SubscriptionFacts(
            reference, state, period_start=now, period_end=now + 30 * 86400
        ),
    )


@pytest.mark.parametrize("provider", ["stripe", "fixture-hosted"])
@pytest.mark.parametrize("state", ["active", "past_due", "paused", "canceled"])
@pytest.mark.parametrize("reported", ["current", "foreign", "missing"])
def test_contract_callback_cannot_replace_a_bound_subscription(
    integration_app: Flask, provider: str, state: str, reported: str
) -> None:
    order, sub = _case(integration_app, provider)
    before = (
        sub.status,
        sub.provider_subscription_id,
        sub.current_period_start_at,
        sub.current_period_end_at,
        deepcopy(sub.metadata_json),
        deepcopy(order.metadata_json),
    )
    event = _notification(
        provider,
        {"current": "sub_current", "foreign": "sub_foreign", "missing": ""}[reported],
        state,
    )
    for _ in range(2):
        if reported == "foreign":
            with pytest.raises(RuntimeError, match="contract reference mismatch"):
                webhooks.apply_billing_provider_notification(
                    integration_app, provider, event
                )
        else:
            webhooks.apply_billing_provider_notification(
                integration_app, provider, event
            )
    dao.db.session.expire_all()
    if reported == "foreign":
        assert (
            sub.status,
            sub.provider_subscription_id,
            sub.current_period_start_at,
            sub.current_period_end_at,
            sub.metadata_json,
            order.metadata_json,
        ) == before
    assert sub.provider_subscription_id == "sub_current"
    assert order.provider_reference_id == "cs_bound"
    assert CreditLedgerEntry.query.count() == 1


@pytest.mark.parametrize("provider", ["stripe", "fixture-hosted"])
def test_first_contract_binding_is_allowed_but_a_later_foreign_contract_is_rejected(
    integration_app: Flask, provider: str
) -> None:
    _order, sub = _case(integration_app, provider, empty=True)
    event = _notification(provider, "sub_first", "active")
    webhooks.apply_billing_provider_notification(integration_app, provider, event)
    assert sub.provider_subscription_id == "sub_first"
    with pytest.raises(RuntimeError, match="contract reference mismatch"):
        webhooks.apply_billing_provider_notification(
            integration_app,
            provider,
            _notification(provider, "sub_foreign", "canceled"),
        )
    dao.db.session.expire_all()
    assert sub.provider_subscription_id == "sub_first"
    assert sub.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE


@pytest.mark.parametrize("provider", ["stripe", "fixture-hosted"])
@pytest.mark.parametrize("source", ["webhook", "query"])
def test_verified_paid_upgrade_can_replace_its_contract_once(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, provider: str, source: str
) -> None:
    app = integration_app
    order, sub = _case(app, provider, upgrade=True)
    event = _notification(
        provider, "sub_upgrade", "active", payment=True, source=source
    )
    if source == "query":
        monkeypatch.setattr(
            checkout,
            "get_payment_provider",
            lambda _p: SimpleNamespace(sync_reference=lambda **_k: event),
        )
    for _ in range(2):
        if source == "query":
            assert (
                checkout.sync_billing_order(
                    app, "creator-1", order.bill_order_bid, {}
                ).status
                == "paid"
            )
        else:
            webhooks.apply_billing_provider_notification(app, provider, event)
    assert order.status == BILLING_ORDER_STATUS_PAID
    assert sub.provider_subscription_id == "sub_upgrade"
    assert (
        CreditLedgerEntry.query.filter_by(source_bid=order.bill_order_bid).count() == 1
    )
    with pytest.raises(RuntimeError, match="contract reference mismatch"):
        webhooks.apply_billing_provider_notification(
            app, provider, _notification(provider, "sub_current", "canceled")
        )
    dao.db.session.expire_all()
    assert sub.provider_subscription_id == "sub_upgrade"
    assert sub.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE


@pytest.mark.parametrize("state", ["active", "past_due", "canceled"])
def test_payment_query_cannot_rebind_an_already_paid_contract(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    app = integration_app
    order, sub = _case(app, "fixture-hosted")
    before = (
        sub.status,
        sub.provider_subscription_id,
        deepcopy(sub.metadata_json),
        deepcopy(order.metadata_json),
    )
    event = _notification(
        "fixture-hosted", "sub_foreign", state, payment=True, source="query"
    )
    monkeypatch.setattr(
        checkout,
        "get_payment_provider",
        lambda _p: SimpleNamespace(sync_reference=lambda **_k: event),
    )
    with pytest.raises(RuntimeError, match="contract reference mismatch"):
        checkout.sync_billing_order(app, "creator-1", order.bill_order_bid, {})
    dao.db.session.expire_all()
    assert (
        sub.status,
        sub.provider_subscription_id,
        sub.metadata_json,
        order.metadata_json,
    ) == before
    assert (
        CreditLedgerEntry.query.filter_by(source_bid=order.bill_order_bid).count() == 1
    )


@pytest.mark.parametrize("source", ["webhook", "query"])
@pytest.mark.parametrize(
    "state",
    [
        "active",
        "trialing",
        "past_due",
        "paused",
        "canceled",
        "unpaid",
        "incomplete_expired",
    ],
)
def test_stripe_confirmed_contract_survives_paid_grant_repair(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    state: str,
) -> None:
    from flaskr.service.billing.consts import (
        BILLING_SUBSCRIPTION_STATUS_CANCELED,
        BILLING_SUBSCRIPTION_STATUS_EXPIRED,
        BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
        BILLING_SUBSCRIPTION_STATUS_PAUSED,
    )

    app = integration_app
    order, sub = _case(app, "stripe")
    event = _notification("stripe", "sub_current", state)
    if source == "query":
        with unit_of_work():
            order.provider_reference_id = "sub_current"
            order.metadata_json = {
                **order.metadata_json,
                "provider_reference_type": "subscription",
            }
        event = PaymentNotificationResult(
            order.bill_order_bid,
            "manual_sync",
            {"subscription": event.provider_payload["data"]["object"]},
        )
        monkeypatch.setattr(
            checkout,
            "get_payment_provider",
            lambda _p: SimpleNamespace(sync_reference=lambda **_k: event),
        )
    for _ in range(2):
        if source == "query":
            checkout.sync_billing_order(app, "creator-1", order.bill_order_bid, {})
        else:
            webhooks.apply_billing_stripe_notification(app, event)
    dao.db.session.expire_all()
    assert (
        sub.status
        == {
            "active": BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            "trialing": BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            "past_due": BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
            "unpaid": BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
            "paused": BILLING_SUBSCRIPTION_STATUS_PAUSED,
            "canceled": BILLING_SUBSCRIPTION_STATUS_CANCELED,
            "incomplete_expired": BILLING_SUBSCRIPTION_STATUS_EXPIRED,
        }[state]
    )
    assert sub.metadata_json["provider_contract_confirmed"] is True
    assert order.status == BILLING_ORDER_STATUS_PAID
    assert (
        CreditLedgerEntry.query.filter_by(source_bid=order.bill_order_bid).count() == 1
    )
