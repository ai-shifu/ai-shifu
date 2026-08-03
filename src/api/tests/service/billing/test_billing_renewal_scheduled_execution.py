from __future__ import annotations


from datetime import datetime, timedelta
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing import renewal as billing_renewal
from flaskr.service.billing.consts import (
    ALLOCATION_INTERVAL_PER_CYCLE,
    BILLING_INTERVAL_DAY,
    BILLING_MODE_RECURRING,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from flaskr.service.billing.renewal import (
    run_billing_renewal_event,
)
from flaskr.util.datetime import now_utc


from tests.service.billing.renewal_execution_test_helpers import (
    _add_paid_renewal_with_reserved_grant,
    _create_renewal_event,
    _create_subscription,
    _self_managed_cycle_end_after_boundary,
)


pytest_plugins = ["tests.service.billing.renewal_execution_app_fixture"]


def test_run_billing_renewal_event_releases_future_event_back_to_pending(
    billing_renewal_app: Flask,
) -> None:
    with billing_renewal_app.app_context():
        subscription = _create_subscription("sub-future-1")
        event = _create_renewal_event(
            "renewal-future-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
            scheduled_at=now_utc() + timedelta(minutes=30),
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-future-1",
    )

    assert payload["status"] == "deferred_until_scheduled_at"
    assert payload["event_status"] == "pending"
    assert payload["attempt_count"] == 1

    with billing_renewal_app.app_context():
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-future-1"
        ).one()
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
        assert event.attempt_count == 1
        assert event.processed_at is None


def test_run_billing_renewal_event_does_not_advance_future_paid_renewal(
    billing_renewal_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_at = datetime(2026, 4, 10, 0, 0, 0)
    current_cycle_start = datetime(2026, 4, 1, 0, 0, 0)
    current_cycle_end = datetime(2026, 5, 1, 0, 0, 0)
    next_cycle_end = datetime(2026, 6, 1, 0, 0, 0)
    monkeypatch.setattr(billing_renewal, "now_utc", lambda: current_at)

    with billing_renewal_app.app_context():
        subscription_bid, order_bid, event_bid, bucket_bid, ledger_bid = (
            _add_paid_renewal_with_reserved_grant(
                suffix="future",
                current_cycle_start=current_cycle_start,
                current_cycle_end=current_cycle_end,
                next_cycle_end=next_cycle_end,
                scheduled_at=current_cycle_end,
                paid_at=current_at - timedelta(days=1),
            )
        )
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid=event_bid,
    )

    assert payload["status"] == "deferred_until_scheduled_at"
    assert payload["event_status"] == "pending"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid=subscription_bid
        ).one()
        order = BillingOrder.query.filter_by(bill_order_bid=order_bid).one()
        event = BillingRenewalEvent.query.filter_by(renewal_event_bid=event_bid).one()
        bucket = CreditWalletBucket.query.filter_by(wallet_bucket_bid=bucket_bid).one()
        grant_entry = CreditLedgerEntry.query.filter_by(ledger_bid=ledger_bid).one()

        assert event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
        assert event.processed_at is None
        assert subscription.current_period_start_at == current_cycle_start
        assert subscription.current_period_end_at == current_cycle_end
        assert "applied_cycle_start_at" not in order.metadata_json
        assert "applied_cycle_end_at" not in order.metadata_json
        assert bucket.available_credits == Decimal("3.0000000000")
        assert bucket.reserved_credits == Decimal("5.0000000000")
        assert grant_entry.metadata_json["bucket_credit_state"] == "reserved"


def test_run_billing_renewal_event_executes_at_exact_scheduled_time(
    billing_renewal_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_cycle_start = datetime(2026, 4, 1, 0, 0, 0)
    current_cycle_end = datetime(2026, 5, 1, 0, 0, 0)
    next_cycle_end = datetime(2026, 6, 1, 0, 0, 0)
    monkeypatch.setattr(billing_renewal, "now_utc", lambda: current_cycle_end)

    with billing_renewal_app.app_context():
        subscription_bid, order_bid, event_bid, bucket_bid, ledger_bid = (
            _add_paid_renewal_with_reserved_grant(
                suffix="equal",
                current_cycle_start=current_cycle_start,
                current_cycle_end=current_cycle_end,
                next_cycle_end=next_cycle_end,
                paid_at=current_cycle_end - timedelta(days=5),
                scheduled_at=current_cycle_end,
            )
        )
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid=event_bid,
    )

    assert payload["status"] == "applied"
    assert payload["subscription_status"] == "active"
    assert payload["event_status"] == "succeeded"
    assert payload["bill_order_bid"] == order_bid

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid=subscription_bid
        ).one()
        event = BillingRenewalEvent.query.filter_by(renewal_event_bid=event_bid).one()
        bucket = CreditWalletBucket.query.filter_by(wallet_bucket_bid=bucket_bid).one()
        grant_entry = CreditLedgerEntry.query.filter_by(ledger_bid=ledger_bid).one()

        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert subscription.current_period_start_at == current_cycle_end
        assert subscription.current_period_end_at == next_cycle_end
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
        assert event.processed_at is not None
        assert bucket.source_bid == order_bid
        assert bucket.available_credits == Decimal("5.0000000000")
        assert bucket.reserved_credits == Decimal("0")
        assert grant_entry.consumable_from == current_cycle_end
        assert grant_entry.expires_at == next_cycle_end
        assert grant_entry.metadata_json["bucket_credit_state"] == "available"


def test_run_billing_renewal_event_queues_subscription_renewal_order(
    billing_renewal_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.renewal.sync_billing_order",
        lambda app, creator_bid, bill_order_bid, payload: {
            "status": "pending",
            "creator_bid": creator_bid,
            "bill_order_bid": bill_order_bid,
        },
    )

    with billing_renewal_app.app_context():
        subscription = _create_subscription("sub-unsupported-1")
        subscription.provider_subscription_id = "sub_provider_unsupported_1"
        subscription_bid = subscription.subscription_bid
        event = _create_renewal_event(
            "renewal-unsupported-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-unsupported-1",
    )

    assert payload["status"] == "queued_for_reconcile"
    assert payload["event_status"] == "succeeded"
    assert payload["bill_order_bid"]

    with billing_renewal_app.app_context():
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-unsupported-1"
        ).one()
        order = BillingOrder.query.filter_by(
            bill_order_bid=payload["bill_order_bid"]
        ).one()
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
        assert order.subscription_bid == subscription_bid
        assert order.provider_reference_id == "sub_provider_unsupported_1"
        assert order.metadata_json["provider_reference_type"] == "subscription"


def test_run_billing_renewal_event_queues_pingxx_order_without_provider_sync(
    billing_renewal_app: Flask,
) -> None:
    cycle_end = now_utc() - timedelta(hours=1)
    with billing_renewal_app.app_context():
        subscription = _create_subscription(
            "sub-pingxx-renewal-1",
            current_period_end_at=cycle_end,
            billing_provider="pingxx",
            provider_subscription_id="",
        )
        event = _create_renewal_event(
            "renewal-pingxx-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            scheduled_at=cycle_end - timedelta(days=7),
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-pingxx-1",
    )

    assert payload["status"] == "queued_for_reconcile"
    assert payload["event_status"] == "succeeded"

    with billing_renewal_app.app_context():
        order = BillingOrder.query.filter_by(
            bill_order_bid=payload["bill_order_bid"]
        ).one()
        assert order.payment_provider == "pingxx"
        assert order.provider_reference_id == ""
        assert order.metadata_json["provider_reference_type"] == "charge"
        assert order.metadata_json["renewal_cycle_start_at"] == cycle_end.isoformat()


def test_run_billing_renewal_event_writes_daily_cycle_metadata(
    billing_renewal_app: Flask,
) -> None:
    cycle_end = now_utc() - timedelta(hours=1)
    expected_cycle_end = _self_managed_cycle_end_after_boundary(
        cycle_end,
        interval=BILLING_INTERVAL_DAY,
        interval_count=7,
    )

    with billing_renewal_app.app_context():
        dao.db.session.add(
            BillingProduct(
                product_bid="bill-product-plan-daily",
                product_code="creator-plan-daily",
                product_type=BILLING_PRODUCT_TYPE_PLAN,
                billing_mode=BILLING_MODE_RECURRING,
                billing_interval=BILLING_INTERVAL_DAY,
                billing_interval_count=7,
                display_name_i18n_key=(
                    "module.billing.catalog.plans.creatorMonthly.title"
                ),
                description_i18n_key=(
                    "module.billing.catalog.plans.creatorMonthly.description"
                ),
                currency="CNY",
                price_amount=390,
                credit_amount=3,
                allocation_interval=ALLOCATION_INTERVAL_PER_CYCLE,
                auto_renew_enabled=1,
                entitlement_payload=None,
                metadata_json=None,
                status=BILLING_PRODUCT_STATUS_ACTIVE,
                sort_order=15,
            )
        )
        subscription = _create_subscription(
            "sub-daily-renewal-1",
            product_bid="bill-product-plan-daily",
            current_period_end_at=cycle_end,
            billing_provider="pingxx",
            provider_subscription_id="",
        )
        event = _create_renewal_event(
            "renewal-daily-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            scheduled_at=cycle_end - timedelta(minutes=5),
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-daily-1",
    )

    assert payload["status"] == "queued_for_reconcile"

    with billing_renewal_app.app_context():
        order = BillingOrder.query.filter_by(
            bill_order_bid=payload["bill_order_bid"]
        ).one()
        assert order.metadata_json["renewal_cycle_start_at"] == cycle_end.isoformat()
        assert (
            order.metadata_json["renewal_cycle_end_at"]
            == expected_cycle_end.isoformat()
        )
