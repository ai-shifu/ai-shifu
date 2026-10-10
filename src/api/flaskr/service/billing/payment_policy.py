"""Capabilities of user-initiated, platform-managed subscription payments."""

from __future__ import annotations

MANUAL_PAYMENT_PROVIDERS = frozenset({"pingxx", "alipay", "wechatpay"})


def is_manual_payment_provider(provider: str) -> bool:
    """Identify one-time payments without inferring automatic debit consent."""
    return str(provider or "").strip().lower() in MANUAL_PAYMENT_PROVIDERS


def manual_payments_are_compatible(*providers: str) -> bool:
    """Allow domestic manual payments to fund the same subscription rules."""
    return bool(providers) and all(is_manual_payment_provider(p) for p in providers)
