from __future__ import annotations

from typing import Any

NATIVE_PAYMENT_STATE_PAID = "paid"
NATIVE_PAYMENT_STATE_CANCELED = "canceled"
NATIVE_PAYMENT_STATE_FAILED = "failed"


def extract_native_trade_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    trade = payload.get("trade", {})
    if isinstance(trade, dict) and trade:
        return trade
    resource = payload.get("resource", {})
    if isinstance(resource, dict) and resource:
        return resource
    return payload


def extract_native_trade_status(provider: str, payload: dict[str, Any]) -> str:
    trade_payload = extract_native_trade_payload(payload)
    if provider == "alipay":
        return str(trade_payload.get("trade_status") or "")
    if provider == "wechatpay":
        return str(trade_payload.get("trade_state") or "")
    return ""


def resolve_native_payment_state(
    provider: str,
    payload: dict[str, Any],
) -> str | None:
    raw_status = extract_native_trade_status(provider, payload).upper()
    if provider == "alipay":
        if raw_status in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
            return NATIVE_PAYMENT_STATE_PAID
        if raw_status == "TRADE_CLOSED":
            return NATIVE_PAYMENT_STATE_CANCELED
        return None
    if provider == "wechatpay":
        if raw_status == "SUCCESS":
            return NATIVE_PAYMENT_STATE_PAID
        if raw_status in {"CLOSED", "REVOKED"}:
            return NATIVE_PAYMENT_STATE_CANCELED
        if raw_status == "PAYERROR":
            return NATIVE_PAYMENT_STATE_FAILED
        return None
    return None


def native_snapshot_status(provider: str, payload: dict[str, Any]) -> int:
    state = resolve_native_payment_state(provider, payload)
    if state == NATIVE_PAYMENT_STATE_PAID:
        return 1
    if state == NATIVE_PAYMENT_STATE_CANCELED:
        return 3
    if state == NATIVE_PAYMENT_STATE_FAILED:
        return 4
    return 0
