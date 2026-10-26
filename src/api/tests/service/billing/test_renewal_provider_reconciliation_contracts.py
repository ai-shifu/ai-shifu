"""Exercise renewal reconciliation through real checkout and ledger transactions."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.billing import checkout, renewal
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RECONCILE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
)
from flaskr.service.billing.models import BillingOrder, CreditLedgerEntry, CreditWallet
from flaskr.service.billing.queries import calculate_billing_cycle_end
from flaskr.service.order.payment_providers.base import PaymentNotificationResult
from flaskr.util.datetime import now_utc, to_utc_iso

from tests.service.billing.renewal_execution_test_helpers import create_renewal_event
from tests.service.billing.test_checkout_state_transition_contracts import _seed

if TYPE_CHECKING:
    from flask import Flask


def _renewal_context(event_type: int, *, provider: str = "stripe") -> tuple:
    order, product, plan = _seed(provider=provider, subscription=True)
    boundary = now_utc() - timedelta(minutes=1)
    cycle_end = calculate_billing_cycle_end(product, cycle_start_at=boundary)
    plan.current_period_start_at = boundary - timedelta(days=30)
    plan.current_period_end_at = boundary
    plan.provider_subscription_id = "sub_" + uuid4().hex if provider == "stripe" else ""
    order.order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
    order.provider_reference_id = plan.provider_subscription_id
    order.metadata_json = {
        "provider_reference_type": "subscription" if provider == "stripe" else "charge",
        "renewal_cycle_start_at": to_utc_iso(boundary),
        "renewal_cycle_end_at": to_utc_iso(cycle_end),
    }
    event = create_renewal_event(
        uuid4().hex,
        plan.subscription_bid,
        plan.creator_bid,
        event_type=event_type,
        scheduled_at=boundary,
    )
    event.payload_json = {"bill_order_bid": order.bill_order_bid}
    db.session.add(event)
    db.session.commit()
    return order, plan, event, boundary, cycle_end


@pytest.mark.parametrize(
    "event_type",
    [
        BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
        BILLING_RENEWAL_EVENT_TYPE_RETRY,
        BILLING_RENEWAL_EVENT_TYPE_RECONCILE,
    ],
)
@pytest.mark.parametrize("outcome", ["paid", "failed", "transport"])
def test_provider_reconciliation_preserves_one_order_and_one_credit_grant_on_retry(
    event_type: int, outcome: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock()
    monkeypatch.setattr(checkout, "get_payment_provider", Mock(return_value=provider))
    with app.app_context():
        order, plan, event, boundary, cycle_end = _renewal_context(event_type)
        provider_payload = {
            "id": plan.provider_subscription_id,
            "status": "active" if outcome == "paid" else "past_due",
            "current_period_start": to_utc_iso(boundary),
            "current_period_end": to_utc_iso(cycle_end),
        }
        provider.sync_reference.return_value = PaymentNotificationResult(
            order.bill_order_bid, outcome, {"subscription": provider_payload}
        )
        if outcome == "transport":
            provider.sync_reference.side_effect = RuntimeError("provider timed out")
        result = renewal.run_billing_renewal_event(
            app, renewal_event_bid=event.renewal_event_bid
        )
        assert result.status == ("applied" if outcome == "paid" else "failed")
        db.session.expire_all()
        assert event.status == (
            BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
            if outcome == "paid"
            else BILLING_RENEWAL_EVENT_STATUS_FAILED
        )
        assert (
            order.status
            == {
                "paid": BILLING_ORDER_STATUS_PAID,
                "failed": BILLING_ORDER_STATUS_FAILED,
                "transport": BILLING_ORDER_STATUS_PENDING,
            }[outcome]
        )
        assert (
            BillingOrder.query.filter_by(
                subscription_bid=plan.subscription_bid,
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            ).count()
            == 1
        )
        assert CreditLedgerEntry.query.filter_by(
            creator_bid=plan.creator_bid
        ).count() == (1 if outcome == "paid" else 0)
        if outcome == "transport":
            assert event.last_error == "provider timed out"
            assert plan.current_period_start_at < boundary
        provider.sync_reference.side_effect = None
        provider_payload["status"] = "active"
        provider.sync_reference.return_value = PaymentNotificationResult(
            order.bill_order_bid, "paid", {"subscription": provider_payload}
        )
        retry = renewal.run_billing_renewal_event(
            app, renewal_event_bid=event.renewal_event_bid
        )
        assert retry.status == ("already_processed" if outcome == "paid" else "applied")
        db.session.expire_all()
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
        assert event.attempt_count == (1 if outcome == "paid" else 2)
        assert order.status == BILLING_ORDER_STATUS_PAID
        assert (
            CreditLedgerEntry.query.filter_by(creator_bid=plan.creator_bid).count() == 1
        )
        wallet = CreditWallet.query.filter_by(creator_bid=plan.creator_bid).one()
        assert wallet.available_credits == Decimal(5)
        assert plan.current_period_start_at == boundary
        assert provider.sync_reference.call_count == (1 if outcome == "paid" else 2)


@pytest.mark.parametrize(
    "event_type",
    [BILLING_RENEWAL_EVENT_TYPE_RETRY, BILLING_RENEWAL_EVENT_TYPE_RECONCILE],
)
def test_uncreated_pingxx_charge_remains_queued_without_provider_or_credit_mutation(
    event_type: int, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock()
    monkeypatch.setattr(checkout, "get_payment_provider", provider)
    with app.app_context():
        order, plan, event, _, _ = _renewal_context(event_type, provider="pingxx")
        result = renewal.run_billing_renewal_event(
            app, renewal_event_bid=event.renewal_event_bid
        )
        assert result.status == "queued_for_reconcile"
        db.session.expire_all()
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
        assert order.status == BILLING_ORDER_STATUS_PENDING
        assert (
            CreditLedgerEntry.query.filter_by(creator_bid=plan.creator_bid).count() == 0
        )
        provider.assert_not_called()


@pytest.mark.parametrize("selector", ["order", "event", "none"])
def test_retry_missing_target_returns_serializable_identity_without_claiming(
    selector: str, app: Flask
) -> None:
    missing = uuid4().hex
    kwargs = {
        "order": {"bill_order_bid": missing},
        "event": {"renewal_event_bid": missing},
        "none": {},
    }[selector]
    with app.app_context():
        result = renewal.retry_billing_renewal_event(app, **kwargs)
        payload = result.to_task_payload()
        assert payload["status"] == "order_not_found"
        assert payload.get("bill_order_bid") == (
            missing if selector == "order" else None
        )
        assert result["status"] == "order_not_found"


@pytest.mark.parametrize("unavailable", ["provider", "product"])
def test_renewal_without_charge_context_fails_before_creating_another_order(
    unavailable: str, app: Flask
) -> None:
    with app.app_context():
        order, plan, event, _, _ = _renewal_context(BILLING_RENEWAL_EVENT_TYPE_RENEWAL)
        if unavailable == "provider":
            plan.provider_subscription_id = ""
        else:
            plan.product_bid = "missing-product"
        db.session.commit()
        result = renewal.run_billing_renewal_event(
            app, renewal_event_bid=event.renewal_event_bid
        )
        assert result.status == "failed"
        db.session.expire_all()
        assert event.last_error == "renewal_order_context_unavailable"
        assert BillingOrder.query.filter_by(creator_bid=plan.creator_bid).count() == 1
        assert order.status == BILLING_ORDER_STATUS_PENDING


@pytest.mark.parametrize(
    "event_type",
    [BILLING_RENEWAL_EVENT_TYPE_EXPIRE, BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE],
)
def test_paid_renewal_with_missing_product_does_not_expire_or_downgrade_subscription(
    event_type: int, app: Flask
) -> None:
    with app.app_context():
        order, plan, event, _, _ = _renewal_context(event_type)
        plan.next_product_bid = uuid4().hex
        order.status = BILLING_ORDER_STATUS_PAID
        order.product_bid = uuid4().hex
        original_product = plan.product_bid
        db.session.commit()
        result = renewal.run_billing_renewal_event(
            app, renewal_event_bid=event.renewal_event_bid
        )
        assert result.status == "failed"
        db.session.expire_all()
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_FAILED
        assert plan.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert plan.product_bid == original_product
        assert (
            CreditLedgerEntry.query.filter_by(creator_bid=plan.creator_bid).count() == 0
        )
