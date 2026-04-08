"""Task entrypoints for billing background jobs."""

from __future__ import annotations

from datetime import datetime
import os
from typing import Any, Callable

from .funcs import (
    build_billing_overview,
    reconcile_billing_provider_reference,
)
from .daily_aggregates import (
    aggregate_daily_ledger_summary,
    aggregate_daily_usage_metrics,
)
from .models import BillingSubscription, CreditWallet
from .renewal import retry_billing_renewal_event, run_billing_renewal_event
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


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", ""}:
        return False
    raise ValueError(f"Unsupported bool value: {value!r}")


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

    return reconcile_billing_provider_reference(
        app,
        creator_bid=normalized_creator_bid,
        payment_provider=normalized_payment_provider,
        provider_reference_id=normalized_provider_reference_id,
        billing_order_bid=normalized_billing_order_bid,
        session_id=normalized_session_id,
    )


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
    payload = run_billing_renewal_event(
        app,
        renewal_event_bid=renewal_event_bid,
        subscription_bid=subscription_bid,
        creator_bid=creator_bid,
    )
    payload["task_name"] = "billing.run_renewal_event"
    return payload


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

    payload = retry_billing_renewal_event(
        app,
        renewal_event_bid=renewal_event_bid,
        subscription_bid="",
        creator_bid=creator_bid,
        billing_order_bid=billing_order_bid,
        provider_reference_id=provider_reference_id,
        payment_provider=payment_provider,
    )
    payload["task_name"] = "billing.retry_failed_renewal"
    return payload


@shared_task(name="billing.aggregate_daily_usage_metrics")
def aggregate_daily_usage_metrics_task(
    *,
    stat_date: str = "",
    creator_bid: str = "",
    finalize: Any = False,
) -> dict[str, Any]:
    """Rebuild one creator/day usage aggregate slice from usage + ledger rows."""

    app = _create_task_app()
    payload = aggregate_daily_usage_metrics(
        app,
        stat_date=_normalize_bid(stat_date),
        creator_bid=_normalize_bid(creator_bid),
        finalize=_coerce_bool(finalize),
    )
    payload["task_name"] = "billing.aggregate_daily_usage_metrics"
    return payload


@shared_task(name="billing.aggregate_daily_ledger_summary")
def aggregate_daily_ledger_summary_task(
    *,
    stat_date: str = "",
    creator_bid: str = "",
    finalize: Any = False,
) -> dict[str, Any]:
    """Rebuild one creator/day ledger summary slice from ledger entries."""

    app = _create_task_app()
    payload = aggregate_daily_ledger_summary(
        app,
        stat_date=_normalize_bid(stat_date),
        creator_bid=_normalize_bid(creator_bid),
        finalize=_coerce_bool(finalize),
    )
    payload["task_name"] = "billing.aggregate_daily_ledger_summary"
    return payload
