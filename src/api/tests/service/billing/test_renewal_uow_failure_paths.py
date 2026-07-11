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

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.dao import uow
from flaskr.service.billing import renewal as billing_renewal
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingRenewalEvent,
    BillingSubscription,
)
from flaskr.service.billing.renewal import run_billing_renewal_event
from flaskr.util.datetime import now_utc
from tests.common.fixtures.bill_products import build_bill_products

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
            raise RuntimeError(f"boom in {subscription.subscription_bid}")

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

    def crashing_sync(*_args, **_kwargs):
        raise RuntimeError("provider sync crash")

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
    with pytest.raises(RuntimeError, match="outer boom"):
        with uow.unit_of_work():
            run_billing_renewal_event(
                renewal_uow_app, renewal_event_bid="renewal-uow-notify"
            )
            assert enqueued == []  # not yet durable, must not dispatch
            raise RuntimeError("outer boom")
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
