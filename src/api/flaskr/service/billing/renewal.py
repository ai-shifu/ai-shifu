"""Renewal event claiming and execution helpers."""

from __future__ import annotations

from dataclasses import dataclass
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
from .primitives import normalize_bid as _normalize_bid
from .wallets import _expire_credit_wallet_buckets_in_session

_CLAIMABLE_EVENT_STATUSES = (
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
)
_TERMINAL_EVENT_STATUSES = (
    BILLING_RENEWAL_EVENT_STATUS_SUCCEEDED,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
)


@dataclass(slots=True, frozen=True)
class RenewalEventSnapshot:
    renewal_event_bid: str | None
    subscription_bid: str | None
    creator_bid: str | None
    event_type: str | None
    event_status: str | None
    scheduled_at: str | None
    attempt_count: int
    last_error: str
    payload: Any

    def to_payload(self) -> dict[str, Any]:
        return {
            "renewal_event_bid": self.renewal_event_bid,
            "subscription_bid": self.subscription_bid,
            "creator_bid": self.creator_bid,
            "event_type": self.event_type,
            "event_status": self.event_status,
            "scheduled_at": self.scheduled_at,
            "attempt_count": self.attempt_count,
            "last_error": self.last_error,
            "payload": self.payload,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class RenewalEventResult:
    status: str
    event: RenewalEventSnapshot | None = None
    renewal_event_bid: str | None = None
    subscription_bid: str | None = None
    creator_bid: str | None = None
    bill_order_bid: str | None = None
    subscription_status: str | None = None
    product_bid: str | None = None
    message: str | None = None
    order_status: int | None = None

    def to_task_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": self.status}
        if self.event is not None:
            payload.update(self.event.to_payload())
        else:
            payload.update(
                {
                    "renewal_event_bid": self.renewal_event_bid,
                    "subscription_bid": self.subscription_bid,
                    "creator_bid": self.creator_bid,
                }
            )
        if self.bill_order_bid is not None:
            payload["bill_order_bid"] = self.bill_order_bid
        if self.subscription_status is not None:
            payload["subscription_status"] = self.subscription_status
        if self.product_bid is not None:
            payload["product_bid"] = self.product_bid
        if self.message is not None:
            payload["message"] = self.message
        if self.order_status is not None:
            payload["order_status"] = self.order_status
        return payload

    def __getitem__(self, key: str) -> Any:
        return self.to_task_payload()[key]


def claim_billing_renewal_event(
    app: Flask,
    *,
    renewal_event_bid: str = "",
    subscription_bid: str = "",
    creator_bid: str = "",
) -> RenewalEventResult:
    """Atomically claim a renewal event for execution."""

    with app.app_context():
        status, event = _claim_target_renewal_event(
            renewal_event_bid=renewal_event_bid,
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
        )
        if status == "claimed":
            db.session.commit()
        if event is not None:
            return _result_from_event(status, event)
        return _result_without_event(
            status,
            renewal_event_bid=renewal_event_bid,
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
        )


def run_billing_renewal_event(
    app: Flask,
    *,
    renewal_event_bid: str = "",
    subscription_bid: str = "",
    creator_bid: str = "",
) -> RenewalEventResult:
    """Claim and execute a renewal event with idempotent state transitions."""

    with app.app_context():
        claim_status, event = _claim_target_renewal_event(
            renewal_event_bid=renewal_event_bid,
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
        )
        if event is None:
            return _result_without_event(
                claim_status,
                renewal_event_bid=renewal_event_bid,
                subscription_bid=subscription_bid,
                creator_bid=creator_bid,
            )
        if claim_status != "claimed":
            return _result_from_event(claim_status, event)

        now = datetime.now()
        if event.scheduled_at and event.scheduled_at > now:
            _release_renewal_event(event, now=now)
            db.session.commit()
            return _result_from_event("deferred_until_scheduled_at", event)

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
        return _result_from_event("failed", event)


def retry_billing_renewal_event(
    app: Flask,
    *,
    renewal_event_bid: str = "",
    subscription_bid: str = "",
    creator_bid: str = "",
    bill_order_bid: str = "",
    provider_reference_id: str = "",
    payment_provider: str = "",
) -> RenewalEventResult:
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
            bill_order_bid=bill_order_bid,
            subscription_bid=subscription_bid,
        )
        if order is None:
            return RenewalEventResult(
                status="order_not_found",
                renewal_event_bid=_normalize_bid(renewal_event_bid) or None,
                subscription_bid=_normalize_bid(subscription_bid)
                or (event.subscription_bid if event is not None else None),
                creator_bid=_normalize_bid(creator_bid)
                or (event.creator_bid if event is not None else None),
                bill_order_bid=_normalize_bid(bill_order_bid) or None,
            )

    return _sync_billing_renewal_order(app, order=order, event=event)


def _execute_cancel_effective(
    app: Flask,
    event: BillingRenewalEvent,
    *,
    now: datetime,
) -> RenewalEventResult:
    subscription = _load_subscription_by_bid(event.subscription_bid)
    if subscription is None:
        _fail_renewal_event(event, now=now, error="subscription_not_found")
        db.session.commit()
        return _result_from_event("failed", event)

    if int(subscription.status or 0) in {
        BILLING_SUBSCRIPTION_STATUS_CANCELED,
        BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    }:
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return _result_from_event(
            "already_applied",
            event,
            subscription_status=BILLING_SUBSCRIPTION_STATUS_LABELS.get(
                int(subscription.status or 0), "canceled"
            ),
        )

    subscription.cancel_at_period_end = 1
    subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCELED
    subscription.updated_at = now
    db.session.add(subscription)
    _sync_subscription_lifecycle_events(app, subscription)
    _complete_renewal_event(event, now=now)
    db.session.commit()
    return _result_from_event("applied", event, subscription_status="canceled")


def _execute_expire_subscription(
    app: Flask,
    event: BillingRenewalEvent,
    *,
    now: datetime,
) -> RenewalEventResult:
    subscription = _load_subscription_by_bid(event.subscription_bid)
    boundary_at = event.scheduled_at or (
        subscription.current_period_end_at if subscription is not None else None
    )
    if subscription is None:
        _fail_renewal_event(event, now=now, error="subscription_not_found")
        db.session.commit()
        return _result_from_event("failed", event)

    if int(subscription.status or 0) == BILLING_SUBSCRIPTION_STATUS_EXPIRED:
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return _result_from_event(
            "already_applied", event, subscription_status="expired"
        )

    if (
        boundary_at is not None
        and subscription.current_period_start_at is not None
        and subscription.current_period_start_at >= boundary_at
    ):
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return _result_from_event(
            "already_applied",
            event,
            subscription_status=BILLING_SUBSCRIPTION_STATUS_LABELS.get(
                int(subscription.status or 0),
                "active",
            ),
        )

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
        return _result_from_event(
            "applied",
            event,
            bill_order_bid=paid_renewal_order.bill_order_bid,
            subscription_status=BILLING_SUBSCRIPTION_STATUS_LABELS.get(
                int(subscription.status or 0),
                "active",
            ),
        )

    _expire_credit_wallet_buckets_in_session(
        app,
        creator_bid=subscription.creator_bid,
        expire_before=boundary_at or now,
    )
    subscription.status = BILLING_SUBSCRIPTION_STATUS_EXPIRED
    subscription.updated_at = now
    db.session.add(subscription)
    _sync_subscription_lifecycle_events(app, subscription)
    _complete_renewal_event(event, now=now)
    db.session.commit()
    return _result_from_event("applied", event, subscription_status="expired")


def _execute_downgrade_effective(
    app: Flask,
    event: BillingRenewalEvent,
    *,
    now: datetime,
) -> RenewalEventResult:
    subscription = _load_subscription_by_bid(event.subscription_bid)
    if subscription is None:
        _fail_renewal_event(event, now=now, error="subscription_not_found")
        db.session.commit()
        return _result_from_event("failed", event)

    next_product_bid = _normalize_bid(subscription.next_product_bid)
    if not next_product_bid:
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return _result_from_event(
            "already_applied",
            event,
            product_bid=subscription.product_bid,
        )

    subscription.product_bid = next_product_bid
    subscription.next_product_bid = ""
    subscription.updated_at = now
    db.session.add(subscription)
    _sync_subscription_lifecycle_events(app, subscription)
    _complete_renewal_event(event, now=now)
    db.session.commit()
    return _result_from_event("applied", event, product_bid=subscription.product_bid)


def _execute_subscription_renewal(
    app: Flask,
    event: BillingRenewalEvent,
    *,
    now: datetime,
) -> RenewalEventResult:
    subscription = _load_subscription_by_bid(event.subscription_bid)
    if subscription is None:
        _fail_renewal_event(event, now=now, error="subscription_not_found")
        db.session.commit()
        return _result_from_event("failed", event)

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
        return _result_from_event("failed", event)

    payload_json = (
        dict(event.payload_json) if isinstance(event.payload_json, dict) else {}
    )
    payload_json["bill_order_bid"] = order.bill_order_bid
    event.payload_json = payload_json
    db.session.add(event)

    if order.payment_provider == "pingxx" and not order.provider_reference_id:
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return _result_from_event(
            "queued_for_reconcile",
            event,
            bill_order_bid=order.bill_order_bid,
        )

    result = _sync_billing_renewal_order(app, order=order, event=event)
    sync_status = str(result.status or "")
    if sync_status in {"paid", "applied", "already_applied"}:
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return _result_from_event(
            "applied",
            event,
            bill_order_bid=order.bill_order_bid,
        )
    if sync_status == "pending":
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return _result_from_event(
            "queued_for_reconcile",
            event,
            bill_order_bid=order.bill_order_bid,
        )

    _fail_renewal_event(
        event,
        now=now,
        error=str(result.message or sync_status or "renewal_sync_failed"),
    )
    db.session.commit()
    return _result_from_event("failed", event, bill_order_bid=order.bill_order_bid)


def _execute_retry_or_reconcile(
    app: Flask,
    event: BillingRenewalEvent,
    *,
    now: datetime,
) -> RenewalEventResult:
    result = retry_billing_renewal_event(
        app,
        renewal_event_bid=event.renewal_event_bid,
        subscription_bid=event.subscription_bid,
        creator_bid=event.creator_bid,
    )
    result_status = str(result.status or "")
    if result_status in {"paid", "applied", "already_applied"}:
        _complete_renewal_event(event, now=now)
        db.session.commit()
        return _result_from_event("applied", event)

    _fail_renewal_event(
        event,
        now=now,
        error=str(result.message or result_status or "renewal_retry_pending"),
    )
    db.session.commit()
    return _result_from_event(
        "failed" if result_status != "order_not_found" else "order_not_found",
        event,
    )


def _resolve_retry_target_order(
    *,
    event: BillingRenewalEvent | None,
    bill_order_bid: str = "",
    subscription_bid: str = "",
) -> BillingOrder | None:
    normalized_bill_order_bid = _normalize_bid(bill_order_bid)
    if normalized_bill_order_bid:
        return (
            BillingOrder.query.filter(
                BillingOrder.deleted == 0,
                BillingOrder.bill_order_bid == normalized_bill_order_bid,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )

    if event is not None and isinstance(event.payload_json, dict):
        payload_order_bid = _normalize_bid(event.payload_json.get("bill_order_bid"))
        if payload_order_bid:
            return (
                BillingOrder.query.filter(
                    BillingOrder.deleted == 0,
                    BillingOrder.bill_order_bid == payload_order_bid,
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
) -> RenewalEventResult:
    bill_order_bid = str(order.bill_order_bid or "")
    if order.payment_provider == "pingxx" and not order.provider_reference_id:
        return RenewalEventResult(
            status="pending",
            bill_order_bid=bill_order_bid or None,
            renewal_event_bid=event.renewal_event_bid if event is not None else None,
        )
    try:
        payload = sync_billing_order(
            app,
            order.creator_bid,
            bill_order_bid,
            {},
        )
    except Exception as exc:
        db.session.expire_all()
        refreshed_order = (
            BillingOrder.query.filter(
                BillingOrder.deleted == 0,
                BillingOrder.bill_order_bid == bill_order_bid,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
        return RenewalEventResult(
            status="failed",
            message=str(exc),
            bill_order_bid=bill_order_bid or None,
            renewal_event_bid=event.renewal_event_bid if event is not None else None,
            order_status=(
                int(refreshed_order.status or 0)
                if refreshed_order is not None
                else None
            ),
        )
    return RenewalEventResult(
        status=payload["status"] if isinstance(payload, dict) else payload.status,
        renewal_event_bid=event.renewal_event_bid if event is not None else None,
        bill_order_bid=bill_order_bid or None,
    )


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


def _serialize_renewal_event(event: BillingRenewalEvent) -> RenewalEventSnapshot:
    return RenewalEventSnapshot(
        renewal_event_bid=event.renewal_event_bid,
        subscription_bid=event.subscription_bid,
        creator_bid=event.creator_bid,
        event_type=BILLING_RENEWAL_EVENT_TYPE_LABELS.get(
            int(event.event_type or 0), str(event.event_type or "")
        ),
        event_status=BILLING_RENEWAL_EVENT_STATUS_LABELS.get(
            int(event.status or 0), str(event.status or "")
        ),
        scheduled_at=event.scheduled_at.isoformat() if event.scheduled_at else None,
        attempt_count=int(event.attempt_count or 0),
        last_error=str(event.last_error or ""),
        payload=event.payload_json or {},
    )


def _result_from_event(
    status: str,
    event: BillingRenewalEvent,
    *,
    bill_order_bid: str | None = None,
    subscription_status: str | None = None,
    product_bid: str | None = None,
    message: str | None = None,
    order_status: int | None = None,
) -> RenewalEventResult:
    return RenewalEventResult(
        status=status,
        event=_serialize_renewal_event(event),
        bill_order_bid=bill_order_bid,
        subscription_status=subscription_status,
        product_bid=product_bid,
        message=message,
        order_status=order_status,
    )


def _result_without_event(
    status: str,
    *,
    renewal_event_bid: str = "",
    subscription_bid: str = "",
    creator_bid: str = "",
) -> RenewalEventResult:
    return RenewalEventResult(
        status=status,
        renewal_event_bid=_normalize_bid(renewal_event_bid) or None,
        subscription_bid=_normalize_bid(subscription_bid) or None,
        creator_bid=_normalize_bid(creator_bid) or None,
    )
