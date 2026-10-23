"""Preserve contract recovery independently from payment of the next cycle."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import checkout
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
)
from flaskr.service.order.payment_providers import PaymentNotificationResult
from flaskr.util.datetime import now_utc, to_utc_iso

from tests.service.billing import billing_write_routes_test_helpers as helpers


@pytest.fixture
def billing_write_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict]:
    yield from helpers.billing_write_client(monkeypatch)


@pytest.mark.parametrize(
    ("provider_status", "cancel_at_period_end", "expected_order", "expected_contract"),
    [
        (
            "active",
            False,
            BILLING_ORDER_STATUS_PENDING,
            BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        ),
        (
            "active",
            True,
            BILLING_ORDER_STATUS_PENDING,
            BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
        ),
        (
            "trialing",
            False,
            BILLING_ORDER_STATUS_PENDING,
            BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        ),
        ("past_due", False, BILLING_ORDER_STATUS_FAILED, None),
        ("unpaid", False, BILLING_ORDER_STATUS_FAILED, None),
        ("incomplete_expired", False, BILLING_ORDER_STATUS_FAILED, None),
        ("canceled", False, BILLING_ORDER_STATUS_FAILED, None),
    ],
)
@pytest.mark.parametrize("returned_id", ["sub_existing_contract", "sub_wrong", None])
def test_stripe_renewal_query_preserves_current_contract_and_failure_details(
    billing_write_client: dict,
    monkeypatch: pytest.MonkeyPatch,
    provider_status: str,
    cancel_at_period_end: bool,
    expected_order: int,
    expected_contract: int | None,
    returned_id: str | None,
) -> None:
    """An unpaid future renewal must not block recovery of the current agreement."""
    app, client = billing_write_client["app"], billing_write_client["client"]
    start = now_utc().replace(microsecond=0) - timedelta(days=1)
    end = start + timedelta(days=30)
    helpers.add_active_subscription(
        app, current_period_start_at=start, current_period_end_at=end
    )
    with app.app_context(), unit_of_work():
        subscription = BillingSubscription.query.filter_by(
            creator_bid="creator-1"
        ).one()
        subscription.status = BILLING_SUBSCRIPTION_STATUS_PAST_DUE
        subscription.provider_subscription_id = "sub_existing_contract"
        db.session.add(
            BillingOrder(
                bill_order_bid="bill-next-cycle",
                creator_bid=subscription.creator_bid,
                subscription_bid=subscription.subscription_bid,
                product_bid=subscription.product_bid,
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                payment_provider="stripe",
                channel="subscription",
                provider_reference_id="sub_existing_contract",
                status=BILLING_ORDER_STATUS_PENDING,
                currency="CNY",
                payable_amount=100,
                paid_amount=0,
                metadata_json={
                    "provider_reference_type": "subscription",
                    "renewal_cycle_start_at": to_utc_iso(end),
                    "renewal_cycle_end_at": to_utc_iso(end + timedelta(days=30)),
                },
            )
        )

    provider = checkout.get_payment_provider("stripe")

    def sync_contract(**kwargs: object) -> PaymentNotificationResult:
        assert kwargs["reference_type"] == "subscription"
        assert kwargs["provider_reference"] == "sub_existing_contract"
        return PaymentNotificationResult(
            order_bid="",
            status="manual_sync",
            provider_payload={
                "subscription": {
                    "id": returned_id,
                    "status": provider_status,
                    "current_period_start": start,
                    "current_period_end": end,
                    "cancel_at_period_end": cancel_at_period_end,
                }
            },
        )

    monkeypatch.setattr(provider, "sync_reference", sync_contract)
    monkeypatch.setattr(checkout, "get_payment_provider", lambda _name: provider)
    result = client.post("/api/billing/orders/bill-next-cycle/sync").get_json(
        force=True
    )
    if returned_id != "sub_existing_contract":
        assert result["code"] != 0, result
        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid="bill-next-cycle").one()
            subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1"
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PENDING
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_PAST_DUE
            assert subscription.current_period_start_at == start
            assert subscription.current_period_end_at == end
            assert subscription.cancel_at_period_end == 0
            assert (
                CreditLedgerEntry.query.filter_by(source_bid="bill-next-cycle").count()
                == 0
            )
        return
    assert result["code"] == 0, result
    with app.app_context():
        order = BillingOrder.query.filter_by(bill_order_bid="bill-next-cycle").one()
        subscription = BillingSubscription.query.filter_by(
            creator_bid="creator-1"
        ).one()
        assert order.status == expected_order
        assert subscription.current_period_start_at == start
        assert subscription.current_period_end_at == end
        assert subscription.cancel_at_period_end == int(cancel_at_period_end)
        if expected_contract is not None:
            assert subscription.status == expected_contract
        if expected_order == BILLING_ORDER_STATUS_FAILED:
            assert order.failure_code == provider_status
            assert order.failure_message == (
                "Stripe subscription sync indicates renewal is not paid yet"
            )
        assert (
            CreditLedgerEntry.query.filter_by(source_bid="bill-next-cycle").count() == 0
        )
