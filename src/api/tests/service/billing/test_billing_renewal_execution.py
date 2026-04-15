from __future__ import annotations

from datetime import datetime, timedelta

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_PRODUCT_SEEDS,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    BILLING_TRIAL_PRODUCT_BID,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
)
from flaskr.service.billing.renewal import (
    claim_billing_renewal_event,
    run_billing_renewal_event,
)
from flaskr.service.billing.subscriptions import sync_subscription_lifecycle_events


def _seed_products() -> list[BillingProduct]:
    items: list[BillingProduct] = []
    for seed in BILLING_PRODUCT_SEEDS:
        payload = dict(seed)
        payload["metadata_json"] = payload.pop("metadata", None)
        items.append(BillingProduct(**payload))
    return items


@pytest.fixture
def billing_renewal_app() -> Flask:
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(_seed_products())
        dao.db.session.commit()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _create_subscription(
    subscription_bid: str,
    *,
    creator_bid: str = "creator-renewal-1",
    product_bid: str = "billing-product-plan-monthly",
    next_product_bid: str = "",
    status: int = BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    current_period_end_at: datetime | None = None,
    billing_provider: str = "stripe",
    provider_subscription_id: str | None = None,
) -> BillingSubscription:
    now = datetime.now()
    return BillingSubscription(
        subscription_bid=subscription_bid,
        creator_bid=creator_bid,
        product_bid=product_bid,
        status=status,
        billing_provider=billing_provider,
        provider_subscription_id=provider_subscription_id
        if provider_subscription_id is not None
        else (f"provider-{subscription_bid}" if billing_provider == "stripe" else ""),
        provider_customer_id=f"customer-{subscription_bid}",
        current_period_start_at=now - timedelta(days=29),
        current_period_end_at=current_period_end_at or (now + timedelta(days=1)),
        cancel_at_period_end=0,
        next_product_bid=next_product_bid,
        metadata_json={},
        created_at=now - timedelta(days=30),
        updated_at=now - timedelta(days=30),
    )


def _create_renewal_event(
    renewal_event_bid: str,
    subscription_bid: str,
    creator_bid: str,
    *,
    event_type: int,
    scheduled_at: datetime | None = None,
    status: int = BILLING_RENEWAL_EVENT_STATUS_PENDING,
) -> BillingRenewalEvent:
    return BillingRenewalEvent(
        renewal_event_bid=renewal_event_bid,
        subscription_bid=subscription_bid,
        creator_bid=creator_bid,
        event_type=event_type,
        scheduled_at=scheduled_at or (datetime.now() - timedelta(minutes=1)),
        status=status,
        attempt_count=0,
        last_error="",
        payload_json={"source": "pytest"},
        processed_at=None,
    )


def test_claim_billing_renewal_event_persists_processing_state(
    billing_renewal_app: Flask,
) -> None:
    with billing_renewal_app.app_context():
        subscription = _create_subscription("sub-claim-1")
        event = _create_renewal_event(
            "renewal-claim-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = claim_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-claim-1",
    )

    assert payload["status"] == "claimed"
    assert payload["event_status"] == "processing"
    assert payload["attempt_count"] == 1

    with billing_renewal_app.app_context():
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-claim-1"
        ).one()
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_PROCESSING
        assert event.attempt_count == 1


def test_run_billing_renewal_event_applies_cancel_effective(
    billing_renewal_app: Flask,
) -> None:
    with billing_renewal_app.app_context():
        subscription = _create_subscription("sub-cancel-1")
        subscription.cancel_at_period_end = 1
        event = _create_renewal_event(
            "renewal-cancel-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-cancel-1",
    )

    assert payload["status"] == "applied"
    assert payload["subscription_status"] == "canceled"
    assert payload["event_status"] == "succeeded"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-cancel-1"
        ).one()
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-cancel-1"
        ).one()
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
        assert event.processed_at is not None


def test_run_billing_renewal_event_applies_expire(
    billing_renewal_app: Flask,
) -> None:
    with billing_renewal_app.app_context():
        subscription = _create_subscription("sub-expire-1")
        event = _create_renewal_event(
            "renewal-expire-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-expire-1",
    )

    assert payload["status"] == "applied"
    assert payload["subscription_status"] == "expired"
    assert payload["event_status"] == "succeeded"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-expire-1"
        ).one()
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_EXPIRED


def test_manual_trial_subscription_schedules_and_applies_expire(
    billing_renewal_app: Flask,
) -> None:
    with billing_renewal_app.app_context():
        subscription = _create_subscription(
            "sub-trial-expire-1",
            product_bid=BILLING_TRIAL_PRODUCT_BID,
            billing_provider="manual",
            provider_subscription_id="",
            current_period_end_at=datetime.now() - timedelta(minutes=1),
        )
        dao.db.session.add(subscription)
        dao.db.session.flush()
        sync_subscription_lifecycle_events(billing_renewal_app, subscription)
        dao.db.session.commit()

        event = BillingRenewalEvent.query.filter_by(
            subscription_bid=subscription.subscription_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
        ).one()
        renewal_event_bid = event.renewal_event_bid
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid=renewal_event_bid,
    )

    assert payload["status"] == "applied"
    assert payload["subscription_status"] == "expired"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-trial-expire-1"
        ).one()
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_EXPIRED


def test_run_billing_renewal_event_applies_downgrade_and_reschedules_renewal(
    billing_renewal_app: Flask,
) -> None:
    next_period_end = datetime.now() + timedelta(days=30)
    with billing_renewal_app.app_context():
        subscription = _create_subscription(
            "sub-downgrade-1",
            product_bid="billing-product-plan-yearly",
            next_product_bid="billing-product-plan-monthly",
            current_period_end_at=next_period_end,
        )
        event = _create_renewal_event(
            "renewal-downgrade-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-downgrade-1",
    )

    assert payload["status"] == "applied"
    assert payload["product_bid"] == "billing-product-plan-monthly"
    assert payload["event_status"] == "succeeded"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-downgrade-1"
        ).one()
        renewal_event = BillingRenewalEvent.query.filter_by(
            subscription_bid="sub-downgrade-1",
            event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
        ).one()
        assert subscription.product_bid == "billing-product-plan-monthly"
        assert subscription.next_product_bid == ""
        assert renewal_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
        assert renewal_event.scheduled_at == next_period_end


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
            scheduled_at=datetime.now() + timedelta(minutes=30),
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


def test_run_billing_renewal_event_queues_subscription_renewal_order(
    billing_renewal_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.renewal.sync_billing_order",
        lambda app, creator_bid, billing_order_bid, payload: {
            "status": "pending",
            "creator_bid": creator_bid,
            "billing_order_bid": billing_order_bid,
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
    assert payload["billing_order_bid"]

    with billing_renewal_app.app_context():
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-unsupported-1"
        ).one()
        order = BillingOrder.query.filter_by(
            billing_order_bid=payload["billing_order_bid"]
        ).one()
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
        assert order.subscription_bid == subscription_bid
        assert order.provider_reference_id == "sub_provider_unsupported_1"
        assert order.metadata_json["provider_reference_type"] == "subscription"


def test_run_billing_renewal_event_queues_pingxx_order_without_provider_sync(
    billing_renewal_app: Flask,
) -> None:
    cycle_end = datetime.now() - timedelta(hours=1)
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
            billing_order_bid=payload["billing_order_bid"]
        ).one()
        assert order.payment_provider == "pingxx"
        assert order.provider_reference_id == ""
        assert order.metadata_json["provider_reference_type"] == "charge"
        assert order.metadata_json["renewal_cycle_start_at"] == cycle_end.isoformat()


def test_expire_event_activates_paid_pingxx_renewal_instead_of_expiring(
    billing_renewal_app: Flask,
) -> None:
    current_cycle_start = datetime.now() - timedelta(days=30)
    current_cycle_end = datetime.now() - timedelta(minutes=1)
    next_cycle_end = current_cycle_end + timedelta(days=30)

    with billing_renewal_app.app_context():
        subscription = BillingSubscription(
            subscription_bid="sub-pingxx-expire-paid",
            creator_bid="creator-renewal-1",
            product_bid="billing-product-plan-monthly",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="pingxx",
            provider_subscription_id="",
            provider_customer_id="customer-sub-pingxx-expire-paid",
            current_period_start_at=current_cycle_start,
            current_period_end_at=current_cycle_end,
            cancel_at_period_end=0,
            next_product_bid="",
            metadata_json={},
            created_at=current_cycle_start,
            updated_at=current_cycle_start,
        )
        order = BillingOrder(
            billing_order_bid="billing-pingxx-expire-paid-1",
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=9900,
            paid_amount=9900,
            payment_provider="pingxx",
            channel="alipay_qr",
            provider_reference_id="ch_pingxx_expire_paid_1",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=current_cycle_end - timedelta(days=5),
            metadata_json={
                "provider_reference_type": "charge",
                "renewal_cycle_start_at": current_cycle_end.isoformat(),
                "renewal_cycle_end_at": next_cycle_end.isoformat(),
            },
        )
        event = _create_renewal_event(
            "renewal-expire-paid-1",
            subscription.subscription_bid,
            subscription.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=current_cycle_end,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.add(event)
        dao.db.session.commit()

    payload = run_billing_renewal_event(
        billing_renewal_app,
        renewal_event_bid="renewal-expire-paid-1",
    )

    assert payload["status"] == "applied"
    assert payload["subscription_status"] == "active"
    assert payload["billing_order_bid"] == "billing-pingxx-expire-paid-1"

    with billing_renewal_app.app_context():
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="sub-pingxx-expire-paid"
        ).one()
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert subscription.current_period_start_at == current_cycle_end
        assert subscription.current_period_end_at == next_cycle_end


def test_run_billing_renewal_event_retries_latest_failed_renewal_order(
    billing_renewal_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.renewal.sync_billing_order",
        lambda app, creator_bid, billing_order_bid, payload: {
            "status": "paid",
            "creator_bid": creator_bid,
            "billing_order_bid": billing_order_bid,
        },
    )

    cycle_start = datetime.now()
    cycle_end = cycle_start + timedelta(days=30)
    with billing_renewal_app.app_context():
        subscription = _create_subscription(
            "sub-retry-1",
            current_period_end_at=cycle_start,
        )
        subscription.provider_subscription_id = "sub_provider_retry_1"
        renewal_order = BillingOrder(
            billing_order_bid="billing-renewal-retry-1",
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
        event = _create_renewal_event(
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
