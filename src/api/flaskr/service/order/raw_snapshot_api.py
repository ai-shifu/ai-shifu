"""Expose billing payment-attempt snapshots through a stable order boundary."""

from __future__ import annotations

from dataclasses import dataclass

from flaskr.dao import db
from sqlalchemy import or_

from .models import AlipayOrder, PingxxOrder, StripeOrder, WechatPayOrder
from .raw_snapshots import (
    billing_native_snapshot_query,
    billing_pingxx_snapshot_query,
    billing_stripe_snapshot_query,
)

_PAID_RAW_STATUSES = {1, 2}
_CLOSED_RAW_STATUS = 3


@dataclass(frozen=True, slots=True)
class BillingProviderAttemptSnapshot:
    """Immutable provider attempt retained outside the billing-order row."""

    bill_order_bid: str
    provider: str
    provider_reference: str
    reference_type: str


def list_open_billing_provider_attempts(
    bill_order_bids: list[str],
) -> tuple[BillingProviderAttemptSnapshot, ...]:
    """Return raw provider references that are not paid, refunded, or closed."""
    normalized_bids = [str(value or "").strip() for value in bill_order_bids if value]
    if not normalized_bids:
        return ()
    attempts: list[BillingProviderAttemptSnapshot] = []

    stripe_rows = billing_stripe_snapshot_query().filter(
        StripeOrder.bill_order_bid.in_(normalized_bids),
        StripeOrder.status.notin_({*_PAID_RAW_STATUSES, _CLOSED_RAW_STATUS}),
    )
    for row in stripe_rows.all():
        checkout_reference = str(row.checkout_session_id or "").strip()
        intent_reference = str(row.payment_intent_id or "").strip()
        reference = checkout_reference or intent_reference
        if reference:
            attempts.append(
                BillingProviderAttemptSnapshot(
                    bill_order_bid=str(row.bill_order_bid or ""),
                    provider="stripe",
                    provider_reference=reference,
                    reference_type=(
                        "checkout_session" if checkout_reference else "payment_intent"
                    ),
                )
            )

    pingxx_rows = billing_pingxx_snapshot_query().filter(
        PingxxOrder.bill_order_bid.in_(normalized_bids),
        PingxxOrder.status.notin_({*_PAID_RAW_STATUSES, _CLOSED_RAW_STATUS}),
    )
    for row in pingxx_rows.all():
        reference = str(row.charge_id or "").strip()
        if reference:
            attempts.append(
                BillingProviderAttemptSnapshot(
                    bill_order_bid=str(row.bill_order_bid or ""),
                    provider="pingxx",
                    provider_reference=reference,
                    reference_type="charge",
                )
            )

    native_models: tuple[tuple[str, type[AlipayOrder | WechatPayOrder]], ...] = (
        ("alipay", AlipayOrder),
        ("wechatpay", WechatPayOrder),
    )
    for provider, model in native_models:
        rows = billing_native_snapshot_query(provider).filter(
            model.bill_order_bid.in_(normalized_bids),
            model.status.notin_({*_PAID_RAW_STATUSES, _CLOSED_RAW_STATUS}),
        )
        for row in rows.all():
            reference = str(row.provider_attempt_id or "").strip()
            if reference:
                attempts.append(
                    BillingProviderAttemptSnapshot(
                        bill_order_bid=str(row.bill_order_bid or ""),
                        provider=provider,
                        provider_reference=reference,
                        reference_type="payment",
                    )
                )
    return tuple(attempts)


def close_billing_provider_attempt(
    attempt: BillingProviderAttemptSnapshot,
) -> str:
    """Lock and close one snapshot if it still identifies the same attempt."""
    model, query = _snapshot_query(attempt)
    row = query.populate_existing().with_for_update().one_or_none()
    if row is None:
        return "changed"
    current_reference = _snapshot_reference(attempt.provider, row)
    if current_reference != attempt.provider_reference:
        return "changed"
    status = int(row.status or 0)
    if status in _PAID_RAW_STATUSES:
        return "paid"
    if status == _CLOSED_RAW_STATUS:
        return "closed"
    row.status = _CLOSED_RAW_STATUS
    db.session.add(row)
    _ = model
    return "closed"


def mark_billing_provider_attempt_paid(
    attempt: BillingProviderAttemptSnapshot,
) -> str:
    """Lock and mark one snapshot paid if it still identifies the attempt."""
    _, query = _snapshot_query(attempt)
    row = query.populate_existing().with_for_update().one_or_none()
    if (
        row is None
        or _snapshot_reference(attempt.provider, row) != attempt.provider_reference
    ):
        return "changed"
    status = int(row.status or 0)
    if status == _CLOSED_RAW_STATUS:
        return "changed"
    if status not in _PAID_RAW_STATUSES:
        row.status = 1
        db.session.add(row)
    return "paid"


def _snapshot_query(
    attempt: BillingProviderAttemptSnapshot,
) -> tuple[type[object], object]:
    if attempt.provider == "stripe":
        model = StripeOrder
        query = billing_stripe_snapshot_query().filter(
            or_(
                StripeOrder.checkout_session_id == attempt.provider_reference,
                StripeOrder.payment_intent_id == attempt.provider_reference,
            )
        )
    elif attempt.provider == "pingxx":
        model = PingxxOrder
        query = billing_pingxx_snapshot_query().filter(
            PingxxOrder.charge_id == attempt.provider_reference
        )
    elif attempt.provider in {"alipay", "wechatpay"}:
        model = AlipayOrder if attempt.provider == "alipay" else WechatPayOrder
        query = billing_native_snapshot_query(attempt.provider).filter(
            model.provider_attempt_id == attempt.provider_reference
        )
    else:
        message = f"Unsupported billing snapshot provider: {attempt.provider}"
        raise ValueError(message)
    return model, query.filter(model.bill_order_bid == attempt.bill_order_bid)


def _snapshot_reference(provider: str, row: object) -> str:
    if provider == "stripe":
        return str(
            getattr(row, "checkout_session_id", "")
            or getattr(row, "payment_intent_id", "")
            or ""
        ).strip()
    if provider == "pingxx":
        return str(getattr(row, "charge_id", "") or "").strip()
    return str(getattr(row, "provider_attempt_id", "") or "").strip()


__all__ = [
    "BillingProviderAttemptSnapshot",
    "close_billing_provider_attempt",
    "list_open_billing_provider_attempts",
    "mark_billing_provider_attempt_paid",
]
