"""Capabilities of user-initiated, platform-managed subscription payments."""

from __future__ import annotations

from flaskr.service.order.payment_providers.api import (
    historical_billing_mode,
    payment_definition,
)

# Kept for legacy imports; current predicates also accept registered extensions.
MANUAL_PAYMENT_PROVIDERS = frozenset({"pingxx", "alipay", "wechatpay"})


def supports_plan_checkout(provider: str) -> bool:
    """Only manual payments may fund plans without creating a recurring contract."""
    capabilities = payment_definition(provider).capabilities
    return (
        capabilities.billing_mode == "platform_managed"
        or capabilities.subscription_create
    )


def is_manual_payment_provider(provider: str) -> bool:
    """Identify one-time payments without inferring automatic debit consent."""
    return historical_billing_mode(provider) == "platform_managed"


def manual_payments_are_compatible(*providers: str) -> bool:
    """Allow domestic manual payments to fund the same subscription rules."""
    return bool(providers) and all(is_manual_payment_provider(p) for p in providers)


def is_provider_managed_payment_provider(provider: str) -> bool:
    """Resolve hosted billing semantics independently of current checkout admission."""
    return historical_billing_mode(provider) == "provider_managed"
