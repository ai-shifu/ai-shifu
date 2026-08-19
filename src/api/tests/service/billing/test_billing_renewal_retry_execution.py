from __future__ import annotations

from datetime import timedelta

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingRenewalEvent,
)
from flaskr.service.billing.renewal import (
    run_billing_renewal_event,
)
from flaskr.util.datetime import now_utc
from tests.service.billing.renewal_execution_test_helpers import (
    create_renewal_event,
    create_renewal_subscription,
)

pytest_plugins = ["tests.service.billing.renewal_execution_app_fixture"]


def test_run_billing_renewal_event_retries_latest_failed_renewal_order(
    billing_renewal_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.renewal.sync_billing_order",
        lambda app, creator_bid, bill_order_bid, payload: {
            "status": "paid",
            "creator_bid": creator_bid,
            "bill_order_bid": bill_order_bid,
        },
    )

    cycle_start = now_utc()
    cycle_end = cycle_start + timedelta(days=30)
    with billing_renewal_app.app_context():
        subscription = create_renewal_subscription(
            "sub-retry-1",
            current_period_end_at=cycle_start,
        )
        subscription.provider_subscription_id = "sub_provider_retry_1"
        renewal_order = BillingOrder(
            bill_order_bid="bill-renewal-retry-1",
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=9900,
            paid_amount=0,
            payment_provider="stripe",
            channel="subscription",
            provider_reference_id="sub_provider_retry_1",
            status=BILLING_ORDER_STATUS_FAILED,
            metadata_json={
                "provider_reference_type": "subscription",
                "renewal_cycle_start_at": cycle_start.isoformat(),
                "renewal_cycle_end_at": cycle_end.isoformat(),
            },
        )
        event = create_renewal_event(
            "renewal-retry-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_RETRY,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(renewal_order)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-retry-1",
    )

    assert payload["status"] == "applied"
    assert payload["event_status"] == "succeeded"

    with billing_renewal_app.app_context():
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-retry-1"
        ).one()
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
