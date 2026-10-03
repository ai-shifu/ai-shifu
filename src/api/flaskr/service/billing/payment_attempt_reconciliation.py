"""Provider-backed reconciliation for non-paid subscription orders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from typing import TYPE_CHECKING, Literal

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, require_transaction_owner, unit_of_work
from flaskr.service.common.models import raise_param_error
from flaskr.service.order.payment_providers.api import get_payment_provider
from flaskr.util.datetime import now_utc

from .checkout import resolve_billing_order_provider_reference_type, sync_billing_order
from .consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
)
from .models import BillingOrder
from .primitives import coerce_datetime, normalize_bid

if TYPE_CHECKING:
    from flask import Flask

ReconciliationStatus = Literal["paid", "closed", "unresolved"]
_PLAN_ORDER_TYPES = {
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
}


@dataclass(frozen=True, slots=True)
class PaymentAttemptReconciliation:
    """Outcome for one provider-bound billing order."""

    bill_order_bid: str
    provider: str
    provider_reference: str
    status: ReconciliationStatus
    reason: str = ""


@dataclass(frozen=True, slots=True)
class SubscriptionPaymentReconciliationResult:
    """Aggregate reconciliation result for one subscription."""

    subscription_bid: str
    attempts: tuple[PaymentAttemptReconciliation, ...]

    @property
    def settled(self) -> bool:
        """Return whether every attempt reached a safe terminal outcome."""
        return all(attempt.status != "unresolved" for attempt in self.attempts)


def _terminal_evidence_matches(order: BillingOrder) -> bool:
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    evidence = metadata.get("provider_payment_terminal_evidence")
    return bool(
        isinstance(evidence, dict)
        and normalize_bid(evidence.get("provider"))
        == normalize_bid(order.payment_provider)
        and normalize_bid(evidence.get("provider_reference"))
        == normalize_bid(order.provider_reference_id)
        and normalize_bid(evidence.get("status")) in {"canceled", "expired"}
    )


def _sync_after_uncertain_close(
    app: Flask,
    *,
    order: BillingOrder,
) -> PaymentAttemptReconciliation:
    try:
        result = sync_billing_order(
            app,
            order.creator_bid,
            order.bill_order_bid,
            {
                "session_id": order.provider_reference_id
                if order.payment_provider == "stripe"
                and resolve_billing_order_provider_reference_type(order)
                == "checkout_session"
                else ""
            },
        )
    except Exception:
        return PaymentAttemptReconciliation(
            order.bill_order_bid,
            order.payment_provider,
            order.provider_reference_id,
            "unresolved",
            "provider_reconciliation_failed",
        )
    return PaymentAttemptReconciliation(
        order.bill_order_bid,
        order.payment_provider,
        order.provider_reference_id,
        "paid" if result.status == "paid" else "unresolved",
        "provider_reported_payment" if result.status == "paid" else "still_payable",
    )


def _reconcile_attempt(
    app: Flask,
    *,
    order: BillingOrder,
    operation_id: str,
) -> PaymentAttemptReconciliation:
    provider = normalize_bid(order.payment_provider)
    provider_reference = normalize_bid(order.provider_reference_id)
    if int(order.status or 0) in {
        BILLING_ORDER_STATUS_PAID,
        BILLING_ORDER_STATUS_REFUNDED,
    }:
        return PaymentAttemptReconciliation(
            order.bill_order_bid, provider, provider_reference, "paid"
        )
    if _terminal_evidence_matches(order):
        return PaymentAttemptReconciliation(
            order.bill_order_bid, provider, provider_reference, "closed"
        )
    reference_type = resolve_billing_order_provider_reference_type(order)
    if provider == "manual" or not provider_reference or not reference_type:
        return PaymentAttemptReconciliation(
            order.bill_order_bid,
            provider,
            provider_reference,
            "unresolved",
            "missing_provider_reference",
        )

    cancellation_context: dict[str, object] | None = None
    if (
        provider == "stripe"
        and int(order.order_type or 0) == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
    ):
        metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
        cycle_start = coerce_datetime(metadata.get("renewal_cycle_start_at"))
        cycle_end = coerce_datetime(metadata.get("renewal_cycle_end_at"))
        if cycle_start is None or cycle_end is None:
            return PaymentAttemptReconciliation(
                order.bill_order_bid,
                provider,
                provider_reference,
                "unresolved",
                "missing_renewal_cycle",
            )
        cancellation_context = {
            "cycle_start": int(cycle_start.replace(tzinfo=UTC).timestamp()),
            "cycle_end": int(cycle_end.replace(tzinfo=UTC).timestamp()),
        }

    try:
        cancellation = get_payment_provider(provider).cancel_payment(
            provider_reference=provider_reference,
            reference_type=reference_type,
            app=app,
            context=cancellation_context,
        )
    except Exception:
        return _sync_after_uncertain_close(app, order=order)
    cancellation_status = normalize_bid(cancellation.status)
    if cancellation_status == "completed":
        return _sync_after_uncertain_close(app, order=order)
    if cancellation_status != "cancelled":
        return PaymentAttemptReconciliation(
            order.bill_order_bid,
            provider,
            provider_reference,
            "unresolved",
            "provider_attempt_still_payable",
        )

    with app_context_scope(app), unit_of_work():
        locked = (
            BillingOrder.query.filter(
                BillingOrder.deleted == 0,
                BillingOrder.bill_order_bid == order.bill_order_bid,
            )
            .populate_existing()
            .with_for_update()
            .one()
        )
        if int(locked.status or 0) in {
            BILLING_ORDER_STATUS_PAID,
            BILLING_ORDER_STATUS_REFUNDED,
        }:
            return PaymentAttemptReconciliation(
                locked.bill_order_bid, provider, provider_reference, "paid"
            )
        locked_provider = normalize_bid(locked.payment_provider)
        locked_reference = normalize_bid(locked.provider_reference_id)
        if locked_provider != provider or locked_reference != provider_reference:
            return PaymentAttemptReconciliation(
                locked.bill_order_bid,
                locked_provider,
                locked_reference,
                "unresolved",
                "provider_reference_changed",
            )
        closed_at = now_utc()
        metadata = (
            dict(locked.metadata_json) if isinstance(locked.metadata_json, dict) else {}
        )
        metadata["provider_payment_terminal_evidence"] = {
            "provider": provider,
            "provider_reference": provider_reference,
            "status": "canceled",
            "confirmed_at": closed_at.isoformat(),
            "operation_id": operation_id,
        }
        locked.metadata_json = metadata
        locked.status = BILLING_ORDER_STATUS_CANCELED
        locked.failed_at = locked.failed_at or closed_at
        locked.failure_code = "provider_payment_reconciled"
        locked.updated_at = closed_at
        db.session.add(locked)
    return PaymentAttemptReconciliation(
        order.bill_order_bid, provider, provider_reference, "closed"
    )


def reconcile_subscription_payment_attempts(
    app: Flask,
    *,
    creator_bid: str,
    subscription_bid: str,
    operation_id: str,
) -> SubscriptionPaymentReconciliationResult:
    """Close or synchronize all non-paid plan attempts for one subscription."""
    require_transaction_owner("subscription payment-attempt reconciliation", app)
    normalized_creator_bid = normalize_bid(creator_bid)
    normalized_subscription_bid = normalize_bid(subscription_bid)
    normalized_operation_id = normalize_bid(operation_id)
    if not normalized_creator_bid:
        raise_param_error("creator_bid")
    if not normalized_subscription_bid:
        raise_param_error("subscription_bid")
    if not normalized_operation_id:
        raise_param_error("operation_id")
    with app_context_scope(app), unit_of_work():
        orders = (
            BillingOrder.query.filter(
                BillingOrder.deleted == 0,
                BillingOrder.creator_bid == normalized_creator_bid,
                BillingOrder.subscription_bid == normalized_subscription_bid,
                BillingOrder.order_type.in_(_PLAN_ORDER_TYPES),
                BillingOrder.status.notin_(
                    {BILLING_ORDER_STATUS_PAID, BILLING_ORDER_STATUS_REFUNDED}
                ),
            )
            .order_by(BillingOrder.id.asc())
            .all()
        )
        order_bids = [order.bill_order_bid for order in orders]

    attempts: list[PaymentAttemptReconciliation] = []
    for order_bid in order_bids:
        with app_context_scope(app), unit_of_work():
            order = BillingOrder.query.filter_by(
                bill_order_bid=order_bid, deleted=0
            ).one()
        attempts.append(
            _reconcile_attempt(app, order=order, operation_id=normalized_operation_id)
        )
    return SubscriptionPaymentReconciliationResult(
        subscription_bid=normalized_subscription_bid,
        attempts=tuple(attempts),
    )


__all__ = [
    "PaymentAttemptReconciliation",
    "SubscriptionPaymentReconciliationResult",
    "reconcile_subscription_payment_attempts",
]
