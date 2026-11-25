"""Normalize provider-native payment statuses."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

NATIVE_PAYMENT_STATE_PAID = "paid"
NATIVE_PAYMENT_STATE_CANCELED = "canceled"
NATIVE_PAYMENT_STATE_FAILED = "failed"


def extract_native_trade_payload(payload: dict[str, object]) -> dict[str, object]:
    """Extract native trade payload."""
    if not isinstance(payload, dict):
        return {}
    trade = payload.get("trade", {})
    if isinstance(trade, dict) and trade:
        return trade
    resource = payload.get("resource", {})
    if isinstance(resource, dict) and resource:
        return resource
    return payload


_CHINA_TZ = dt.timezone(dt.timedelta(hours=8))


def extract_native_paid_at(
    provider: str, payload: dict[str, object]
) -> dt.datetime | None:
    """Return when the provider says the trade was paid, as an aware datetime.

    WeChat Pay reports ``success_time`` in RFC 3339. Alipay reports
    ``gmt_payment`` (notifications) or ``send_pay_date`` (trade query) as
    ``YYYY-MM-DD HH:MM:SS`` in China time. Returns None when absent or invalid.
    """
    trade_payload = extract_native_trade_payload(payload)
    try:
        if provider == "wechatpay":
            value = str(trade_payload.get("success_time") or "").strip()
            return dt.datetime.fromisoformat(value) if value else None
        if provider == "alipay":
            value = str(
                trade_payload.get("gmt_payment")
                or trade_payload.get("send_pay_date")
                or ""
            ).strip()
            if not value:
                return None
            return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=_CHINA_TZ
            )
    except ValueError:
        return None
    return None


def extract_native_paid_amount(provider: str, payload: dict[str, object]) -> int | None:
    """Return the paid amount in minor units, or None when the payload has none.

    Alipay reports ``total_amount`` in yuan. WeChat Pay reports ``amount`` in fen;
    ``total`` is the order amount and ``payer_total`` excludes WeChat-funded
    coupons, so ``total`` is what must match the merchant order.
    """
    trade_payload = extract_native_trade_payload(payload)
    if provider == "alipay":
        value = trade_payload.get("total_amount")
        if value in (None, ""):
            return None
        return int((Decimal(str(value)) * 100).to_integral_value())
    if provider == "wechatpay":
        amount = trade_payload.get("amount", {})
        if not isinstance(amount, dict):
            return None
        value = amount.get("total", amount.get("payer_total"))
        if value in (None, ""):
            return None
        return int(value)
    return None


def extract_native_trade_status(provider: str, payload: dict[str, object]) -> str:
    """Extract native trade status."""
    trade_payload = extract_native_trade_payload(payload)
    if provider == "alipay":
        return str(trade_payload.get("trade_status") or "")
    if provider == "wechatpay":
        return str(trade_payload.get("trade_state") or "")
    return ""


def resolve_native_payment_state(
    provider: str,
    payload: dict[str, object],
) -> str | None:
    """Resolve native payment state."""
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


def is_native_payment_payable(provider: str, payload: dict[str, object]) -> bool:
    """Confirm that a saved credential belongs to an unpaid, open trade."""
    raw_status = extract_native_trade_status(provider, payload).upper()
    if provider == "alipay":
        return raw_status == "WAIT_BUYER_PAY"
    if provider == "wechatpay":
        return raw_status == "NOTPAY"
    return False


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
