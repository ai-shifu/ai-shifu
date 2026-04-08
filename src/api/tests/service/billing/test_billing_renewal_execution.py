from __future__ import annotations

from datetime import datetime, timedelta

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_PRODUCT_SEEDS,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
)
from flaskr.service.billing.models import (
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
)
from flaskr.service.billing.renewal import (
    claim_billing_renewal_event,
    run_billing_renewal_event,
)


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
) -> BillingSubscription:
    now = datetime.now()
    return BillingSubscription(
        subscription_bid=subscription_bid,
        creator_bid=creator_bid,
        product_bid=product_bid,
        status=status,
        billing_provider="stripe",
        provider_subscription_id=f"provider-{subscription_bid}",
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


def test_run_billing_renewal_event_marks_unsupported_event_failed(
    billing_renewal_app: Flask,
) -> None:
    with billing_renewal_app.app_context():
        subscription = _create_subscription("sub-unsupported-1")
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

    assert payload["status"] == "failed"
    assert payload["event_status"] == "failed"
    assert "renewal_event_handler_not_implemented:renewal" in payload["last_error"]

    with billing_renewal_app.app_context():
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-unsupported-1"
        ).one()
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_FAILED
        assert "renewal_event_handler_not_implemented:renewal" in event.last_error
