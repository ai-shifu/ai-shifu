"""Channel-independent purchase settlement rules shared by protocol consumers."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from .consts import ORDER_STATUS_REPRICING, ORDER_STATUS_TO_BE_PAID

if TYPE_CHECKING:
    from .payment_providers.contracts import PaymentEvent


def saved_refund_controls_state(event: PaymentEvent, metadata: object) -> bool:
    """Require saved refunds to admit evidence before ordinary payment projection."""
    return (
        (event.kind == "refund" or event.payment.state == "refunded")
        and isinstance(metadata, dict)
        and bool(
            metadata.get("refund_operation") or metadata.get("refund_operation_history")
        )
    )


def purchase_attempt_matches(
    *,
    price: object,
    attempt_amount: int,
    attempt_id: int,
    latest_id: int | None,
) -> bool:
    """Require the latest attempt and the amount authorized by the current order."""
    expected = Decimal(price or 0)
    return attempt_id == latest_id and (
        expected <= 0 or attempt_amount == int(expected * 100)
    )


def purchase_attempt_can_complete(
    *,
    order_status: int,
    attempt_status: int,
    current_attempt: bool,
    eligible_attempt_statuses: tuple[int, ...] = (0,),
) -> bool:
    """Allow fulfillment only for a pending purchase and an eligible current attempt."""
    return (
        current_attempt
        and attempt_status in eligible_attempt_statuses
        and order_status in {ORDER_STATUS_TO_BE_PAID, ORDER_STATUS_REPRICING}
    )
