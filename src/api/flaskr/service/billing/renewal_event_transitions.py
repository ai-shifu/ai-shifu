"""Renewal event persistence transitions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Flask
from sqlalchemy.exc import IntegrityError

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

CANCELABLE_RENEWAL_EVENT_STATUSES = (
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
)


def _update_processing_renewal_event(
    event: BillingRenewalEvent,
    values: dict[str, Any],
) -> bool:
    updated_rows = BillingRenewalEvent.query.filter(
        BillingRenewalEvent.deleted == 0,
        BillingRenewalEvent.id == event.id,
        BillingRenewalEvent.status == BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    ).update(values, synchronize_session=False)
    db.session.flush()
    db.session.expire(event)
    return updated_rows == 1


def release_renewal_event(event: BillingRenewalEvent, *, now: datetime) -> bool:
    return _update_processing_renewal_event(
        event,
        {
            "status": BILLING_RENEWAL_EVENT_STATUS_PENDING,
            "updated_at": now,
        },
    )


def complete_renewal_event(event: BillingRenewalEvent, *, now: datetime) -> bool:
    return _update_processing_renewal_event(
        event,
        {
            "status": BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
            "last_error": "",
            "processed_at": now,
            "updated_at": now,
        },
    )


def fail_renewal_event(
    event: BillingRenewalEvent,
    *,
    now: datetime,
    error: str,
) -> bool:
    return _update_processing_renewal_event(
        event,
        {
            "status": BILLING_RENEWAL_EVENT_STATUS_FAILED,
            "last_error": str(error or "")[:255],
            "processed_at": now,
            "updated_at": now,
        },
    )


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


def _load_subscription_renewal_event(
    subscription_bid: str,
    *,
    event_type: int,
    scheduled_at: datetime,
) -> BillingRenewalEvent | None:
    return (
        BillingRenewalEvent.query.filter(
            BillingRenewalEvent.deleted == 0,
            BillingRenewalEvent.subscription_bid == subscription_bid,
            BillingRenewalEvent.event_type == event_type,
            BillingRenewalEvent.scheduled_at == scheduled_at,
        )
        .order_by(BillingRenewalEvent.id.desc())
        .first()
    )


def _reset_subscription_renewal_event(
    event: BillingRenewalEvent,
    subscription: BillingSubscription,
    *,
    payload: dict[str, Any],
) -> None:
    if int(event.status or 0) == BILLING_RENEWAL_EVENT_STATUS_PROCESSING:
        return
    event.creator_bid = subscription.creator_bid
    event.status = BILLING_RENEWAL_EVENT_STATUS_PENDING
    event.last_error = ""
    event.payload_json = payload
    event.processed_at = None
    event.updated_at = now_utc()
    db.session.add(event)


def _build_subscription_renewal_event(
    app: Flask,
    subscription: BillingSubscription,
    *,
    event_type: int,
    scheduled_at: datetime,
    payload: dict[str, Any],
) -> BillingRenewalEvent:
    return BillingRenewalEvent(
        renewal_event_bid=generate_id(app),
        subscription_bid=subscription.subscription_bid,
        creator_bid=subscription.creator_bid,
        event_type=event_type,
        scheduled_at=scheduled_at,
        status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
        attempt_count=0,
        last_error="",
        payload_json=payload,
        processed_at=None,
    )


def upsert_subscription_renewal_event(
    app: Flask,
    subscription: BillingSubscription,
    *,
    event_type: int,
    scheduled_at: datetime,
) -> None:
    normalized_scheduled_at = _normalize_mysql_datetime(scheduled_at)
    payload = build_subscription_renewal_event_payload(subscription)
    event = _load_subscription_renewal_event(
        subscription.subscription_bid,
        event_type=event_type,
        scheduled_at=normalized_scheduled_at,
    )
    if event is None:
        try:
            with db.session.begin_nested():
                event = _build_subscription_renewal_event(
                    app,
                    subscription,
                    event_type=event_type,
                    scheduled_at=normalized_scheduled_at,
                    payload=payload,
                )
                db.session.add(event)
                db.session.flush()
        except IntegrityError:
            event = _load_subscription_renewal_event(
                subscription.subscription_bid,
                event_type=event_type,
                scheduled_at=normalized_scheduled_at,
            )
            if event is None:
                raise
            _reset_subscription_renewal_event(event, subscription, payload=payload)
    else:
        _reset_subscription_renewal_event(event, subscription, payload=payload)

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
            BillingRenewalEvent.status.in_(CANCELABLE_RENEWAL_EVENT_STATUSES),
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
            BillingRenewalEvent.status.in_(CANCELABLE_RENEWAL_EVENT_STATUSES),
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
