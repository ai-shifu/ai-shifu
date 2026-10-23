"""Handle payment channel resolution for legacy orders."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.service.common.models import raise_error
from flaskr.service.config import get_config
from flaskr.service.order.payment_providers import (
    payment_definition,
    registered_payment_providers,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


def resolve_payment_channel(
    *,
    payment_channel_hint: str | None,
    channel_hint: str | None,
    stored_channel: str | None,
    default_pingxx_channel: str | None = None,
    additional_enabled_providers: Iterable[str] | None = None,
) -> tuple[str, str]:
    """Resolve the payment provider and provider-specific channel from config."""
    requested_payment_channel = (payment_channel_hint or "").strip().lower()
    requested_channel = (channel_hint or "").strip()
    requested_channel_lower = requested_channel.lower()
    default_channel = (default_pingxx_channel or "").strip()

    supported_providers = set(registered_payment_providers())
    enabled_providers = enabled_payment_providers(additional_enabled_providers)

    provider_from_channel = ""
    if ":" in requested_channel_lower:
        prefix, _ = requested_channel_lower.split(":", 1)
        prefix = prefix.strip().lower()
        if prefix in supported_providers:
            provider_from_channel = prefix
    elif requested_channel_lower in supported_providers:
        provider_from_channel = requested_channel_lower
    elif requested_channel:
        provider_from_channel = _provider_for_channel(
            requested_channel_lower,
            enabled_providers,
        )

    target_provider = requested_payment_channel or provider_from_channel

    if not target_provider:
        stored = (stored_channel or "").strip().lower()
        if stored in supported_providers and stored in enabled_providers:
            target_provider = stored
        elif default_channel:
            default_provider = _provider_for_channel(
                default_channel.lower(),
                enabled_providers,
            )
            if default_provider in enabled_providers:
                target_provider = default_provider
        if not target_provider:
            if not enabled_providers:
                raise_error("server.pay.payChannelNotSupport")
            if len(enabled_providers) == 1:
                target_provider = next(iter(enabled_providers))
            elif "stripe" in enabled_providers:
                target_provider = "stripe"
            elif "alipay" in enabled_providers:
                target_provider = "alipay"
            elif "wechatpay" in enabled_providers:
                target_provider = "wechatpay"
            elif "pingxx" in enabled_providers:
                target_provider = "pingxx"
            else:
                target_provider = min(enabled_providers)

    if target_provider not in supported_providers:
        raise_error("server.pay.payChannelNotSupport")
    if target_provider not in enabled_providers:
        raise_error("server.pay.payChannelNotSupport")

    definition = payment_definition(target_provider)
    hint = requested_channel
    if hint.lower() == target_provider and not definition.accepts_custom_channels:
        hint = ""
    provider_channel = definition.normalize_channel(hint, default_channel)
    if provider_channel is None:
        raise_error("server.pay.payChannelNotSupport")
    return target_provider, provider_channel


def resolve_market_payment_provider(
    *, additional_enabled_providers: Iterable[str] | None = None
) -> str:
    """Return the market provider used to attribute orders that need no charge."""
    provider, _ = resolve_payment_channel(
        payment_channel_hint=None,
        channel_hint=None,
        stored_channel=None,
        default_pingxx_channel="alipay_qr",
        additional_enabled_providers=additional_enabled_providers,
    )
    return provider


def _provider_for_channel(channel: str, enabled_providers: set[str]) -> str:
    if channel == "alipay_qr":
        return "alipay" if "alipay" in enabled_providers else "pingxx"
    if channel in {"wx_pub_qr", "wx_pub"}:
        return "wechatpay" if "wechatpay" in enabled_providers else "pingxx"
    if channel == "wx_wap":
        return "pingxx"
    for provider in registered_payment_providers():
        if provider in enabled_providers and any(
            route.channel == channel for route in payment_definition(provider).routes
        ):
            return provider
    return "pingxx"


def _strip_provider_prefix(channel: str) -> str:
    if ":" not in channel:
        return channel
    _, provider_channel = channel.split(":", 1)
    return provider_channel.strip().lower()


def enabled_payment_providers(
    additional_enabled_providers: Iterable[str] | None = None,
) -> set[str]:
    """Share existing configured eligibility with read-only payment options."""
    enabled_raw = str(get_config("PAYMENT_CHANNELS_ENABLED", "pingxx,stripe") or "")
    enabled_providers = {
        item.strip().lower() for item in enabled_raw.split(",") if item.strip()
    } or {"pingxx", "stripe"}
    supported_providers = set(registered_payment_providers())
    enabled_providers = enabled_providers.intersection(supported_providers)
    scoped_providers = {
        item.strip().lower()
        for item in (additional_enabled_providers or [])
        if str(item or "").strip()
    }.intersection(supported_providers)

    if enabled_raw.strip().lower() == "pingxx,stripe":
        if "pingxx" in enabled_providers:
            pingxx_key = str(get_config("PINGXX_SECRET_KEY", "") or "")
            pingxx_app = str(get_config("PINGXX_APP_ID", "") or "")
            pingxx_key_path = str(get_config("PINGXX_PRIVATE_KEY_PATH", "") or "")
            if not (pingxx_key and pingxx_app and pingxx_key_path):
                enabled_providers.discard("pingxx")
        if "stripe" in enabled_providers:
            stripe_key = str(get_config("STRIPE_SECRET_KEY", "") or "")
            if not stripe_key:
                enabled_providers.discard("stripe")
        if not enabled_providers:
            enabled_providers = {"pingxx", "stripe"}

    enabled_providers.update(scoped_providers)

    return enabled_providers
