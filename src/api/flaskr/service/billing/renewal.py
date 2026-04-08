"""Renewal event claiming and execution helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Flask

from flaskr.dao import db

from .consts import (
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_LABELS,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_LABELS,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    BILLING_SUBSCRIPTION_STATUS_LABELS,
)
from .funcs import _load_subscription_by_bid, _sync_subscription_lifecycle_events
from .models import BillingRenewalEvent

_CLAIMABLE_EVENT_STATUSES = (
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
)
_TERMINAL_EVENT_STATUSES = (
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
)


def claim_billing_renewal_event(
    app: Flask,
    *,
    renewal_event_bid: str = "",
    subscription_bid: str = "",
    creator_bid: str = "",
) -> dict[str, Any]:
    """Atomically claim a renewal event for execution."""

    with app.app_context():
        status, event = _claim_target_renewal_event(
            renewal_event_bid=renewal_event_bid,
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
        )
        payload = {"status": status}
        if event is not None:
            payload.update(_serialize_renewal_event(event))
        else:
            payload.update(
                {
                    "renewal_event_bid": _normalize_bid(renewal_event_bid) or None,
                    "subscription_bid": _normalize_bid(subscription_bid) or None,
                    "creator_bid": _normalize_bid(creator_bid) or None,
                }
            )
        if status == "claimed":
            db.session.commit()
        return payload


def run_billing_renewal_event(
    app: Flask,
    *,
    renewal_event_bid: str = "",
    subscription_bid: str = "",
    creator_bid: str = "",
) -> dict[str, Any]:
    """Claim and execute a renewal event with idempotent state transitions."""

    with app.app_context():
        claim_status, event = _claim_target_renewal_event(
            renewal_event_bid=renewal_event_bid,
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
        )
        if event is None:
            return {
                "status": claim_status,
                "renewal_event_bid": _normalize_bid(renewal_event_bid) or None,
                "subscription_bid": _normalize_bid(subscription_bid) or None,
                "creator_bid": _normalize_bid(creator_bid) or None,
            }
        if claim_status != "claimed":
            return {
                "status": claim_status,
                **_serialize_renewal_event(event),
            }

        now = datetime.now()
        if event.scheduled_at and event.scheduled_at > now:
            _release_renewal_event(event, now=now)
            db.session.commit()
            return {
                "status": "deferred_until_scheduled_at",
                **_serialize_renewal_event(event),
            }

        if int(event.event_type or 0) == BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE:
            return _execute_cancel_effective(app, event, now=now)
        if int(event.event_type or 0) == BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE:
            return _execute_downgrade_effective(app, event, now=now)
        if int(event.event_type or 0) == BILLING_RENEWAL_EVENT_TYPE_EXPIRE:
            return _execute_expire_subscription(app, event, now=now)

        _fail_renewal_event(
            event,
            now=now,
            error=(
                "renewal_event_handler_not_implemented:"
                f"{BILLING_RENEWAL_EVENT_TYPE_LABELS.get(int(event.event_type or 0), event.event_type)}"
            ),
        )
        db.session.commit()
        return {
            "status": "failed",
            **_serialize_renewal_event(event),
        }


def _execute_cancel_effective(
    app: Flask,
    event: BillingRenewalEvent,
    *,
    now: datetime,
) -> dict[str, Any]:
    subscription = _load_subscription_by_bid(event.subscription_bid)
    if subscription is None:
        _fail_renewal_event(event, now=now, error="subscription_not_found")
        db.session.commit()
        return {
            "status": "failed",
            **_serialize_renewal_event(event),
        }

    if int(subscription.status or 0) in {
        BILLING_SUBSCRIPTION_STATUS_CANCELED,
        BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    }:
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return {
            "status": "already_applied",
            "subscription_status": BILLING_SUBSCRIPTION_STATUS_LABELS.get(
                int(subscription.status or 0), "canceled"
            ),
            **_serialize_renewal_event(event),
        }

    subscription.cancel_at_period_end = 1
    subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCELED
    subscription.updated_at = now
    db.session.add(subscription)
    _sync_subscription_lifecycle_events(app, subscription)
    _complete_renewal_event(event, now=now)
    db.session.commit()
    return {
        "status": "applied",
        "subscription_status": "canceled",
        **_serialize_renewal_event(event),
    }


def _execute_expire_subscription(
    app: Flask,
    event: BillingRenewalEvent,
    *,
    now: datetime,
) -> dict[str, Any]:
    subscription = _load_subscription_by_bid(event.subscription_bid)
    if subscription is None:
        _fail_renewal_event(event, now=now, error="subscription_not_found")
        db.session.commit()
        return {
            "status": "failed",
            **_serialize_renewal_event(event),
        }

    if int(subscription.status or 0) == BILLING_SUBSCRIPTION_STATUS_EXPIRED:
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return {
            "status": "already_applied",
            "subscription_status": "expired",
            **_serialize_renewal_event(event),
        }

    subscription.status = BILLING_SUBSCRIPTION_STATUS_EXPIRED
    subscription.updated_at = now
    db.session.add(subscription)
    _sync_subscription_lifecycle_events(app, subscription)
    _complete_renewal_event(event, now=now)
    db.session.commit()
    return {
        "status": "applied",
        "subscription_status": "expired",
        **_serialize_renewal_event(event),
    }


def _execute_downgrade_effective(
    app: Flask,
    event: BillingRenewalEvent,
    *,
    now: datetime,
) -> dict[str, Any]:
    subscription = _load_subscription_by_bid(event.subscription_bid)
    if subscription is None:
        _fail_renewal_event(event, now=now, error="subscription_not_found")
        db.session.commit()
        return {
            "status": "failed",
            **_serialize_renewal_event(event),
        }

    next_product_bid = _normalize_bid(subscription.next_product_bid)
    if not next_product_bid:
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return {
            "status": "already_applied",
            "product_bid": subscription.product_bid,
            **_serialize_renewal_event(event),
        }

    subscription.product_bid = next_product_bid
    subscription.next_product_bid = ""
    subscription.updated_at = now
    db.session.add(subscription)
    _sync_subscription_lifecycle_events(app, subscription)
    _complete_renewal_event(event, now=now)
    db.session.commit()
    return {
        "status": "applied",
        "product_bid": subscription.product_bid,
        **_serialize_renewal_event(event),
    }


def _claim_target_renewal_event(
    *,
    renewal_event_bid: str = "",
    subscription_bid: str = "",
    creator_bid: str = "",
) -> tuple[str, BillingRenewalEvent | None]:
    event = _load_target_renewal_event(
        renewal_event_bid=renewal_event_bid,
        subscription_bid=subscription_bid,
        creator_bid=creator_bid,
    )
    if event is None:
        return "event_not_found", None
    if int(event.status or 0) in _TERMINAL_EVENT_STATUSES:
        return "already_processed", event
    if int(event.status or 0) == BILLING_RENEWAL_EVENT_STATUS_PROCESSING:
        return "already_claimed", event

    now = datetime.now()
    expected_attempt_count = int(event.attempt_count or 0)
    updated_rows = BillingRenewalEvent.query.filter(
        BillingRenewalEvent.deleted == 0,
        BillingRenewalEvent.id == event.id,
        BillingRenewalEvent.status.in_(_CLAIMABLE_EVENT_STATUSES),
        BillingRenewalEvent.attempt_count == expected_attempt_count,
    ).update(
        {
            "status": BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
            "attempt_count": expected_attempt_count + 1,
            "updated_at": now,
        },
        synchronize_session=False,
    )
    if updated_rows != 1:
        db.session.expire_all()
        current = _load_target_renewal_event(
            renewal_event_bid=renewal_event_bid,
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
        )
        if current is None:
            return "event_not_found", None
        if int(current.status or 0) in _TERMINAL_EVENT_STATUSES:
            return "already_processed", current
        return "already_claimed", current

    db.session.flush()
    db.session.expire_all()
    claimed = _load_target_renewal_event(
        renewal_event_bid=renewal_event_bid,
        subscription_bid=subscription_bid,
        creator_bid=creator_bid,
    )
    return "claimed", claimed


def _release_renewal_event(event: BillingRenewalEvent, *, now: datetime) -> None:
    event.status = BILLING_RENEWAL_EVENT_STATUS_PENDING
    event.updated_at = now
    db.session.add(event)


def _complete_renewal_event(event: BillingRenewalEvent, *, now: datetime) -> None:
    event.status = BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
    event.last_error = ""
    event.processed_at = now
    event.updated_at = now
    db.session.add(event)


def _fail_renewal_event(
    event: BillingRenewalEvent,
    *,
    now: datetime,
    error: str,
) -> None:
    event.status = BILLING_RENEWAL_EVENT_STATUS_FAILED
    event.last_error = str(error or "")[:255]
    event.processed_at = now
    event.updated_at = now
    db.session.add(event)


def _load_target_renewal_event(
    *,
    renewal_event_bid: str = "",
    subscription_bid: str = "",
    creator_bid: str = "",
) -> BillingRenewalEvent | None:
    normalized_renewal_event_bid = _normalize_bid(renewal_event_bid)
    normalized_subscription_bid = _normalize_bid(subscription_bid)
    normalized_creator_bid = _normalize_bid(creator_bid)

    query = BillingRenewalEvent.query.filter(BillingRenewalEvent.deleted == 0)
    if normalized_creator_bid:
        query = query.filter(BillingRenewalEvent.creator_bid == normalized_creator_bid)
    if normalized_renewal_event_bid:
        query = query.filter(
            BillingRenewalEvent.renewal_event_bid == normalized_renewal_event_bid
        )
    elif normalized_subscription_bid:
        query = query.filter(
            BillingRenewalEvent.subscription_bid == normalized_subscription_bid
        )
        query = query.filter(
            BillingRenewalEvent.status.in_(
                _CLAIMABLE_EVENT_STATUSES + (BILLING_RENEWAL_EVENT_STATUS_PROCESSING,)
            )
        )
    else:
        return None
    return query.order_by(
        BillingRenewalEvent.scheduled_at.asc(),
        BillingRenewalEvent.id.asc(),
    ).first()


def _serialize_renewal_event(event: BillingRenewalEvent) -> dict[str, Any]:
    return {
        "renewal_event_bid": event.renewal_event_bid,
        "subscription_bid": event.subscription_bid,
        "creator_bid": event.creator_bid,
        "event_type": BILLING_RENEWAL_EVENT_TYPE_LABELS.get(
            int(event.event_type or 0), str(event.event_type or "")
        ),
        "event_status": BILLING_RENEWAL_EVENT_STATUS_LABELS.get(
            int(event.status or 0), str(event.status or "")
        ),
        "scheduled_at": event.scheduled_at.isoformat() if event.scheduled_at else None,
        "attempt_count": int(event.attempt_count or 0),
        "last_error": str(event.last_error or ""),
        "payload": event.payload_json or {},
    }


def _normalize_bid(value: Any) -> str:
    return str(value or "").strip()
