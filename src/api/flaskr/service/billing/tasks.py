"""Task entrypoints for billing background jobs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from flaskr.service.config import get_config

from .checkout import reconcile_billing_provider_reference
from .consts import (
    BILL_CONFIG_KEY_RENEWAL_TASK_CONFIG,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
)
from .daily_aggregates import (
    aggregate_daily_ledger_summary,
    aggregate_daily_usage_metrics,
    rebuild_daily_aggregates,
)
from .domains import verify_domain_binding
from .models import BillingRenewalEvent, BillingSubscription, CreditWallet
from .notifications import (
    TASK_NAME as _SUBSCRIPTION_PURCHASE_SMS_TASK_NAME,
    deliver_subscription_purchase_sms as _deliver_subscription_purchase_sms,
)
from .primitives import coerce_bool as _coerce_bool
from .primitives import coerce_datetime as _coerce_datetime
from .primitives import normalize_bid as _normalize_bid
from .read_models import build_billing_overview
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


class SubscriptionPurchaseSmsRetryableError(RuntimeError):
    """Raised when the SMS worker should use Celery autoretry."""


def _create_task_app():
    os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")
    from app import create_app

    return create_app()


@dataclass(slots=True, frozen=True)
class LowBalanceAlertCandidate:
    creator_bid: str
    wallet_available_credits: Any
    alerts: list[Any]

    def to_task_payload(self) -> dict[str, Any]:
        serialized_alerts: list[Any] = []
        for alert in self.alerts:
            if hasattr(alert, "__json__"):
                serialized_alerts.append(alert.__json__())
            elif isinstance(alert, dict):
                serialized_alerts.append(dict(alert))
            else:
                serialized_alerts.append(alert)
        return {
            "creator_bid": self.creator_bid,
            "wallet_available_credits": self.wallet_available_credits,
            "alerts": serialized_alerts,
        }


@dataclass(slots=True, frozen=True)
class LowBalanceAlertTaskResult:
    status: str
    creator_count: int
    alert_count: int
    creators: list[LowBalanceAlertCandidate]
    task_name: str = "billing.send_low_balance_alert"

    def to_task_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "creator_count": self.creator_count,
            "alert_count": self.alert_count,
            "creators": [creator.to_task_payload() for creator in self.creators],
            "task_name": self.task_name,
        }


def _serialize_task_payload(result: Any) -> Any:
    if isinstance(result, dict):
        return dict(result)
    if hasattr(result, "to_task_payload"):
        return result.to_task_payload()
    if hasattr(result, "to_payload"):
        return result.to_payload()
    if hasattr(result, "__json__"):
        return result.__json__()
    raise TypeError(f"Unsupported task payload type: {type(result)!r}")


def _load_renewal_task_config() -> dict[str, Any]:
    defaults = {
        "enabled": 0,
        "batch_size": 100,
        "lookahead_minutes": 60,
        "queue": "billing-renewal",
    }
    raw_config = get_config(BILL_CONFIG_KEY_RENEWAL_TASK_CONFIG, "") or ""
    try:
        parsed = json.loads(str(raw_config))
    except (TypeError, ValueError):
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    return {**defaults, **parsed}


def _coerce_positive_int(
    value: Any,
    default: int,
    *,
    minimum: int = 0,
) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, normalized)


def dispatch_due_renewal_events(
    app,
) -> dict[str, Any]:
    """Find due renewal events and enqueue the existing runner task."""

    with app.app_context():
        config = _load_renewal_task_config()
        if not _coerce_bool(config.get("enabled")):
            return {
                "status": "noop_disabled",
                "candidate_count": 0,
                "enqueued_count": 0,
                "renewal_event_bids": [],
            }

        batch_size = _coerce_positive_int(config.get("batch_size"), 100, minimum=1)
        lookahead_minutes = _coerce_positive_int(
            config.get("lookahead_minutes"),
            60,
            minimum=0,
        )
        cutoff = datetime.now() + timedelta(minutes=lookahead_minutes)
        events = (
            BillingRenewalEvent.query.filter(
                BillingRenewalEvent.deleted == 0,
                BillingRenewalEvent.status == BILLING_RENEWAL_EVENT_STATUS_PENDING,
                BillingRenewalEvent.scheduled_at <= cutoff,
            )
            .order_by(
                BillingRenewalEvent.scheduled_at.asc(),
                BillingRenewalEvent.id.asc(),
            )
            .limit(batch_size)
            .all()
        )

        renewal_event_bids: list[str] = []
        for event in events:
            run_renewal_event_task.apply_async(
                kwargs={
                    "renewal_event_bid": event.renewal_event_bid,
                    "subscription_bid": event.subscription_bid,
                    "creator_bid": event.creator_bid,
                }
            )
            renewal_event_bids.append(event.renewal_event_bid)

        return {
            "status": "enqueued" if renewal_event_bids else "noop",
            "candidate_count": len(events),
            "enqueued_count": len(renewal_event_bids),
            "renewal_event_bids": renewal_event_bids,
        }


def _run_reconcile_provider_reference(
    app,
    *,
    creator_bid: str = "",
    payment_provider: str = "",
    provider_reference_id: str = "",
    bill_order_bid: str = "",
    session_id: str = "",
):
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_payment_provider = _normalize_bid(payment_provider)
    normalized_provider_reference_id = _normalize_bid(provider_reference_id)
    normalized_bill_order_bid = _normalize_bid(bill_order_bid)
    normalized_session_id = _normalize_bid(session_id)

    return reconcile_billing_provider_reference(
        app,
        creator_bid=normalized_creator_bid,
        payment_provider=normalized_payment_provider,
        provider_reference_id=normalized_provider_reference_id,
        bill_order_bid=normalized_bill_order_bid,
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
    payload = _serialize_task_payload(settle_bill_usage(app, usage_bid=usage_bid))
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
    payload = _serialize_task_payload(payload)
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
    payload = _serialize_task_payload(payload)
    payload["task_name"] = "billing.expire_wallet_buckets"
    return payload


@shared_task(name="billing.reconcile_provider_reference")
def reconcile_provider_reference_task(
    *,
    payment_provider: str = "",
    provider_reference_id: str = "",
    bill_order_bid: str = "",
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
        bill_order_bid=bill_order_bid,
        session_id=session_id,
    )
    payload = _serialize_task_payload(payload)
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

    creators: list[LowBalanceAlertCandidate] = []
    for item_creator_bid in creator_bids:
        overview = build_billing_overview(
            app,
            item_creator_bid,
            timezone_name=_normalize_bid(timezone_name) or None,
        )
        if isinstance(overview, dict):
            low_balance_alerts = [
                alert
                for alert in overview.get("billing_alerts", [])
                if alert.get("code") == "low_balance"
            ]
            wallet_available_credits = overview.get("wallet", {}).get(
                "available_credits"
            )
            alerts = low_balance_alerts
        else:
            low_balance_alerts = [
                alert
                for alert in overview.billing_alerts
                if alert.code == "low_balance"
            ]
            wallet_available_credits = overview.wallet.available_credits
            alerts = low_balance_alerts
        if not low_balance_alerts:
            continue
        creators.append(
            LowBalanceAlertCandidate(
                creator_bid=item_creator_bid,
                wallet_available_credits=wallet_available_credits,
                alerts=list(alerts),
            )
        )

    result = LowBalanceAlertTaskResult(
        status="alerts_found" if creators else "noop",
        creator_count=len(creator_bids),
        alert_count=len(creators),
        creators=creators,
    )
    return result.to_task_payload()


@shared_task(
    name="billing.send_subscription_purchase_sms",
    autoretry_for=(SubscriptionPurchaseSmsRetryableError,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
)
def send_subscription_purchase_sms_task(
    *,
    bill_order_bid: str = "",
) -> dict[str, Any]:
    """Deliver one pending subscription purchase SMS notification."""

    app = _create_task_app()
    payload = _deliver_subscription_purchase_sms(
        app,
        bill_order_bid=_normalize_bid(bill_order_bid),
    )
    payload = _serialize_task_payload(payload)
    payload["task_name"] = _SUBSCRIPTION_PURCHASE_SMS_TASK_NAME
    if payload.get("status") == "failed_provider":
        raise SubscriptionPurchaseSmsRetryableError(
            json.dumps(
                payload,
                sort_keys=True,
                default=str,
            )
        )
    return payload


@shared_task(name="billing.dispatch_due_renewal_events")
def dispatch_due_renewal_events_task() -> dict[str, Any]:
    """Enqueue due renewal events onto the default worker queue."""

    app = _create_task_app()
    payload = dispatch_due_renewal_events(app)
    payload = _serialize_task_payload(payload)
    payload["task_name"] = "billing.dispatch_due_renewal_events"
    return payload


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
    payload = _serialize_task_payload(payload)
    payload["task_name"] = "billing.run_renewal_event"
    return payload


@shared_task(name="billing.retry_failed_renewal")
def retry_failed_renewal_task(
    *,
    renewal_event_bid: str = "",
    bill_order_bid: str = "",
    provider_reference_id: str = "",
    payment_provider: str = "",
    creator_bid: str = "",
) -> dict[str, Any]:
    """Retry a failed renewal using the same provider reference contract."""

    app = _create_task_app()
    if _normalize_bid(bill_order_bid) or _normalize_bid(provider_reference_id):
        payload = _run_reconcile_provider_reference(
            app,
            creator_bid=creator_bid,
            payment_provider=payment_provider,
            provider_reference_id=provider_reference_id,
            bill_order_bid=bill_order_bid,
            session_id=provider_reference_id,
        )
        payload = _serialize_task_payload(payload)
        payload["renewal_event_bid"] = _normalize_bid(renewal_event_bid) or None
        payload["task_name"] = "billing.retry_failed_renewal"
        return payload

    payload = retry_billing_renewal_event(
        app,
        renewal_event_bid=renewal_event_bid,
        subscription_bid="",
        creator_bid=creator_bid,
        bill_order_bid=bill_order_bid,
        provider_reference_id=provider_reference_id,
        payment_provider=payment_provider,
    )
    payload = _serialize_task_payload(payload)
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
    payload = _serialize_task_payload(payload)
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
    payload = _serialize_task_payload(payload)
    payload["task_name"] = "billing.aggregate_daily_ledger_summary"
    return payload


@shared_task(name="billing.rebuild_daily_aggregates")
def rebuild_daily_aggregates_task(
    *,
    creator_bid: str = "",
    shifu_bid: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict[str, Any]:
    """Rebuild one date window of usage/ledger daily aggregates."""

    app = _create_task_app()
    payload = rebuild_daily_aggregates(
        app,
        creator_bid=_normalize_bid(creator_bid),
        shifu_bid=_normalize_bid(shifu_bid),
        date_from=_normalize_bid(date_from),
        date_to=_normalize_bid(date_to),
    )
    payload = _serialize_task_payload(payload)
    payload["task_name"] = "billing.rebuild_daily_aggregates"
    return payload


@shared_task(name="billing.verify_domain_binding")
def verify_domain_binding_task(
    *,
    creator_bid: str = "",
    domain_binding_bid: str = "",
    host: str = "",
    verification_token: str = "",
) -> dict[str, Any]:
    """Refresh one custom domain binding using the existing verify flow."""

    app = _create_task_app()
    payload = verify_domain_binding(
        app,
        creator_bid=_normalize_bid(creator_bid),
        domain_binding_bid=_normalize_bid(domain_binding_bid),
        host=_normalize_bid(host),
        verification_token=_normalize_bid(verification_token),
    )
    payload = _serialize_task_payload(payload)
    payload["task_name"] = "billing.verify_domain_binding"
    return payload
