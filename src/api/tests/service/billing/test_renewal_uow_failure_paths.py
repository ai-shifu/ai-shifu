"""Mid-flow-failure tests for the billing renewal unit-of-work migration (B4b).

Before the migration, ``billing/renewal.py`` committed 25 times mid-flow.
These tests pin the new semantics:

- Each renewal event executes in its own transaction scope, so a failure in
  one event never affects the outcome of neighboring events (per-item
  isolation; the dispatcher in ``billing/tasks.py`` enqueues one task per
  event, and each task call is one item).
- The claim (PENDING -> PROCESSING + attempt_count increment) is a deliberate
  must-persist step that commits before execution and survives an execution
  failure, so a crashed run cannot be double-executed and retries stay
  bounded until the stale-claim recovery releases the event.
- The renewal order and the event payload's ``bill_order_bid`` link commit
  before the payment-provider sync, so a provider crash cannot lose the
  charge context (a retry resolves the same order instead of double-charging).
- The preorder credit-release notification dispatch goes through
  ``uow.on_commit``: it fires only after the transaction is durable and is
  dropped on rollback.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao import uow
from flaskr.service.billing import renewal as billing_renewal
from flaskr.service.billing import renewal_event_transitions
from flaskr.service.billing import tasks as billing_tasks
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RECONCILE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingRenewalEvent,
    BillingSubscription,
)
from flaskr.service.billing.renewal import run_billing_renewal_event
from flaskr.util.datetime import now_utc
from sqlalchemy.orm import sessionmaker

from tests.common.fixtures.bill_products import build_bill_products

if TYPE_CHECKING:
    from pathlib import Path

CREATOR_BID = "creator-uow-renewal"


@pytest.fixture
def renewal_uow_app() -> Flask:
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
        dao.db.session.add_all(build_bill_products())
        dao.db.session.commit()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


@pytest.fixture
def renewal_uow_file_app(tmp_path: Path) -> Flask:
    db_path = tmp_path / "renewal-uow.sqlite"
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_path}",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": f"sqlite:///{tmp_path / 'saas.sqlite'}",
            "ai_shifu_admin": f"sqlite:///{tmp_path / 'admin.sqlite'}",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(build_bill_products())
        dao.db.session.commit()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _seed_subscription(subscription_bid: str) -> BillingSubscription:
    now = now_utc()
    subscription = BillingSubscription(
        subscription_bid=subscription_bid,
        creator_bid=CREATOR_BID,
        product_bid="bill-product-plan-monthly",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        billing_provider="stripe",
        provider_subscription_id=f"provider-{subscription_bid}",
        provider_customer_id=f"customer-{subscription_bid}",
        current_period_start_at=now - timedelta(days=29),
        current_period_end_at=now + timedelta(days=1),
        cancel_at_period_end=0,
        next_product_bid="",
        metadata_json={},
        created_at=now - timedelta(days=30),
        updated_at=now - timedelta(days=30),
    )
    dao.db.session.add(subscription)
    return subscription


def _seed_event(
    renewal_event_bid: str,
    subscription_bid: str,
    *,
    event_type: int,
) -> BillingRenewalEvent:
    event = BillingRenewalEvent(
        renewal_event_bid=renewal_event_bid,
        subscription_bid=subscription_bid,
        creator_bid=CREATOR_BID,
        event_type=event_type,
        scheduled_at=now_utc() - timedelta(minutes=1),
        status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
        attempt_count=0,
        last_error="",
        payload_json={"source": "pytest"},
        processed_at=None,
    )
    dao.db.session.add(event)
    return event


def _failing_lifecycle_sync(monkeypatch: pytest.MonkeyPatch, *, failing_bids: set):
    """Fail the cancel-effective handler mid-flow for selected subscriptions.

    The failure point sits after the subscription mutation and before the
    event completion, simulating any late in-transaction error.
    """

    def fake_sync(_app, subscription):
        if subscription.subscription_bid in failing_bids:
            message = f"boom in {subscription.subscription_bid}"
            raise RuntimeError(message)

    monkeypatch.setattr(
        billing_renewal, "_sync_subscription_lifecycle_events", fake_sync
    )


def test_second_event_failure_is_isolated_from_neighbor_events(
    renewal_uow_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-item isolation: item 2 of 3 fails; items 1 and 3 stay applied.

    Each event is one dispatch unit (one celery task per event), and each
    run owns its own claim + execution transactions, so the failed event's
    business writes roll back without touching its neighbors.
    """
    for index in (1, 2, 3):
        _seed_subscription(f"sub-uow-iso-{index}")
        _seed_event(
            f"renewal-uow-iso-{index}",
            f"sub-uow-iso-{index}",
            event_type=BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
        )
    dao.db.session.commit()
    _failing_lifecycle_sync(monkeypatch, failing_bids={"sub-uow-iso-2"})

    first = run_billing_renewal_event(
        renewal_uow_app, renewal_event_bid="renewal-uow-iso-1"
    )
    with pytest.raises(RuntimeError, match="boom in sub-uow-iso-2"):
        run_billing_renewal_event(
            renewal_uow_app, renewal_event_bid="renewal-uow-iso-2"
        )
    dao.db.session.rollback()
    third = run_billing_renewal_event(
        renewal_uow_app, renewal_event_bid="renewal-uow-iso-3"
    )

    assert first["status"] == "applied"
    assert third["status"] == "applied"

    dao.db.session.expire_all()
    for index in (1, 3):
        subscription = BillingSubscription.query.filter_by(
            subscription_bid=f"sub-uow-iso-{index}"
        ).one()
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid=f"renewal-uow-iso-{index}"
        ).one()
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED

    failed_subscription = BillingSubscription.query.filter_by(
        subscription_bid="sub-uow-iso-2"
    ).one()
    failed_event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-iso-2"
    ).one()
    # The business mutation rolled back completely...
    assert failed_subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert failed_subscription.cancel_at_period_end == 0
    # ...while the claim (must-persist step) survived the failure.
    assert failed_event.status == BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    assert failed_event.attempt_count == 1


def test_claim_persists_across_execution_failure_and_bounds_reruns(
    renewal_uow_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Must-persist step: the claim survives an execution failure.

    A durable PROCESSING claim blocks duplicate execution until the stale
    recovery in billing/tasks.py releases the event, after which a rerun
    completes and the attempt count keeps growing monotonically.
    """
    _seed_subscription("sub-uow-claim")
    _seed_event(
        "renewal-uow-claim",
        "sub-uow-claim",
        event_type=BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    )
    dao.db.session.commit()
    _failing_lifecycle_sync(monkeypatch, failing_bids={"sub-uow-claim"})

    with pytest.raises(RuntimeError, match="boom in sub-uow-claim"):
        run_billing_renewal_event(
            renewal_uow_app, renewal_event_bid="renewal-uow-claim"
        )
    dao.db.session.rollback()
    dao.db.session.expire_all()

    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-claim"
    ).one()
    subscription = BillingSubscription.query.filter_by(
        subscription_bid="sub-uow-claim"
    ).one()
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    assert event.attempt_count == 1
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE

    # While PROCESSING, another run must refuse to execute the event again.
    blocked = run_billing_renewal_event(
        renewal_uow_app, renewal_event_bid="renewal-uow-claim"
    )
    assert blocked["status"] == "already_claimed"

    # Simulate the stale-claim recovery task releasing the event, then rerun
    # without the fault: the event completes and the attempt count advances.
    event.status = BILLING_RENEWAL_EVENT_STATUS_PENDING
    dao.db.session.add(event)
    dao.db.session.commit()
    _failing_lifecycle_sync(monkeypatch, failing_bids=set())

    payload = run_billing_renewal_event(
        renewal_uow_app, renewal_event_bid="renewal-uow-claim"
    )
    assert payload["status"] == "applied"
    dao.db.session.expire_all()
    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-claim"
    ).one()
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
    assert event.attempt_count == 2


def test_renewal_order_persists_before_provider_sync_crash(
    renewal_uow_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Must-persist step: the renewal order commits before the provider sync.

    If the payment-provider sync crashes, the order row and the event
    payload's bill_order_bid link are already durable, so a later retry or
    reconcile resolves the same charge context instead of creating a second
    one (the double-charge guard).
    """
    _seed_subscription("sub-uow-order")
    _seed_event(
        "renewal-uow-order",
        "sub-uow-order",
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    dao.db.session.commit()

    def crashing_sync(*_args: object, **_kwargs):
        message = "provider sync crash"
        raise RuntimeError(message)

    monkeypatch.setattr(billing_renewal, "_sync_billing_renewal_order", crashing_sync)

    with pytest.raises(RuntimeError, match="provider sync crash"):
        run_billing_renewal_event(
            renewal_uow_app, renewal_event_bid="renewal-uow-order"
        )
    dao.db.session.rollback()
    dao.db.session.expire_all()

    order = BillingOrder.query.filter_by(subscription_bid="sub-uow-order").one()
    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-order"
    ).one()
    assert order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
    assert event.payload_json["bill_order_bid"] == order.bill_order_bid
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    assert event.attempt_count == 1


def test_expire_notification_fires_after_commit_and_drops_on_rollback(
    renewal_uow_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The credit-release dispatch obeys uow.on_commit semantics.

    Nested in a failing outer unit of work the callback is dropped with the
    rollback; at top level it fires exactly once, after the commit.
    """
    now = now_utc()
    subscription = _seed_subscription("sub-uow-notify")
    subscription.current_period_start_at = now - timedelta(days=31)
    subscription.current_period_end_at = now - timedelta(minutes=5)
    _seed_event(
        "renewal-uow-notify",
        "sub-uow-notify",
        event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    )
    paid_order = BillingOrder(
        bill_order_bid="bill-uow-notify-1",
        creator_bid=CREATOR_BID,
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        product_bid="bill-product-plan-monthly",
        subscription_bid="sub-uow-notify",
        currency="CNY",
        payable_amount=990,
        paid_amount=990,
        payment_provider="stripe",
        channel="subscription",
        provider_reference_id="provider-sub-uow-notify",
        status=BILLING_ORDER_STATUS_PAID,
        paid_at=now - timedelta(days=1),
        metadata_json={},
    )
    dao.db.session.add(paid_order)
    dao.db.session.commit()

    monkeypatch.setattr(
        billing_renewal,
        "_load_paid_renewal_order_for_cycle",
        lambda **_kwargs: BillingOrder.query.filter_by(
            bill_order_bid="bill-uow-notify-1"
        ).one(),
    )
    monkeypatch.setattr(
        billing_renewal,
        "_activate_subscription_for_paid_order",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        billing_renewal,
        "_stage_preorder_credit_release_notification",
        lambda *_args, **_kwargs: "notif-uow-1",
    )
    enqueued: list[str] = []
    monkeypatch.setattr(
        billing_renewal,
        "_enqueue_credit_release_notification",
        lambda _app, notification_bid: enqueued.append(notification_bid),
    )

    # Nested: the outer failure rolls the whole event back and the deferred
    # dispatch is dropped — the pre-migration code enqueued right after its
    # own commit and could never be taken back.
    def run_then_fail() -> None:
        with uow.unit_of_work():
            run_billing_renewal_event(
                renewal_uow_app, renewal_event_bid="renewal-uow-notify"
            )
            assert enqueued == []  # not yet durable, must not dispatch
            message = "outer boom"
            raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="outer boom"):
        run_then_fail()
    dao.db.session.expire_all()
    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-notify"
    ).one()
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
    assert enqueued == []

    # Top level: the dispatch fires exactly once, after the commit.
    payload = run_billing_renewal_event(
        renewal_uow_app, renewal_event_bid="renewal-uow-notify"
    )
    assert payload["status"] == "applied"
    assert enqueued == ["notif-uow-1"]
    dao.db.session.expire_all()
    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-notify"
    ).one()
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED


def test_subscription_lifecycle_cancel_skips_processing_events(
    renewal_uow_app: Flask,
) -> None:
    """Lifecycle sync must not cancel a worker that already claimed an event."""
    _ = renewal_uow_app
    subscription = _seed_subscription("sub-uow-cancel-processing")
    pending = _seed_event(
        "renewal-uow-cancel-pending",
        subscription.subscription_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    failed = _seed_event(
        "renewal-uow-cancel-failed",
        subscription.subscription_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    processing = _seed_event(
        "renewal-uow-cancel-processing",
        subscription.subscription_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    failed.status = BILLING_RENEWAL_EVENT_STATUS_FAILED
    processing.status = BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    dao.db.session.commit()
    processing_updated_at = processing.updated_at

    renewal_event_transitions.cancel_subscription_renewal_events(
        subscription.subscription_bid,
        event_types=(BILLING_RENEWAL_EVENT_TYPE_RENEWAL,),
    )
    dao.db.session.commit()
    dao.db.session.expire_all()

    pending = BillingRenewalEvent.query.filter_by(
        renewal_event_bid=pending.renewal_event_bid
    ).one()
    failed = BillingRenewalEvent.query.filter_by(
        renewal_event_bid=failed.renewal_event_bid
    ).one()
    processing = BillingRenewalEvent.query.filter_by(
        renewal_event_bid=processing.renewal_event_bid
    ).one()
    assert pending.status == BILLING_RENEWAL_EVENT_STATUS_CANCELED
    assert pending.processed_at is not None
    assert failed.status == BILLING_RENEWAL_EVENT_STATUS_CANCELED
    assert failed.processed_at is not None
    assert processing.status == BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    assert processing.processed_at is None
    assert processing.updated_at == processing_updated_at


def test_upsert_preserves_existing_processing_event(
    renewal_uow_app: Flask,
) -> None:
    """Lifecycle sync must not release an event that a worker already claimed."""
    subscription = _seed_subscription("sub-uow-upsert-processing")
    scheduled_at = now_utc() + timedelta(days=1)
    event = _seed_event(
        "renewal-uow-upsert-processing",
        subscription.subscription_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    event.scheduled_at = scheduled_at
    event.status = BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    event.attempt_count = 1
    event.last_error = "worker has claimed"
    event.payload_json = {"source": "claimed"}
    dao.db.session.commit()

    renewal_event_transitions.upsert_subscription_renewal_event(
        renewal_uow_app,
        subscription,
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
        scheduled_at=scheduled_at,
    )
    dao.db.session.commit()
    dao.db.session.expire_all()

    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-upsert-processing"
    ).one()
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    assert event.attempt_count == 1
    assert event.last_error == "worker has claimed"
    assert event.payload_json == {"source": "claimed"}


def test_processing_event_release_does_not_overwrite_canceled_event(
    renewal_uow_app: Flask,
) -> None:
    """A stale defer path cannot release a terminal event back to pending."""
    _ = renewal_uow_app
    _seed_subscription("sub-uow-stale-release")
    event = _seed_event(
        "renewal-uow-stale-release",
        "sub-uow-stale-release",
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    event.status = BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    dao.db.session.commit()

    loaded_by_worker = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-stale-release"
    ).one()
    BillingRenewalEvent.query.filter_by(
        id=loaded_by_worker.id,
    ).update(
        {
            "status": BILLING_RENEWAL_EVENT_STATUS_CANCELED,
            "processed_at": now_utc(),
        },
        synchronize_session=False,
    )
    dao.db.session.commit()

    with pytest.raises(renewal_event_transitions.RenewalEventClaimLostError):
        renewal_event_transitions.release_renewal_event(
            loaded_by_worker,
            now=now_utc(),
        )
    dao.db.session.rollback()
    dao.db.session.expire_all()

    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-stale-release"
    ).one()
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_CANCELED


def test_processing_event_completion_does_not_overwrite_canceled_event(
    renewal_uow_app: Flask,
) -> None:
    """A stale worker cannot mark an event succeeded after another transition."""
    _ = renewal_uow_app
    _seed_subscription("sub-uow-stale-complete")
    event = _seed_event(
        "renewal-uow-stale-complete",
        "sub-uow-stale-complete",
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    event.status = BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    dao.db.session.commit()

    loaded_by_worker = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-stale-complete"
    ).one()
    BillingRenewalEvent.query.filter_by(
        id=loaded_by_worker.id,
    ).update(
        {
            "status": BILLING_RENEWAL_EVENT_STATUS_CANCELED,
            "processed_at": now_utc(),
        },
        synchronize_session=False,
    )
    dao.db.session.commit()

    with pytest.raises(renewal_event_transitions.RenewalEventClaimLostError):
        renewal_event_transitions.complete_renewal_event(
            loaded_by_worker,
            now=now_utc(),
        )
    dao.db.session.rollback()
    dao.db.session.expire_all()

    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-stale-complete"
    ).one()
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_CANCELED


def test_processing_event_failure_does_not_overwrite_succeeded_event(
    renewal_uow_app: Flask,
) -> None:
    """A stale failure path cannot move a terminal event back to failed."""
    _ = renewal_uow_app
    _seed_subscription("sub-uow-stale-fail")
    event = _seed_event(
        "renewal-uow-stale-fail",
        "sub-uow-stale-fail",
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    event.status = BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    dao.db.session.commit()

    loaded_by_worker = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-stale-fail"
    ).one()
    BillingRenewalEvent.query.filter_by(
        id=loaded_by_worker.id,
    ).update(
        {
            "status": BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
            "processed_at": now_utc(),
            "last_error": "",
        },
        synchronize_session=False,
    )
    dao.db.session.commit()

    with pytest.raises(renewal_event_transitions.RenewalEventClaimLostError):
        renewal_event_transitions.fail_renewal_event(
            loaded_by_worker,
            now=now_utc(),
            error="late failure",
        )
    dao.db.session.rollback()
    dao.db.session.expire_all()

    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-stale-fail"
    ).one()
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
    assert event.last_error == ""


def test_renewal_event_skips_obsolete_canceled_subscription(
    renewal_uow_app: Flask,
) -> None:
    """A stale recovered renewal event cannot charge a canceled subscription."""
    subscription = _seed_subscription("sub-uow-obsolete-renewal")
    subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCELED
    event = _seed_event(
        "renewal-uow-obsolete-renewal",
        subscription.subscription_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    dao.db.session.commit()

    payload = run_billing_renewal_event(
        renewal_uow_app,
        renewal_event_bid=event.renewal_event_bid,
    )
    dao.db.session.expire_all()

    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-obsolete-renewal"
    ).one()
    assert payload["status"] == "already_applied"
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
    assert (
        BillingOrder.query.filter_by(
            subscription_bid=subscription.subscription_bid,
        ).count()
        == 0
    )


def test_renewal_event_cancels_existing_obsolete_order_for_canceled_subscription(
    renewal_uow_app: Flask,
) -> None:
    """Obsolete subscriptions must not leave retryable renewal orders pending."""
    now = now_utc()
    subscription = _seed_subscription("sub-uow-obsolete-order")
    subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCELED
    event = _seed_event(
        "renewal-uow-obsolete-order",
        subscription.subscription_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    event.payload_json = {"bill_order_bid": "bill-uow-obsolete-order"}
    order = BillingOrder(
        bill_order_bid="bill-uow-obsolete-order",
        creator_bid=CREATOR_BID,
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        product_bid="bill-product-plan-monthly",
        subscription_bid=subscription.subscription_bid,
        currency="CNY",
        payable_amount=990,
        paid_amount=0,
        payment_provider="stripe",
        channel="subscription",
        provider_reference_id="provider-sub-uow-obsolete-order",
        status=BILLING_ORDER_STATUS_PENDING,
        paid_at=None,
        metadata_json={"renewal_event_bid": event.renewal_event_bid},
        created_at=now,
        updated_at=now,
    )
    dao.db.session.add(order)
    dao.db.session.commit()

    payload = run_billing_renewal_event(
        renewal_uow_app,
        renewal_event_bid=event.renewal_event_bid,
    )
    dao.db.session.expire_all()

    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-obsolete-order"
    ).one()
    order = BillingOrder.query.filter_by(bill_order_bid="bill-uow-obsolete-order").one()
    assert payload["status"] == "already_applied"
    assert payload["bill_order_bid"] == "bill-uow-obsolete-order"
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
    assert order.status == BILLING_ORDER_STATUS_CANCELED
    assert order.metadata_json["canceled_reason"] == "subscription_canceled"
    assert order.metadata_json["canceled_at"].endswith("Z")


def test_renewal_event_skips_obsolete_expired_subscription(
    renewal_uow_app: Flask,
) -> None:
    """A stale recovered renewal event cannot charge an expired subscription."""
    subscription = _seed_subscription("sub-uow-expired-renewal")
    subscription.status = BILLING_SUBSCRIPTION_STATUS_EXPIRED
    event = _seed_event(
        "renewal-uow-expired-renewal",
        subscription.subscription_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    dao.db.session.commit()

    payload = run_billing_renewal_event(
        renewal_uow_app,
        renewal_event_bid=event.renewal_event_bid,
    )
    dao.db.session.expire_all()

    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-expired-renewal"
    ).one()
    assert payload["status"] == "already_applied"
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
    assert (
        BillingOrder.query.filter_by(
            subscription_bid=subscription.subscription_bid,
        ).count()
        == 0
    )


def test_old_claim_cannot_complete_new_processing_attempt(
    renewal_uow_app: Flask,
) -> None:
    """Attempt-count CAS prevents an old worker from finishing a new claim."""
    _ = renewal_uow_app
    _seed_subscription("sub-uow-claim-generation")
    event = _seed_event(
        "renewal-uow-claim-generation",
        "sub-uow-claim-generation",
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    event.status = BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    event.attempt_count = 1
    dao.db.session.commit()

    old_worker_event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-claim-generation"
    ).one()
    renewal_event_transitions.bind_renewal_event_claim(
        old_worker_event,
        attempt_count=1,
    )
    BillingRenewalEvent.query.filter_by(id=old_worker_event.id).update(
        {
            "status": BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
            "attempt_count": 2,
            "updated_at": now_utc(),
        },
        synchronize_session=False,
    )
    dao.db.session.commit()

    with pytest.raises(renewal_event_transitions.RenewalEventClaimLostError):
        renewal_event_transitions.complete_renewal_event(
            old_worker_event,
            now=now_utc(),
        )
    dao.db.session.rollback()
    dao.db.session.expire_all()

    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-claim-generation"
    ).one()
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    assert event.attempt_count == 2


def test_lost_claim_rolls_back_business_side_effects(
    renewal_uow_app: Flask,
) -> None:
    """Callers must not commit business writes when terminal CAS loses."""
    _ = renewal_uow_app
    subscription = _seed_subscription("sub-uow-lost-claim-rollback")
    event = _seed_event(
        "renewal-uow-lost-claim-rollback",
        subscription.subscription_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    event.status = BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    event.attempt_count = 1
    dao.db.session.commit()

    old_worker_event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-lost-claim-rollback"
    ).one()
    renewal_event_transitions.bind_renewal_event_claim(
        old_worker_event,
        attempt_count=1,
    )
    BillingRenewalEvent.query.filter_by(id=old_worker_event.id).update(
        {
            "status": BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
            "attempt_count": 2,
            "updated_at": now_utc(),
        },
        synchronize_session=False,
    )
    dao.db.session.commit()

    def cancel_then_complete() -> None:
        with uow.unit_of_work():
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-uow-lost-claim-rollback"
            ).one()
            subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCELED
            dao.db.session.add(subscription)
            renewal_event_transitions.complete_renewal_event(
                old_worker_event,
                now=now_utc(),
            )

    with pytest.raises(renewal_event_transitions.RenewalEventClaimLostError):
        cancel_then_complete()
    dao.db.session.expire_all()

    subscription = BillingSubscription.query.filter_by(
        subscription_bid="sub-uow-lost-claim-rollback"
    ).one()
    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-lost-claim-rollback"
    ).one()
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    assert event.attempt_count == 2


def test_lost_claim_stops_before_renewal_order_or_provider_side_effects(
    renewal_uow_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale attempt must stop before order creation or provider sync."""
    subscription = _seed_subscription("sub-uow-lost-before-side-effect")
    event = _seed_event(
        "renewal-uow-lost-before-side-effect",
        subscription.subscription_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    event.status = BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    event.attempt_count = 1
    dao.db.session.commit()

    old_worker_event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-lost-before-side-effect"
    ).one()
    renewal_event_transitions.bind_renewal_event_claim(
        old_worker_event,
        attempt_count=1,
    )
    BillingRenewalEvent.query.filter_by(id=old_worker_event.id).update(
        {
            "status": BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
            "attempt_count": 2,
            "updated_at": now_utc(),
        },
        synchronize_session=False,
    )
    dao.db.session.commit()

    monkeypatch.setattr(
        billing_renewal,
        "ensure_subscription_renewal_order",
        lambda *_args, **_kwargs: pytest.fail("order creation must not run"),
    )
    monkeypatch.setattr(
        billing_renewal,
        "_sync_billing_renewal_order",
        lambda *_args, **_kwargs: pytest.fail("provider sync must not run"),
    )

    with pytest.raises(renewal_event_transitions.RenewalEventClaimLostError):
        billing_renewal._execute_subscription_renewal(
            renewal_uow_app,
            old_worker_event,
            now=now_utc(),
        )
    dao.db.session.rollback()
    dao.db.session.expire_all()

    assert (
        BillingOrder.query.filter_by(
            subscription_bid=subscription.subscription_bid,
        ).count()
        == 0
    )
    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-lost-before-side-effect"
    ).one()
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_PROCESSING
    assert event.attempt_count == 2


def test_provider_guard_renews_lease_before_cross_transaction_sync(
    renewal_uow_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stale recovery cannot hand off a freshly guarded provider attempt."""
    subscription = _seed_subscription("sub-uow-lease-before-provider")
    event = _seed_event(
        "renewal-uow-lease-before-provider",
        subscription.subscription_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    )
    dao.db.session.commit()

    recovery_counts: list[int] = []

    def fake_sync(*_args: object, **_kwargs):
        recovery_counts.append(
            billing_tasks._recover_stale_processing_renewal_events(
                stale_before=now_utc() - timedelta(minutes=30),
            )
        )
        current = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-uow-lease-before-provider"
        ).one()
        assert current.status == BILLING_RENEWAL_EVENT_STATUS_PROCESSING
        assert current.attempt_count == 1
        return SimpleNamespace(status="pending", message="")

    monkeypatch.setattr(billing_renewal, "_sync_billing_renewal_order", fake_sync)

    payload = run_billing_renewal_event(
        renewal_uow_app,
        renewal_event_bid=event.renewal_event_bid,
    )
    dao.db.session.expire_all()

    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid="renewal-uow-lease-before-provider"
    ).one()
    assert recovery_counts == [0]
    assert payload["status"] == "queued_for_reconcile"
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
    assert event.attempt_count == 1


@pytest.mark.parametrize(
    "event_type",
    [
        BILLING_RENEWAL_EVENT_TYPE_RETRY,
        BILLING_RENEWAL_EVENT_TYPE_RECONCILE,
    ],
)
def test_retry_or_reconcile_skips_obsolete_subscription_before_provider_sync(
    renewal_uow_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    event_type: int,
) -> None:
    """Recovered retry/reconcile events must not sync canceled subscriptions."""
    now = now_utc()
    subscription = _seed_subscription(f"sub-uow-obsolete-retry-{event_type}")
    subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCELED
    event = _seed_event(
        f"renewal-uow-obsolete-retry-{event_type}",
        subscription.subscription_bid,
        event_type=event_type,
    )
    event.payload_json = {"bill_order_bid": f"bill-uow-obsolete-retry-{event_type}"}
    order = BillingOrder(
        bill_order_bid=f"bill-uow-obsolete-retry-{event_type}",
        creator_bid=CREATOR_BID,
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        product_bid="bill-product-plan-monthly",
        subscription_bid=subscription.subscription_bid,
        currency="CNY",
        payable_amount=990,
        paid_amount=0,
        payment_provider="stripe",
        channel="subscription",
        provider_reference_id=f"provider-sub-uow-obsolete-retry-{event_type}",
        status=BILLING_ORDER_STATUS_PENDING,
        paid_at=None,
        metadata_json={"renewal_event_bid": event.renewal_event_bid},
        created_at=now,
        updated_at=now,
    )
    dao.db.session.add(order)
    dao.db.session.commit()

    monkeypatch.setattr(
        billing_renewal,
        "_sync_billing_renewal_order",
        lambda *_args, **_kwargs: pytest.fail("provider sync must not run"),
    )

    payload = run_billing_renewal_event(
        renewal_uow_app,
        renewal_event_bid=event.renewal_event_bid,
    )
    dao.db.session.expire_all()

    event = BillingRenewalEvent.query.filter_by(
        renewal_event_bid=f"renewal-uow-obsolete-retry-{event_type}"
    ).one()
    order = BillingOrder.query.filter_by(
        bill_order_bid=f"bill-uow-obsolete-retry-{event_type}"
    ).one()
    assert payload["status"] == "already_applied"
    assert payload["bill_order_bid"] == order.bill_order_bid
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
    assert order.status == BILLING_ORDER_STATUS_CANCELED


def test_upsert_recovers_when_concurrent_insert_wins(
    renewal_uow_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent lifecycle sync should reuse the unique-key winner."""
    subscription = _seed_subscription("sub-uow-upsert-race")
    scheduled_at = now_utc() + timedelta(days=1)
    dao.db.session.commit()

    original_load = renewal_event_transitions._load_subscription_renewal_event
    calls = 0

    def racing_load(
        subscription_bid: str,
        *,
        event_type: int,
        scheduled_at,
        for_update: bool = False,
    ):
        nonlocal calls
        calls += 1
        if calls == 1:
            winner = BillingRenewalEvent(
                renewal_event_bid="renewal-uow-upsert-race-winner",
                subscription_bid=subscription_bid,
                creator_bid="stale-creator",
                event_type=event_type,
                scheduled_at=scheduled_at,
                status=BILLING_RENEWAL_EVENT_STATUS_FAILED,
                attempt_count=3,
                last_error="stale failure",
                payload_json={"source": "racing worker"},
                processed_at=now_utc(),
            )
            dao.db.session.add(winner)
            dao.db.session.flush()
            return None
        return original_load(
            subscription_bid,
            event_type=event_type,
            scheduled_at=scheduled_at,
            for_update=for_update,
        )

    monkeypatch.setattr(
        renewal_event_transitions,
        "_load_subscription_renewal_event",
        racing_load,
    )

    renewal_event_transitions.upsert_subscription_renewal_event(
        renewal_uow_app,
        subscription,
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
        scheduled_at=scheduled_at,
    )
    dao.db.session.commit()
    dao.db.session.expire_all()

    events = BillingRenewalEvent.query.filter_by(
        subscription_bid=subscription.subscription_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    ).all()
    assert len(events) == 1
    event = events[0]
    assert event.renewal_event_bid == "renewal-uow-upsert-race-winner"
    assert event.creator_bid == CREATOR_BID
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
    assert event.attempt_count == 3
    assert event.last_error == ""
    assert event.processed_at is None
    assert event.payload_json["subscription_bid"] == subscription.subscription_bid


def test_upsert_recovers_when_cross_session_insert_wins(
    renewal_uow_file_app: Flask,
) -> None:
    """Duplicate-key recovery reloads a winner committed by another session."""
    subscription = _seed_subscription("sub-uow-upsert-cross-session")
    scheduled_at = now_utc() + timedelta(days=1)
    dao.db.session.commit()

    original_load = renewal_event_transitions._load_subscription_renewal_event
    calls: list[bool] = []

    def racing_load(
        subscription_bid: str,
        *,
        event_type: int,
        scheduled_at,
        for_update: bool = False,
    ):
        calls.append(for_update)
        if len(calls) == 1:
            session_factory = sessionmaker(bind=dao.db.engine)
            other_session = session_factory()
            try:
                winner = BillingRenewalEvent(
                    renewal_event_bid="renewal-uow-upsert-cross-session-winner",
                    subscription_bid=subscription_bid,
                    creator_bid="stale-creator",
                    event_type=event_type,
                    scheduled_at=scheduled_at,
                    status=BILLING_RENEWAL_EVENT_STATUS_FAILED,
                    attempt_count=2,
                    last_error="stale failure",
                    payload_json={"source": "other session"},
                    processed_at=now_utc(),
                )
                other_session.add(winner)
                other_session.commit()
            finally:
                other_session.close()
            return None
        return original_load(
            subscription_bid,
            event_type=event_type,
            scheduled_at=scheduled_at,
            for_update=for_update,
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        renewal_event_transitions,
        "_load_subscription_renewal_event",
        racing_load,
    )
    try:
        renewal_event_transitions.upsert_subscription_renewal_event(
            renewal_uow_file_app,
            subscription,
            event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            scheduled_at=scheduled_at,
        )
        dao.db.session.commit()
    finally:
        monkeypatch.undo()
    dao.db.session.expire_all()

    events = BillingRenewalEvent.query.filter_by(
        subscription_bid=subscription.subscription_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    ).all()
    assert calls == [False, True]
    assert len(events) == 1
    event = events[0]
    assert event.renewal_event_bid == "renewal-uow-upsert-cross-session-winner"
    assert event.creator_bid == CREATOR_BID
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
    assert event.attempt_count == 2
    assert event.last_error == ""
    assert event.processed_at is None
    assert event.payload_json["subscription_bid"] == subscription.subscription_bid
