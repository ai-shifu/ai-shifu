"""Verify renewal events preserve ownership and handle missing lifecycle evidence."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.billing import renewal
from flaskr.service.billing.consts import (
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RECONCILE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
)
from flaskr.service.billing.models import BillingRenewalEvent
from flaskr.util.datetime import now_utc

from tests.service.billing.renewal_execution_test_helpers import create_renewal_event
from tests.service.billing.test_checkout_state_transition_contracts import _seed

if TYPE_CHECKING:
    from flask import Flask


@pytest.mark.parametrize(
    "event_type",
    [
        BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
        BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
        BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
        BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
        BILLING_RENEWAL_EVENT_TYPE_RETRY,
        BILLING_RENEWAL_EVENT_TYPE_RECONCILE,
    ],
)
def test_renewal_event_marks_missing_subscription_as_failed_without_abandoning_claim(
    event_type: int, app: Flask
) -> None:
    with app.app_context():
        event = create_renewal_event(
            uuid4().hex, uuid4().hex, uuid4().hex, event_type=event_type
        )
        db.session.add(event)
        db.session.commit()
        result = renewal.run_billing_renewal_event(
            app, renewal_event_bid=event.renewal_event_bid
        )
        db.session.expire_all()
        assert result.status == "failed"
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_FAILED
        assert event.last_error == "subscription_not_found"
        assert event.attempt_count == 1
        assert event.processed_at is not None


@pytest.mark.parametrize(
    ("event_type", "subscription_status", "advance_cycle"),
    [
        (
            BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
            BILLING_SUBSCRIPTION_STATUS_CANCELED,
            False,
        ),
        (
            BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
            BILLING_SUBSCRIPTION_STATUS_EXPIRED,
            False,
        ),
        (BILLING_RENEWAL_EVENT_TYPE_EXPIRE, BILLING_SUBSCRIPTION_STATUS_EXPIRED, False),
        (BILLING_RENEWAL_EVENT_TYPE_EXPIRE, BILLING_SUBSCRIPTION_STATUS_ACTIVE, True),
        (
            BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
            BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            False,
        ),
    ],
)
def test_already_applied_subscription_event_completes_once_without_reverting_state(
    event_type: int, subscription_status: int, advance_cycle: bool, app: Flask
) -> None:
    with app.app_context():
        _, _, plan = _seed(subscription=True)
        plan.status = subscription_status
        boundary = now_utc() - timedelta(minutes=1)
        if advance_cycle:
            plan.current_period_start_at = boundary
        event = create_renewal_event(
            uuid4().hex,
            plan.subscription_bid,
            plan.creator_bid,
            event_type=event_type,
            scheduled_at=boundary,
        )
        db.session.add(event)
        db.session.commit()
        result = renewal.run_billing_renewal_event(
            app, renewal_event_bid=event.renewal_event_bid
        )
        assert result.status == "already_applied"
        db.session.expire_all()
        assert plan.status == subscription_status
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
        repeat = renewal.run_billing_renewal_event(
            app, renewal_event_bid=event.renewal_event_bid
        )
        assert repeat.status == "already_processed"
        assert event.attempt_count == 1


def test_unknown_renewal_handler_persists_failure_diagnostics(app: Flask) -> None:
    with app.app_context():
        event = create_renewal_event(
            uuid4().hex, uuid4().hex, uuid4().hex, event_type=99999
        )
        db.session.add(event)
        db.session.commit()
        result = renewal.run_billing_renewal_event(
            app, renewal_event_bid=event.renewal_event_bid
        )
        assert result.to_task_payload()["status"] == "failed"
        db.session.expire_all()
        assert event.status == BILLING_RENEWAL_EVENT_STATUS_FAILED
        assert event.last_error == "renewal_event_handler_not_implemented:99999"


@pytest.mark.parametrize(
    "scope", ["missing", "owner", "subscription", "already-processing"]
)
def test_claim_respects_event_ownership_and_existing_worker(
    scope: str, app: Flask
) -> None:
    with app.app_context():
        event = create_renewal_event(
            uuid4().hex,
            uuid4().hex,
            uuid4().hex,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
        )
        if scope == "already-processing":
            event.status = BILLING_RENEWAL_EVENT_STATUS_PROCESSING
            event.attempt_count = 2
        db.session.add(event)
        db.session.commit()
        kwargs = (
            {"subscription_bid": event.subscription_bid}
            if scope == "subscription"
            else {
                "renewal_event_bid": "absent"
                if scope == "missing"
                else event.renewal_event_bid
            }
        )
        if scope == "owner":
            kwargs["creator_bid"] = "other-owner"
        result = renewal.claim_billing_renewal_event(app, **kwargs)
        db.session.expire_all()
        assert (
            result.status
            == {
                "missing": "event_not_found",
                "owner": "event_not_found",
                "subscription": "claimed",
                "already-processing": "already_claimed",
            }[scope]
        )
        assert event.attempt_count == (
            2 if scope == "already-processing" else int(scope == "subscription")
        )


@pytest.mark.parametrize("winner", ["processing", "completed", "deleted"])
def test_lost_claim_does_not_commit_stale_subscription_cancellation(
    winner: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        _, _, plan = _seed(subscription=True)
        event = create_renewal_event(
            uuid4().hex,
            plan.subscription_bid,
            plan.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
        )
        db.session.add(event)
        db.session.commit()
        event_id = event.id
        original_loader = renewal._load_subscription_by_bid
        raced: list[int] = []

        def concurrent_worker_claim(subscription_bid: str) -> object:
            subscription = original_loader(subscription_bid)
            if not raced:
                # Simulate a different worker after the first worker's durable
                # claim, before its cancellation transaction writes anything.
                with db.engine.begin() as connection:
                    connection.execute(
                        BillingRenewalEvent.__table__.update()
                        .where(BillingRenewalEvent.id == event_id)
                        .values(
                            attempt_count=2,
                            status=BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
                            if winner == "completed"
                            else BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
                            deleted=int(winner == "deleted"),
                        )
                    )
                raced.append(event_id)
            return subscription

        monkeypatch.setattr(
            renewal, "_load_subscription_by_bid", concurrent_worker_claim
        )
        result = renewal.run_billing_renewal_event(
            app, renewal_event_bid=event.renewal_event_bid
        )
        assert (
            result.status
            == {
                "processing": "lost_claim",
                "completed": "already_processed",
                "deleted": "event_not_found",
            }[winner]
        )
        db.session.expire_all()
        assert raced == [event_id]
        assert plan.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert plan.cancel_at_period_end == 0
        assert event.attempt_count == 2
        if winner != "deleted":
            assert result.to_task_payload()["message"] == "renewal_event_claim_lost"
