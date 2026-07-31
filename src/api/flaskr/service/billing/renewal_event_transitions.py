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

RESETTABLE_RENEWAL_EVENT_STATUSES = (
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
)

_TARGET_UPSERT_UNIQUE_KEY_NAME = "uq_bill_renewal_events_subscription_event_scheduled"
_CLAIM_ATTEMPT_ATTR = "_billing_renewal_claim_attempt_count"


class RenewalEventClaimLostError(RuntimeError):
    """Raised when a worker no longer owns the event processing claim."""


def bind_renewal_event_claim(
    event: BillingRenewalEvent,
    *,
    attempt_count: int,
) -> None:
    setattr(event, _CLAIM_ATTEMPT_ATTR, int(attempt_count or 0))


def _expected_claim_attempt_count(event: BillingRenewalEvent) -> int:
    bound_attempt_count = getattr(event, _CLAIM_ATTEMPT_ATTR, None)
    if bound_attempt_count is not None:
        return int(bound_attempt_count or 0)
    return int(event.attempt_count or 0)


def _is_target_upsert_integrity_error(exc: IntegrityError) -> bool:
    message = str(getattr(exc, "orig", exc))
    return _TARGET_UPSERT_UNIQUE_KEY_NAME in message or (
        "subscription_bid" in message
        and "event_type" in message
        and "scheduled_at" in message
    )


def _update_processing_renewal_event(
    event: BillingRenewalEvent,
    values: dict[str, Any],
) -> None:
    expected_attempt_count = _expected_claim_attempt_count(event)
    updated_rows = BillingRenewalEvent.query.filter(
        BillingRenewalEvent.deleted == 0,
        BillingRenewalEvent.id == event.id,
        BillingRenewalEvent.status == BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
        BillingRenewalEvent.attempt_count == expected_attempt_count,
    ).update(values, synchronize_session=False)
    db.session.flush()
    db.session.expire(event)
    if updated_rows != 1:
        raise RenewalEventClaimLostError(
            f"renewal_event_claim_lost:{event.renewal_event_bid}"
        )


def release_renewal_event(event: BillingRenewalEvent, *, now: datetime) -> None:
    return _update_processing_renewal_event(
        event,
        {
            "status": BILLING_RENEWAL_EVENT_STATUS_PENDING,
            "updated_at": now,
        },
    )


def complete_renewal_event(event: BillingRenewalEvent, *, now: datetime) -> None:
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
) -> None:
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
    for_update: bool = False,
) -> BillingRenewalEvent | None:
    query = BillingRenewalEvent.query.filter(
        BillingRenewalEvent.deleted == 0,
        BillingRenewalEvent.subscription_bid == subscription_bid,
        BillingRenewalEvent.event_type == event_type,
        BillingRenewalEvent.scheduled_at == scheduled_at,
    )
    if for_update:
        query = query.populate_existing().with_for_update()
    return query.order_by(BillingRenewalEvent.id.desc()).first()


def _reset_subscription_renewal_event(
    event: BillingRenewalEvent,
    subscription: BillingSubscription,
    *,
    payload: dict[str, Any],
) -> None:
    BillingRenewalEvent.query.filter(
        BillingRenewalEvent.deleted == 0,
        BillingRenewalEvent.id == event.id,
        BillingRenewalEvent.status.in_(RESETTABLE_RENEWAL_EVENT_STATUSES),
    ).update(
        {
            "creator_bid": subscription.creator_bid,
            "status": BILLING_RENEWAL_EVENT_STATUS_PENDING,
            "last_error": "",
            "payload_json": payload,
            "processed_at": None,
            "updated_at": now_utc(),
        },
        synchronize_session=False,
    )
    db.session.flush()
    db.session.expire(event)


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
        except IntegrityError as exc:
            if not _is_target_upsert_integrity_error(exc):
                raise
            event = _load_subscription_renewal_event(
                subscription.subscription_bid,
                event_type=event_type,
                scheduled_at=normalized_scheduled_at,
                for_update=True,
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
    now = now_utc()
    BillingRenewalEvent.query.filter(
        BillingRenewalEvent.deleted == 0,
        BillingRenewalEvent.subscription_bid == subscription_bid,
        BillingRenewalEvent.event_type == event_type,
        BillingRenewalEvent.status.in_(CANCELABLE_RENEWAL_EVENT_STATUSES),
        BillingRenewalEvent.scheduled_at != keep_scheduled_at,
    ).update(
        {
            "status": BILLING_RENEWAL_EVENT_STATUS_CANCELED,
            "processed_at": now,
            "updated_at": now,
        },
        synchronize_session=False,
    )


def cancel_subscription_renewal_events(
    subscription_bid: str,
    *,
    event_types: tuple[int, ...] = MANAGED_RENEWAL_EVENT_TYPES,
) -> None:
    now = now_utc()
    BillingRenewalEvent.query.filter(
        BillingRenewalEvent.deleted == 0,
        BillingRenewalEvent.subscription_bid == subscription_bid,
        BillingRenewalEvent.event_type.in_(event_types),
        BillingRenewalEvent.status.in_(CANCELABLE_RENEWAL_EVENT_STATUSES),
    ).update(
        {
            "status": BILLING_RENEWAL_EVENT_STATUS_CANCELED,
            "processed_at": now,
            "updated_at": now,
        },
        synchronize_session=False,
    )
