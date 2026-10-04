"""Provider-backed reconciliation for non-paid subscription orders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from typing import TYPE_CHECKING, Literal

from flaskr.dao import db, uow
from flaskr.dao.uow import app_context_scope, require_transaction_owner, unit_of_work
from flaskr.service.common.models import raise_param_error
from flaskr.service.order.payment_providers.api import (
    BillingProviderAttemptSnapshot,
    close_billing_provider_attempt,
    get_payment_provider,
    list_open_billing_provider_attempts,
    mark_billing_provider_attempt_paid,
)
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
from .provider_state import apply_billing_order_provider_update

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


@dataclass(frozen=True, slots=True)
class _OrderAttemptSnapshot:
    bill_order_bid: str
    creator_bid: str
    payment_provider: str
    provider_reference_id: str
    status: int
    order_type: int
    metadata_json: dict[str, object] | None


def _snapshot_order_attempt(order: BillingOrder) -> _OrderAttemptSnapshot:
    return _OrderAttemptSnapshot(
        bill_order_bid=normalize_bid(order.bill_order_bid),
        creator_bid=normalize_bid(order.creator_bid),
        payment_provider=normalize_bid(order.payment_provider),
        provider_reference_id=normalize_bid(order.provider_reference_id),
        status=int(order.status or 0),
        order_type=int(order.order_type or 0),
        metadata_json=(
            dict(order.metadata_json) if isinstance(order.metadata_json, dict) else None
        ),
    )


def _terminal_evidence_matches(order: _OrderAttemptSnapshot) -> bool:
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
    order: _OrderAttemptSnapshot,
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
    order: _OrderAttemptSnapshot,
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
        if (
            provider == "stripe"
            and order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        ):
            return _apply_paid_renewal_invoice(
                app,
                order=order,
                cancellation_payload=cancellation.raw_response,
            )
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


def _apply_paid_renewal_invoice(
    app: Flask,
    *,
    order: _OrderAttemptSnapshot,
    cancellation_payload: object,
) -> PaymentAttemptReconciliation:
    payload = cancellation_payload if isinstance(cancellation_payload, dict) else {}
    invoice = payload.get("invoice")
    if not isinstance(invoice, dict) or not bool(invoice.get("paid")):
        return PaymentAttemptReconciliation(
            order.bill_order_bid,
            order.payment_provider,
            order.provider_reference_id,
            "unresolved",
            "paid_invoice_evidence_missing",
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
        locked_provider = normalize_bid(locked.payment_provider)
        locked_reference = normalize_bid(locked.provider_reference_id)
        if (
            locked_provider != order.payment_provider
            or locked_reference != order.provider_reference_id
        ):
            return PaymentAttemptReconciliation(
                locked.bill_order_bid,
                locked_provider,
                locked_reference,
                "unresolved",
                "provider_reference_changed",
            )
        update = apply_billing_order_provider_update(
            locked,
            provider="stripe",
            event_type="invoice.paid",
            source="sync",
            payload={"invoice": invoice},
            provider_reference_id=order.provider_reference_id,
            target_status=BILLING_ORDER_STATUS_PAID,
        )
        update.stage_after_state_changes(app, locked)
        db.session.add(locked)
        uow.on_commit(lambda: update.dispatch_after_commit(app))
    return PaymentAttemptReconciliation(
        order.bill_order_bid,
        order.payment_provider,
        order.provider_reference_id,
        "paid",
        "provider_reported_payment",
    )


def _reconcile_raw_attempt(
    app: Flask,
    *,
    attempt: BillingProviderAttemptSnapshot,
) -> PaymentAttemptReconciliation:
    try:
        cancellation = get_payment_provider(attempt.provider).cancel_payment(
            provider_reference=attempt.provider_reference,
            reference_type=attempt.reference_type,
            app=app,
            context=None,
        )
    except Exception:
        return PaymentAttemptReconciliation(
            attempt.bill_order_bid,
            attempt.provider,
            attempt.provider_reference,
            "unresolved",
            "provider_reconciliation_failed",
        )
    cancellation_status = normalize_bid(cancellation.status)
    if cancellation_status == "completed":
        with app_context_scope(app), unit_of_work():
            paid_status = mark_billing_provider_attempt_paid(attempt)
        if paid_status == "changed":
            return PaymentAttemptReconciliation(
                attempt.bill_order_bid,
                attempt.provider,
                attempt.provider_reference,
                "unresolved",
                "provider_reference_changed",
            )
        return PaymentAttemptReconciliation(
            attempt.bill_order_bid,
            attempt.provider,
            attempt.provider_reference,
            "paid",
            "provider_reported_payment",
        )
    if cancellation_status != "cancelled":
        return PaymentAttemptReconciliation(
            attempt.bill_order_bid,
            attempt.provider,
            attempt.provider_reference,
            "unresolved",
            "provider_attempt_still_payable",
        )
    with app_context_scope(app), unit_of_work():
        close_status = close_billing_provider_attempt(attempt)
    if close_status == "changed":
        return PaymentAttemptReconciliation(
            attempt.bill_order_bid,
            attempt.provider,
            attempt.provider_reference,
            "unresolved",
            "provider_reference_changed",
        )
    return PaymentAttemptReconciliation(
        attempt.bill_order_bid,
        attempt.provider,
        attempt.provider_reference,
        "paid" if close_status == "paid" else "closed",
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
            )
            .order_by(BillingOrder.id.asc())
            .all()
        )
        order_snapshots = [_snapshot_order_attempt(order) for order in orders]
        order_bids = [order.bill_order_bid for order in order_snapshots]
        raw_attempts = list_open_billing_provider_attempts(order_bids)

    attempts: list[PaymentAttemptReconciliation] = []
    current_references = {
        (order.bill_order_bid, order.payment_provider, order.provider_reference_id)
        for order in order_snapshots
    }
    for order_snapshot in order_snapshots:
        if order_snapshot.status in {
            BILLING_ORDER_STATUS_PAID,
            BILLING_ORDER_STATUS_REFUNDED,
        }:
            continue
        attempts.append(
            _reconcile_attempt(
                app,
                order=order_snapshot,
                operation_id=normalized_operation_id,
            )
        )
    for raw_attempt in raw_attempts:
        if (
            raw_attempt.bill_order_bid,
            raw_attempt.provider,
            raw_attempt.provider_reference,
        ) in current_references:
            continue
        attempts.append(_reconcile_raw_attempt(app, attempt=raw_attempt))
    return SubscriptionPaymentReconciliationResult(
        subscription_bid=normalized_subscription_bid,
        attempts=tuple(attempts),
    )


__all__ = [
    "PaymentAttemptReconciliation",
    "SubscriptionPaymentReconciliationResult",
    "reconcile_subscription_payment_attempts",
]
