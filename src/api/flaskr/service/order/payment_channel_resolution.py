"""Handle payment channel resolution for legacy orders."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.service.common.models import raise_error
from flaskr.service.config import get_config

if TYPE_CHECKING:
    from collections.abc import Iterable

SUPPORTED_PAYMENT_PROVIDERS = frozenset({"stripe", "alipay", "wechatpay"})
_DEFAULT_ENABLED_PROVIDERS = "alipay,wechatpay,stripe"
# Settings that must be present for a provider to count when
# PAYMENT_CHANNELS_ENABLED is left at its default.
_PROVIDER_REQUIRED_SETTINGS = {
    "alipay": ("ALIPAY_APP_ID",),
    "wechatpay": ("WECHATPAY_MCH_ID",),
    "stripe": ("STRIPE_SECRET_KEY",),
}


def enabled_payment_provider_list() -> list[str]:
    """Return the enabled platform payment providers in configuration order.

    An explicit ``PAYMENT_CHANNELS_ENABLED`` is taken as is (unknown names are
    ignored). When it is unset, every supported provider whose credentials are
    configured is enabled, in the default order.
    """
    configured = str(get_config("PAYMENT_CHANNELS_ENABLED", "") or "").strip()
    providers: list[str] = []
    for item in (configured or _DEFAULT_ENABLED_PROVIDERS).split(","):
        provider = item.strip().lower()
        if provider in SUPPORTED_PAYMENT_PROVIDERS and provider not in providers:
            providers.append(provider)
    if configured:
        return providers
    return [
        provider
        for provider in providers
        if all(
            str(get_config(name, "") or "").strip()
            for name in _PROVIDER_REQUIRED_SETTINGS[provider]
        )
    ]


def enabled_payment_providers() -> set[str]:
    """Return the enabled platform payment providers as a set."""
    return set(enabled_payment_provider_list())


def resolve_payment_channel(
    *,
    payment_channel_hint: str | None,
    channel_hint: str | None,
    stored_channel: str | None,
    default_channel: str | None = None,
    additional_enabled_providers: Iterable[str] | None = None,
) -> tuple[str, str]:
    """Resolve the payment provider and provider-specific channel from config."""
    requested_payment_channel = (payment_channel_hint or "").strip().lower()
    requested_channel = (channel_hint or "").strip()
    requested_channel_lower = requested_channel.lower()
    default_channel = (default_channel or "").strip()

    enabled_providers = enabled_payment_providers()
    enabled_providers.update(
        {
            item.strip().lower()
            for item in (additional_enabled_providers or [])
            if str(item or "").strip()
        }.intersection(SUPPORTED_PAYMENT_PROVIDERS)
    )

    provider_from_channel = ""
    if ":" in requested_channel_lower:
        prefix, _ = requested_channel_lower.split(":", 1)
        prefix = prefix.strip().lower()
        if prefix in SUPPORTED_PAYMENT_PROVIDERS:
            provider_from_channel = prefix
    elif requested_channel_lower in SUPPORTED_PAYMENT_PROVIDERS:
        provider_from_channel = requested_channel_lower
    elif requested_channel:
        provider_from_channel = _provider_for_channel(requested_channel_lower)

    target_provider = requested_payment_channel or provider_from_channel

    if not target_provider:
        stored = (stored_channel or "").strip().lower()
        if stored in enabled_providers:
            target_provider = stored
        elif default_channel:
            default_provider = _provider_for_channel(default_channel.lower())
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
            else:
                target_provider = "wechatpay"

    if target_provider not in enabled_providers:
        raise_error("server.pay.payChannelNotSupport")

    if target_provider == "stripe":
        normalized_channel = requested_channel.lower()
        provider_channel = "checkout_session"
        if ":" in normalized_channel:
            _, provider_channel = normalized_channel.split(":", 1)
        elif normalized_channel and normalized_channel != "stripe":
            provider_channel = normalized_channel

        provider_channel = provider_channel or "checkout_session"
        if provider_channel in {"checkout", "checkout_session"}:
            provider_channel = "checkout_session"
        elif provider_channel in {"intent", "payment_intent"}:
            provider_channel = "payment_intent"
        else:
            provider_channel = "checkout_session"
        return "stripe", provider_channel

    if target_provider == "alipay":
        provider_channel = _strip_provider_prefix(requested_channel_lower)
        if provider_channel in {"", "alipay"}:
            provider_channel = "alipay_qr"
        if provider_channel != "alipay_qr":
            raise_error("server.pay.payChannelNotSupport")
        return "alipay", provider_channel

    provider_channel = _strip_provider_prefix(requested_channel_lower)
    if provider_channel in {"", "wechatpay"}:
        provider_channel = (
            default_channel
            if default_channel in {"wx_pub_qr", "wx_pub"}
            else "wx_pub_qr"
        )
    if provider_channel not in {"wx_pub_qr", "wx_pub"}:
        raise_error("server.pay.payChannelNotSupport")
    return "wechatpay", provider_channel


def resolve_market_payment_provider(
    *, additional_enabled_providers: Iterable[str] | None = None
) -> str:
    """Return the market provider used to attribute orders that need no charge.

    Returns an empty string when no payment provider is enabled, so free
    orders and order listings keep working in environments without payments.
    """
    enabled = enabled_payment_providers()
    enabled.update(
        str(item or "").strip().lower() for item in (additional_enabled_providers or [])
    )
    if not enabled.intersection(SUPPORTED_PAYMENT_PROVIDERS):
        return ""
    provider, _ = resolve_payment_channel(
        payment_channel_hint=None,
        channel_hint=None,
        stored_channel=None,
        default_channel="alipay_qr",
        additional_enabled_providers=additional_enabled_providers,
    )
    return provider


def _provider_for_channel(channel: str) -> str:
    if channel == "alipay_qr":
        return "alipay"
    if channel in {"wx_pub_qr", "wx_pub"}:
        return "wechatpay"
    return ""


def _strip_provider_prefix(channel: str) -> str:
    if ":" not in channel:
        return channel
    _, provider_channel = channel.split(":", 1)
    return provider_channel.strip().lower()
