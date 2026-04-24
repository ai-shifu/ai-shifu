from __future__ import annotations

from typing import Optional, Tuple

from flaskr.service.common.models import raise_error
from flaskr.service.config import get_config


def resolve_payment_channel(
    *,
    payment_channel_hint: Optional[str],
    channel_hint: Optional[str],
    stored_channel: Optional[str],
    default_pingxx_channel: Optional[str] = None,
) -> Tuple[str, str]:
    """Resolve the payment provider and provider-specific channel from config."""

    requested_payment_channel = (payment_channel_hint or "").strip().lower()
    requested_channel = (channel_hint or "").strip()

    enabled_raw = str(get_config("PAYMENT_CHANNELS_ENABLED", "pingxx,stripe") or "")
    enabled_providers = {
        item.strip().lower() for item in enabled_raw.split(",") if item.strip()
    } or {"pingxx", "stripe"}

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

    provider_from_channel = ""
    if ":" in requested_channel:
        prefix, _ = requested_channel.split(":", 1)
        prefix = prefix.strip().lower()
        if prefix in {"stripe", "pingxx"}:
            provider_from_channel = prefix
    elif requested_channel.lower() in {"stripe", "pingxx"}:
        provider_from_channel = requested_channel.lower()
    elif requested_channel:
        provider_from_channel = "pingxx"

    target_provider = requested_payment_channel or provider_from_channel

    if not target_provider:
        stored = (stored_channel or "").strip().lower()
        if stored in {"pingxx", "stripe"} and stored in enabled_providers:
            target_provider = stored
        else:
            if not enabled_providers:
                raise_error("server.pay.payChannelNotSupport")
            if len(enabled_providers) == 1:
                target_provider = next(iter(enabled_providers))
            elif "stripe" in enabled_providers:
                target_provider = "stripe"
            elif "pingxx" in enabled_providers:
                target_provider = "pingxx"
            else:
                raise_error("server.pay.payChannelNotSupport")

    if target_provider not in {"pingxx", "stripe"}:
        raise_error("server.pay.payChannelNotSupport")
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

    provider_channel = requested_channel or (default_pingxx_channel or "")
    if not provider_channel:
        raise_error("server.pay.payChannelNotSupport")
    return "pingxx", provider_channel
