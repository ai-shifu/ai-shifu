"""Payment provider adapters."""

from .base import (
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentProvider,
    PaymentRefundRequest,
    PaymentRefundResult,
    PaymentRequest,
    SubscriptionUpdateResult,
)

_PROVIDER_REGISTRY: dict[str, type[PaymentProvider]] = {}


def register_payment_provider(provider_cls: type[PaymentProvider]) -> None:
    """Register a payment provider class keyed by its declared channel."""
    channel = provider_cls.channel
    if not channel:
        raise ValueError("Payment provider must declare a non-empty channel")
    _PROVIDER_REGISTRY[channel] = provider_cls


def get_payment_provider(channel: str) -> PaymentProvider:
    """Instantiate a provider for the requested channel."""
    try:
        provider_cls = _PROVIDER_REGISTRY[channel]
    except KeyError as exc:
        message = f"Unsupported payment channel: {channel}"
        raise ValueError(message) from exc
    return provider_cls()


__all__ = [
    "PaymentCreationResult",
    "PaymentNotificationResult",
    "PaymentProvider",
    "PaymentRefundRequest",
    "PaymentRefundResult",
    "PaymentRequest",
    "SubscriptionUpdateResult",
    "get_payment_provider",
    "register_payment_provider",
]

# Ensure built-in providers are registered on import.
from . import (  # noqa: E402
    alipay,  # noqa: F401
    pingxx,  # noqa: F401
    stripe,  # noqa: F401
    wechatpay,  # noqa: F401
)
