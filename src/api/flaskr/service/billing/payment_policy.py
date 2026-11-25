"""Capabilities of user-initiated, platform-managed subscription payments."""

from __future__ import annotations

# Ping++ no longer takes payments (native Alipay/WeChat Pay replaced it on
# 2026-11-25), but subscriptions and orders recorded with it remain. Keeping it
# in the manual group lets those subscriptions renew and upgrade with the
# native providers.
LEGACY_PINGXX_PROVIDER = "pingxx"
MANUAL_PAYMENT_PROVIDERS = frozenset({LEGACY_PINGXX_PROVIDER, "alipay", "wechatpay"})


def is_manual_payment_provider(provider: str) -> bool:
    """Identify one-time payments without inferring automatic debit consent."""
    return str(provider or "").strip().lower() in MANUAL_PAYMENT_PROVIDERS


def manual_payments_are_compatible(*providers: str) -> bool:
    """Allow domestic manual payments to fund the same subscription rules."""
    return bool(providers) and all(is_manual_payment_provider(p) for p in providers)


def is_legacy_pingxx_provider(provider: str) -> bool:
    """Identify orders recorded with the retired Ping++ provider."""
    return str(provider or "").strip().lower() == LEGACY_PINGXX_PROVIDER
