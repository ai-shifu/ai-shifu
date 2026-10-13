"""Describe payment administration capabilities and isolate legacy sync policy."""

from flaskr.service.config import get_config
from flaskr.service.order.payment_providers.api import (
    payment_definition,
    registered_payment_providers,
)
from flaskr.util.boolean import parse_bool

# Legacy mixed-channel discount admission is deferred to the historical PR.
_LEGACY_DISCOUNT_PROVIDERS = frozenset({"stripe"})


def configured_provider_names(raw: object = None) -> set[str]:
    """Read deployment selection without constructing payment clients."""
    if raw is None:
        raw = get_config("PAYMENT_CHANNELS_ENABLED", "pingxx,stripe")
    return {item.strip().lower() for item in str(raw or "").split(",") if item.strip()}


def configured_discount_providers(enabled: set[str] | None = None) -> list[str]:
    """Return only registered providers that own remote discount references."""
    enabled = configured_provider_names() if enabled is None else enabled
    capable = {
        provider
        for provider in registered_payment_providers()
        if provider in enabled and payment_definition(provider).capabilities.discounts
    }
    if capable - _LEGACY_DISCOUNT_PROVIDERS and not parse_bool(
        get_config("STRIPE_ENABLED", default=False)
    ):
        capable.discard("stripe")
    return sorted(capable)


def requires_provider_discount_sync(enabled: set[str] | None = None) -> bool:
    """Require all capable providers for new configurations, preserving legacy admission."""
    enabled = configured_provider_names() if enabled is None else enabled
    capable = set(configured_discount_providers(enabled))
    if capable <= _LEGACY_DISCOUNT_PROVIDERS:
        return bool(capable) and enabled == capable
    return bool(capable)


def build_admin_payment_providers() -> dict[str, object]:
    """Expose safe declarations for operator tools, never account details or secrets."""
    enabled = configured_provider_names()
    items = []
    for provider in registered_payment_providers():
        if provider not in enabled:
            continue
        if provider == "stripe" and not parse_bool(
            get_config("STRIPE_ENABLED", default=False)
        ):
            continue
        definition = payment_definition(provider)
        items.append(
            {
                "provider": provider,
                "label_key": definition.label_key,
                "catalog": definition.capabilities.catalog,
                "discounts": definition.capabilities.discounts,
            }
        )
    return {"items": items, "discount_sync_required": requires_provider_discount_sync()}
