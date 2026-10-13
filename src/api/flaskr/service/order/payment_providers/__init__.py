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
from .contracts import HISTORICAL_BILLING_MODES, BillingMode, PaymentDefinition

_PROVIDER_REGISTRY: dict[str, type[PaymentProvider]] = {}


def register_payment_provider(provider_cls: type[PaymentProvider]) -> None:
    """Register a payment provider class keyed by its declared channel."""
    channel = provider_cls.channel
    if not channel:
        message = "Payment provider must declare a non-empty channel"
        raise ValueError(message)
    _PROVIDER_REGISTRY[channel] = provider_cls
    HISTORICAL_BILLING_MODES.setdefault(
        channel, provider_cls.definition.capabilities.billing_mode
    )


def registered_payment_providers() -> tuple[str, ...]:
    """Return active integrations without constructing clients or doing I/O."""
    return tuple(_PROVIDER_REGISTRY)


def payment_definition(channel: str) -> PaymentDefinition:
    """Resolve declared capabilities independently of client initialization."""
    try:
        return _PROVIDER_REGISTRY[channel].definition
    except KeyError as exc:
        message = f"Unsupported payment channel: {channel}"
        raise ValueError(message) from exc


def historical_billing_mode(channel: str) -> BillingMode | None:
    """Read historical business semantics even after an integration is disabled."""
    return HISTORICAL_BILLING_MODES.get(str(channel or "").strip().lower())


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
