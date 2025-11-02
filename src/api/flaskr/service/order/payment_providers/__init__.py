from .base import (
    PaymentProvider,
    PaymentRequest,
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentRefundRequest,
    PaymentRefundResult,
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
        raise ValueError(f"Unsupported payment channel: {channel}") from exc
    return provider_cls()


__all__ = [
    "PaymentProvider",
    "PaymentRequest",
    "PaymentCreationResult",
    "PaymentNotificationResult",
    "PaymentRefundRequest",
    "PaymentRefundResult",
    "register_payment_provider",
    "get_payment_provider",
]
