"""Apply verified refund evidence to the current learner purchase operation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .consts import ORDER_STATUS_REFUND

if TYPE_CHECKING:
    from .models import Order
    from .payment_providers.contracts import PaymentEvent
    from .payment_snapshots import PaymentAttempt


def reconcile_learner_refund(
    order: Order, attempt: PaymentAttempt, event: PaymentEvent, payload: dict
) -> None:
    """Join the caller's current-attempt lock and transaction; never call a gateway."""
    if event.kind != "refund" or not event.refund_status:
        return
    metadata = attempt.metadata
    operation = dict(metadata.get("refund_operation") or {})
    if not operation or operation.get("status") == "succeeded":
        return
    if metadata.get("refund_operation_history") and not event.refund_reference:
        return
    if event.refund_reference and any(
        event.refund_reference
        == (
            (old.get("response") or {}).get("provider_reference")
            or old.get("provider_reference")
        )
        for old in metadata.get("refund_operation_history") or []
    ):
        return
    previous = operation.get("response") or {}
    reference = event.refund_reference or previous.get("provider_reference") or ""
    if (
        previous.get("provider_reference")
        and reference != previous["provider_reference"]
    ):
        return
    status = event.refund_status.lower()
    if status not in {"pending", "requires_action", "succeeded", "failed", "canceled"}:
        return
    if operation.get("status") in {"failed", "canceled"} and status in {
        "pending",
        "requires_action",
    }:
        return
    if previous and "initial_response" not in operation:
        operation["initial_response"] = previous
    operation.update(
        status=status,
        provider_reference=reference,
        response={
            "provider_reference": reference,
            "raw_response": payload,
            "status": status,
        },
    )
    attempt.metadata = {
        **metadata,
        "refund_operation": operation,
        "last_refund_id": reference,
    }
    if status == "succeeded":
        attempt.status = 2
        order.status = ORDER_STATUS_REFUND
