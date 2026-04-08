"""Task entrypoints for billing background jobs."""

from __future__ import annotations

from datetime import datetime
import os
from typing import Any, Callable

from .consts import (
    BILLING_RENEWAL_EVENT_STATUS_LABELS,
    BILLING_RENEWAL_EVENT_TYPE_LABELS,
)
from .funcs import build_billing_overview, sync_billing_order
from .models import BillingOrder, BillingRenewalEvent, BillingSubscription, CreditWallet
from .settlement import replay_bill_usage_settlement, settle_bill_usage
from .wallets import expire_credit_wallet_buckets

try:  # pragma: no cover - exercised indirectly when Celery is installed
    from celery import shared_task
except ImportError:  # pragma: no cover - local fallback for non-Celery test envs

    def shared_task(*args, **kwargs):
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return decorator


def _create_task_app():
    os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")
    from app import create_app

    return create_app()


def _normalize_bid(value: Any) -> str:
    return str(value or "").strip()


def _coerce_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    raise ValueError(f"Unsupported datetime value: {value!r}")


def _load_target_billing_order(
    *,
    creator_bid: str = "",
    billing_order_bid: str = "",
    provider_reference_id: str = "",
    payment_provider: str = "",
):
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_billing_order_bid = _normalize_bid(billing_order_bid)
    normalized_provider_reference_id = _normalize_bid(provider_reference_id)
    normalized_payment_provider = _normalize_bid(payment_provider)

    query = BillingOrder.query.filter(BillingOrder.deleted == 0)
    if normalized_creator_bid:
        query = query.filter(BillingOrder.creator_bid == normalized_creator_bid)
    if normalized_billing_order_bid:
        query = query.filter(
            BillingOrder.billing_order_bid == normalized_billing_order_bid
        )
    elif normalized_provider_reference_id:
        query = query.filter(
            BillingOrder.provider_reference_id == normalized_provider_reference_id
        )
    else:
        return None
    if normalized_payment_provider:
        query = query.filter(
            BillingOrder.payment_provider == normalized_payment_provider
        )
    return query.order_by(BillingOrder.id.desc()).first()


def _load_target_renewal_event(
    *,
    renewal_event_bid: str = "",
    subscription_bid: str = "",
    creator_bid: str = "",
):
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
    else:
        return None
    return query.order_by(
        BillingRenewalEvent.scheduled_at.asc(),
        BillingRenewalEvent.id.asc(),
    ).first()


def _run_reconcile_provider_reference(
    app,
    *,
    creator_bid: str = "",
    payment_provider: str = "",
    provider_reference_id: str = "",
    billing_order_bid: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_payment_provider = _normalize_bid(payment_provider)
    normalized_provider_reference_id = _normalize_bid(provider_reference_id)
    normalized_billing_order_bid = _normalize_bid(billing_order_bid)
    normalized_session_id = _normalize_bid(session_id)

    with app.app_context():
        order = _load_target_billing_order(
            creator_bid=normalized_creator_bid,
            billing_order_bid=normalized_billing_order_bid,
            provider_reference_id=normalized_provider_reference_id,
            payment_provider=normalized_payment_provider,
        )
        if order is None:
            return {
                "status": "order_not_found",
                "creator_bid": normalized_creator_bid or None,
                "billing_order_bid": normalized_billing_order_bid or None,
                "provider_reference_id": normalized_provider_reference_id or None,
                "payment_provider": normalized_payment_provider or None,
            }

    sync_payload: dict[str, Any] = {}
    if order.payment_provider == "stripe":
        resolved_session_id = normalized_session_id or normalized_provider_reference_id
        if resolved_session_id:
            sync_payload["session_id"] = resolved_session_id

    payload = sync_billing_order(
        app,
        order.creator_bid,
        order.billing_order_bid,
        sync_payload,
    )
    payload["creator_bid"] = order.creator_bid
    payload["billing_order_bid"] = order.billing_order_bid
    payload["payment_provider"] = order.payment_provider
    payload["provider_reference_id"] = (
        normalized_provider_reference_id or order.provider_reference_id or None
    )
    return payload


def _serialize_renewal_event_snapshot(event: BillingRenewalEvent) -> dict[str, Any]:
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
        "payload": event.payload_json or {},
    }


def _collect_low_balance_creator_bids() -> list[str]:
    wallet_creator_rows = (
        CreditWallet.query.filter(
            CreditWallet.deleted == 0,
            CreditWallet.creator_bid != "",
        )
        .order_by(CreditWallet.id.asc())
        .all()
    )
    subscription_creator_rows = (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid != "",
        )
        .order_by(BillingSubscription.id.asc())
        .all()
    )
    creator_bids = {
        _normalize_bid(row.creator_bid)
        for row in (*wallet_creator_rows, *subscription_creator_rows)
        if _normalize_bid(row.creator_bid)
    }
    return sorted(creator_bids)


@shared_task(name="billing.settle_usage")
def settle_usage_task(*, creator_bid: str = "", usage_bid: str = "") -> dict[str, Any]:
    """Default async entrypoint for usage credit settlement."""

    app = _create_task_app()
    payload = settle_bill_usage(app, usage_bid=usage_bid)
    payload["requested_creator_bid"] = str(creator_bid or "").strip() or None
    payload["task_name"] = "billing.settle_usage"
    return payload


@shared_task(name="billing.replay_usage_settlement")
def replay_usage_settlement_task(
    *,
    creator_bid: str = "",
    usage_bid: str = "",
) -> dict[str, Any]:
    """Replay a usage settlement without duplicating ledger consumption."""

    app = _create_task_app()
    payload = replay_bill_usage_settlement(
        app,
        creator_bid=creator_bid,
        usage_bid=usage_bid,
    )
    payload["task_name"] = "billing.replay_usage_settlement"
    return payload


@shared_task(name="billing.expire_wallet_buckets")
def expire_wallet_buckets_task(
    *,
    creator_bid: str = "",
    expire_before: Any = None,
) -> dict[str, Any]:
    """Scan expiring wallet buckets and write expire ledger entries."""

    app = _create_task_app()
    payload = expire_credit_wallet_buckets(
        app,
        creator_bid=_normalize_bid(creator_bid),
        expire_before=_coerce_datetime(expire_before),
    )
    payload["task_name"] = "billing.expire_wallet_buckets"
    return payload


@shared_task(name="billing.reconcile_provider_reference")
def reconcile_provider_reference_task(
    *,
    payment_provider: str = "",
    provider_reference_id: str = "",
    billing_order_bid: str = "",
    creator_bid: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """Reconcile a provider reference back into billing order state."""

    app = _create_task_app()
    payload = _run_reconcile_provider_reference(
        app,
        creator_bid=creator_bid,
        payment_provider=payment_provider,
        provider_reference_id=provider_reference_id,
        billing_order_bid=billing_order_bid,
        session_id=session_id,
    )
    payload["task_name"] = "billing.reconcile_provider_reference"
    return payload


@shared_task(name="billing.send_low_balance_alert")
def send_low_balance_alert_task(
    *,
    creator_bid: str = "",
    timezone_name: str = "",
) -> dict[str, Any]:
    """Build low-balance alert candidates for one creator or a batch."""

    app = _create_task_app()
    normalized_creator_bid = _normalize_bid(creator_bid)
    with app.app_context():
        creator_bids = (
            [normalized_creator_bid]
            if normalized_creator_bid
            else _collect_low_balance_creator_bids()
        )

    creators: list[dict[str, Any]] = []
    for item_creator_bid in creator_bids:
        overview = build_billing_overview(
            app,
            item_creator_bid,
            timezone_name=_normalize_bid(timezone_name) or None,
        )
        low_balance_alerts = [
            alert
            for alert in overview.get("billing_alerts", [])
            if alert.get("code") == "low_balance"
        ]
        if not low_balance_alerts:
            continue
        creators.append(
            {
                "creator_bid": item_creator_bid,
                "wallet_available_credits": overview.get("wallet", {}).get(
                    "available_credits"
                ),
                "alerts": low_balance_alerts,
            }
        )

    return {
        "status": "alerts_found" if creators else "noop",
        "creator_count": len(creator_bids),
        "alert_count": len(creators),
        "creators": creators,
        "task_name": "billing.send_low_balance_alert",
    }


@shared_task(name="billing.run_renewal_event")
def run_renewal_event_task(
    *,
    renewal_event_bid: str = "",
    subscription_bid: str = "",
    creator_bid: str = "",
) -> dict[str, Any]:
    """Normalize and expose the renewal event payload to the worker queue."""

    app = _create_task_app()
    with app.app_context():
        event = _load_target_renewal_event(
            renewal_event_bid=renewal_event_bid,
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
        )
        if event is None:
            return {
                "status": "event_not_found",
                "renewal_event_bid": _normalize_bid(renewal_event_bid) or None,
                "subscription_bid": _normalize_bid(subscription_bid) or None,
                "creator_bid": _normalize_bid(creator_bid) or None,
                "task_name": "billing.run_renewal_event",
            }
        snapshot = _serialize_renewal_event_snapshot(event)

    return {
        "status": "pending_implementation",
        **snapshot,
        "task_name": "billing.run_renewal_event",
    }


@shared_task(name="billing.retry_failed_renewal")
def retry_failed_renewal_task(
    *,
    renewal_event_bid: str = "",
    billing_order_bid: str = "",
    provider_reference_id: str = "",
    payment_provider: str = "",
    creator_bid: str = "",
) -> dict[str, Any]:
    """Retry a failed renewal using the same provider reference contract."""

    app = _create_task_app()
    if _normalize_bid(billing_order_bid) or _normalize_bid(provider_reference_id):
        payload = _run_reconcile_provider_reference(
            app,
            creator_bid=creator_bid,
            payment_provider=payment_provider,
            provider_reference_id=provider_reference_id,
            billing_order_bid=billing_order_bid,
            session_id=provider_reference_id,
        )
        payload["renewal_event_bid"] = _normalize_bid(renewal_event_bid) or None
        payload["task_name"] = "billing.retry_failed_renewal"
        return payload

    return {
        "status": "pending_implementation",
        "renewal_event_bid": _normalize_bid(renewal_event_bid) or None,
        "billing_order_bid": _normalize_bid(billing_order_bid) or None,
        "provider_reference_id": _normalize_bid(provider_reference_id) or None,
        "payment_provider": _normalize_bid(payment_provider) or None,
        "creator_bid": _normalize_bid(creator_bid) or None,
        "task_name": "billing.retry_failed_renewal",
    }
