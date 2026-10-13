"""Normalize provider-native payment statuses."""

from __future__ import annotations

from flaskr.service.order.payment_providers.api import (
    native_facts,
    trade_payload,
)

NATIVE_PAYMENT_STATE_PAID = "paid"
NATIVE_PAYMENT_STATE_CANCELED = "canceled"
NATIVE_PAYMENT_STATE_FAILED = "failed"


def reported_payment_currency_matches(
    *, expected_currency: object, reported_currency: object
) -> bool:
    """Reject a different reported unit while preserving currency-less legacy facts."""
    reported = str(reported_currency or "").strip().upper()
    return not reported or reported == str(expected_currency or "").strip().upper()


def extract_native_trade_payload(payload: dict[str, object]) -> dict[str, object]:
    """Read native snapshots through their adapter-owned compatibility boundary."""
    return trade_payload(payload) if isinstance(payload, dict) else {}


def extract_native_trade_status(provider: str, payload: dict[str, object]) -> str:
    """Read the original status without interpreting it in business code."""
    return native_facts(provider, payload).raw_status


def resolve_native_payment_state(
    provider: str, payload: dict[str, object]
) -> str | None:
    """Retain the existing terminal-state compatibility interface."""
    state = native_facts(provider, payload).state
    return state if state in {"paid", "failed", "canceled"} else None


def is_native_payment_payable(provider: str, payload: dict[str, object]) -> bool:
    """Confirm that a saved credential belongs to an unpaid, open trade."""
    return native_facts(provider, payload).state == "pending"


def native_snapshot_status(provider: str, payload: dict[str, object]) -> int:
    """Return native snapshot status."""
    state = resolve_native_payment_state(provider, payload)
    if state == NATIVE_PAYMENT_STATE_PAID:
        return 1
    if state == NATIVE_PAYMENT_STATE_CANCELED:
        return 3
    if state == NATIVE_PAYMENT_STATE_FAILED:
        return 4
    return 0
