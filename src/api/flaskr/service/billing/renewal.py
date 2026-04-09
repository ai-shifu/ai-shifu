"""Renewal event claiming and execution helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Flask

from flaskr.dao import db

from .consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PENDING,
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
    BILLING_RENEWAL_EVENT_TYPE_RECONCILE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    BILLING_SUBSCRIPTION_STATUS_LABELS,
)
from .checkout import sync_billing_order
from .subscriptions import (
    activate_subscription_for_paid_order as _activate_subscription_for_paid_order,
    ensure_subscription_renewal_order,
    load_latest_subscription_renewal_order as _load_latest_subscription_renewal_order,
    load_subscription_by_bid as _load_subscription_by_bid,
    load_subscription_renewal_order_by_cycle as _load_subscription_renewal_order_by_cycle,
    sync_subscription_lifecycle_events as _sync_subscription_lifecycle_events,
)
from .models import BillingOrder, BillingRenewalEvent

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
        if int(event.event_type or 0) == BILLING_RENEWAL_EVENT_TYPE_RENEWAL:
            return _execute_subscription_renewal(app, event, now=now)
        if int(event.event_type or 0) in {
            BILLING_RENEWAL_EVENT_TYPE_RETRY,
            BILLING_RENEWAL_EVENT_TYPE_RECONCILE,
        }:
            return _execute_retry_or_reconcile(app, event, now=now)
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


def retry_billing_renewal_event(
    app: Flask,
    *,
    renewal_event_bid: str = "",
    subscription_bid: str = "",
    creator_bid: str = "",
    billing_order_bid: str = "",
    provider_reference_id: str = "",
    payment_provider: str = "",
) -> dict[str, Any]:
    """Resolve the latest renewal order context and sync it with the provider."""

    del provider_reference_id, payment_provider

    with app.app_context():
        event = _load_target_renewal_event(
            renewal_event_bid=renewal_event_bid,
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
        )
        order = _resolve_retry_target_order(
            event=event,
            billing_order_bid=billing_order_bid,
            subscription_bid=subscription_bid,
        )
        if order is None:
            return {
                "status": "order_not_found",
                "renewal_event_bid": _normalize_bid(renewal_event_bid) or None,
                "subscription_bid": _normalize_bid(subscription_bid)
                or (event.subscription_bid if event is not None else None),
                "creator_bid": _normalize_bid(creator_bid)
                or (event.creator_bid if event is not None else None),
                "billing_order_bid": _normalize_bid(billing_order_bid) or None,
            }

    return _sync_billing_renewal_order(app, order=order, event=event)


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
    boundary_at = event.scheduled_at or (
        subscription.current_period_end_at if subscription is not None else None
    )
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

    if (
        boundary_at is not None
        and subscription.current_period_start_at is not None
        and subscription.current_period_start_at >= boundary_at
    ):
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return {
            "status": "already_applied",
            "subscription_status": BILLING_SUBSCRIPTION_STATUS_LABELS.get(
                int(subscription.status or 0),
                "active",
            ),
            **_serialize_renewal_event(event),
        }

    paid_renewal_order = None
    if boundary_at is not None:
        paid_renewal_order = _load_subscription_renewal_order_by_cycle(
            subscription.subscription_bid,
            cycle_start_at=boundary_at,
            statuses=(BILLING_ORDER_STATUS_PAID,),
        )
    if paid_renewal_order is not None:
        _activate_subscription_for_paid_order(
            app,
            paid_renewal_order,
            subscription=subscription,
            force=True,
        )
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return {
            "status": "applied",
            "billing_order_bid": paid_renewal_order.billing_order_bid,
            "subscription_status": BILLING_SUBSCRIPTION_STATUS_LABELS.get(
                int(subscription.status or 0),
                "active",
            ),
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


def _execute_subscription_renewal(
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

    order = ensure_subscription_renewal_order(
        app,
        subscription,
        renewal_event_bid=event.renewal_event_bid,
        scheduled_at=event.scheduled_at or subscription.current_period_end_at,
    )
    if order is None:
        _fail_renewal_event(
            event,
            now=now,
            error="renewal_order_context_unavailable",
        )
        db.session.commit()
        return {
            "status": "failed",
            **_serialize_renewal_event(event),
        }

    payload_json = (
        dict(event.payload_json) if isinstance(event.payload_json, dict) else {}
    )
    payload_json["billing_order_bid"] = order.billing_order_bid
    event.payload_json = payload_json
    db.session.add(event)

    if order.payment_provider == "pingxx" and not order.provider_reference_id:
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return {
            "status": "queued_for_reconcile",
            "billing_order_bid": order.billing_order_bid,
            **_serialize_renewal_event(event),
        }

    result = _sync_billing_renewal_order(app, order=order, event=event)
    sync_status = str(result.get("status") or "")
    if sync_status in {"paid", "applied", "already_applied"}:
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return {
            "status": "applied",
            "billing_order_bid": order.billing_order_bid,
            **_serialize_renewal_event(event),
        }
    if sync_status == "pending":
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return {
            "status": "queued_for_reconcile",
            "billing_order_bid": order.billing_order_bid,
            **_serialize_renewal_event(event),
        }

    _fail_renewal_event(
        event,
        now=now,
        error=str(result.get("message") or sync_status or "renewal_sync_failed"),
    )
    db.session.commit()
    return {
        "status": "failed",
        "billing_order_bid": order.billing_order_bid,
        **_serialize_renewal_event(event),
    }


def _execute_retry_or_reconcile(
    app: Flask,
    event: BillingRenewalEvent,
    *,
    now: datetime,
) -> dict[str, Any]:
    result = retry_billing_renewal_event(
        app,
        renewal_event_bid=event.renewal_event_bid,
        subscription_bid=event.subscription_bid,
        creator_bid=event.creator_bid,
    )
    result_status = str(result.get("status") or "")
    if result_status in {"paid", "applied", "already_applied"}:
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return {
            "status": "applied",
            **_serialize_renewal_event(event),
        }

    _fail_renewal_event(
        event,
        now=now,
        error=str(result.get("message") or result_status or "renewal_retry_pending"),
    )
    db.session.commit()
    return {
        "status": "failed" if result_status != "order_not_found" else "order_not_found",
        **_serialize_renewal_event(event),
    }


def _resolve_retry_target_order(
    *,
    event: BillingRenewalEvent | None,
    billing_order_bid: str = "",
    subscription_bid: str = "",
) -> BillingOrder | None:
    normalized_billing_order_bid = _normalize_bid(billing_order_bid)
    if normalized_billing_order_bid:
        return (
            BillingOrder.query.filter(
                BillingOrder.deleted == 0,
                BillingOrder.billing_order_bid == normalized_billing_order_bid,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )

    if event is not None and isinstance(event.payload_json, dict):
        payload_order_bid = _normalize_bid(event.payload_json.get("billing_order_bid"))
        if payload_order_bid:
            return (
                BillingOrder.query.filter(
                    BillingOrder.deleted == 0,
                    BillingOrder.billing_order_bid == payload_order_bid,
                )
                .order_by(BillingOrder.id.desc())
                .first()
            )

    target_subscription_bid = _normalize_bid(subscription_bid) or (
        event.subscription_bid if event is not None else ""
    )
    return _load_latest_subscription_renewal_order(
        target_subscription_bid,
        statuses=(
            BILLING_ORDER_STATUS_PENDING,
            BILLING_ORDER_STATUS_FAILED,
        ),
    )


def _sync_billing_renewal_order(
    app: Flask,
    *,
    order: BillingOrder,
    event: BillingRenewalEvent | None,
) -> dict[str, Any]:
    billing_order_bid = str(order.billing_order_bid or "")
    if order.payment_provider == "pingxx" and not order.provider_reference_id:
        return {
            "status": "pending",
            "billing_order_bid": billing_order_bid or None,
            "renewal_event_bid": (
                event.renewal_event_bid if event is not None else None
            ),
        }
    try:
        payload = sync_billing_order(
            app,
            order.creator_bid,
            billing_order_bid,
            {},
        )
    except Exception as exc:
        db.session.expire_all()
        refreshed_order = (
            BillingOrder.query.filter(
                BillingOrder.deleted == 0,
                BillingOrder.billing_order_bid == billing_order_bid,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
        return {
            "status": "failed",
            "message": str(exc),
            "billing_order_bid": billing_order_bid or None,
            "renewal_event_bid": (
                event.renewal_event_bid if event is not None else None
            ),
            "order_status": (
                int(refreshed_order.status or 0)
                if refreshed_order is not None
                else None
            ),
        }

    payload["renewal_event_bid"] = (
        event.renewal_event_bid if event is not None else None
    )
    payload["billing_order_bid"] = billing_order_bid or None
    return payload


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
