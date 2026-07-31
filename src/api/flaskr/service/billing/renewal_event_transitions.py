"""Renewal event persistence transitions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Flask

from flaskr.dao import db
from flaskr.util.datetime import now_utc
from flaskr.util.uuid import generate_id

from .consts import (
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_SUBSCRIPTION_STATUS_LABELS,
)
from .models import BillingRenewalEvent, BillingSubscription
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .primitives import normalize_mysql_datetime as _normalize_mysql_datetime

MANAGED_RENEWAL_EVENT_TYPES = (
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
)

PENDING_RENEWAL_EVENT_STATUSES = (
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
)


def release_renewal_event(event: BillingRenewalEvent, *, now: datetime) -> None:
    event.status = BILLING_RENEWAL_EVENT_STATUS_PENDING
    event.updated_at = now
    db.session.add(event)


def complete_renewal_event(event: BillingRenewalEvent, *, now: datetime) -> None:
    event.status = BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED
    event.last_error = ""
    event.processed_at = now
    event.updated_at = now
    db.session.add(event)


def fail_renewal_event(
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


def build_subscription_renewal_event_payload(
    subscription: BillingSubscription,
) -> dict[str, Any]:
    return _normalize_json_object(
        {
            "subscription_bid": subscription.subscription_bid,
            "creator_bid": subscription.creator_bid,
            "product_bid": subscription.product_bid,
            "next_product_bid": _normalize_bid(subscription.next_product_bid) or None,
            "status": BILLING_SUBSCRIPTION_STATUS_LABELS.get(
                subscription.status,
                "draft",
            ),
            "cancel_at_period_end": bool(subscription.cancel_at_period_end),
        }
    ).to_metadata_json()


def upsert_subscription_renewal_event(
    app: Flask,
    subscription: BillingSubscription,
    *,
    event_type: int,
    scheduled_at: datetime,
) -> None:
    normalized_scheduled_at = _normalize_mysql_datetime(scheduled_at)
    payload = build_subscription_renewal_event_payload(subscription)
    event = (
        BillingRenewalEvent.query.filter(
            BillingRenewalEvent.deleted == 0,
            BillingRenewalEvent.subscription_bid == subscription.subscription_bid,
            BillingRenewalEvent.event_type == event_type,
            BillingRenewalEvent.scheduled_at == normalized_scheduled_at,
        )
        .order_by(BillingRenewalEvent.id.desc())
        .first()
    )
    if event is None:
        event = BillingRenewalEvent(
            renewal_event_bid=generate_id(app),
            subscription_bid=subscription.subscription_bid,
            creator_bid=subscription.creator_bid,
            event_type=event_type,
            scheduled_at=normalized_scheduled_at,
            status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
            attempt_count=0,
            last_error="",
            payload_json=payload,
            processed_at=None,
        )
    else:
        event.creator_bid = subscription.creator_bid
        event.status = BILLING_RENEWAL_EVENT_STATUS_PENDING
        event.last_error = ""
        event.payload_json = payload
        event.processed_at = None
        event.updated_at = now_utc()

    db.session.add(event)
    cancel_stale_subscription_renewal_events(
        subscription.subscription_bid,
        event_type=event_type,
        keep_scheduled_at=normalized_scheduled_at,
    )


def cancel_stale_subscription_renewal_events(
    subscription_bid: str,
    *,
    event_type: int,
    keep_scheduled_at: datetime,
) -> None:
    rows = (
        BillingRenewalEvent.query.filter(
            BillingRenewalEvent.deleted == 0,
            BillingRenewalEvent.subscription_bid == subscription_bid,
            BillingRenewalEvent.event_type == event_type,
            BillingRenewalEvent.status.in_(PENDING_RENEWAL_EVENT_STATUSES),
            BillingRenewalEvent.scheduled_at != keep_scheduled_at,
        )
        .order_by(BillingRenewalEvent.id.desc())
        .all()
    )
    now = now_utc()
    for row in rows:
        row.status = BILLING_RENEWAL_EVENT_STATUS_CANCELED
        row.processed_at = now
        row.updated_at = now
        db.session.add(row)


def cancel_subscription_renewal_events(
    subscription_bid: str,
    *,
    event_types: tuple[int, ...] = MANAGED_RENEWAL_EVENT_TYPES,
) -> None:
    rows = (
        BillingRenewalEvent.query.filter(
            BillingRenewalEvent.deleted == 0,
            BillingRenewalEvent.subscription_bid == subscription_bid,
            BillingRenewalEvent.event_type.in_(event_types),
            BillingRenewalEvent.status.in_(PENDING_RENEWAL_EVENT_STATUSES),
        )
        .order_by(BillingRenewalEvent.id.desc())
        .all()
    )
    now = now_utc()
    for row in rows:
        row.status = BILLING_RENEWAL_EVENT_STATUS_CANCELED
        row.processed_at = now
        row.updated_at = now
        db.session.add(row)
