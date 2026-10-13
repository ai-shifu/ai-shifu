"""Build browser payment options from existing server-owned routing policy."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

from flaskr.service.config import get_config
from flaskr.util.boolean import parse_bool

from . import historical_billing_mode, payment_definition, registered_payment_providers
from .contracts import PaymentOption, PaymentRoute


def _supports_billing_route(route: PaymentRoute) -> bool:
    """Match the teacher browser's implemented action consumers."""
    return route.scene in {"qr", "hosted"} and route.action in {"qr", "redirect"}


def configured_payment_options(
    *,
    biz_domain: str,
    additional_enabled_providers: Iterable[str] | None = None,
) -> list[PaymentOption]:
    """Describe configured routes without provider calls or new routing rules."""
    from flaskr.service.order.learner_payments import supports_learner_attempt
    from flaskr.service.order.payment_channel_resolution import (
        enabled_payment_providers,
        resolve_payment_channel,
    )

    enabled = enabled_payment_providers(additional_enabled_providers)
    stripe_enabled = parse_bool(get_config("STRIPE_ENABLED", default=False))
    result = []
    for provider in registered_payment_providers():
        if provider not in enabled or (provider == "stripe" and not stripe_enabled):
            continue
        if biz_domain == "order" and not supports_learner_attempt(provider):
            continue
        definition = payment_definition(provider)
        for route in definition.routes:
            # Keep the learner's existing native-over-aggregator wallet preference.
            if biz_domain == "order" and route.method in {"wechat", "alipay"}:
                selected, _ = resolve_payment_channel(
                    payment_channel_hint=None,
                    channel_hint=route.channel,
                    stored_channel=None,
                    additional_enabled_providers=additional_enabled_providers,
                )
                if selected != provider:
                    continue
            # Teacher checkout currently offers QR or hosted Checkout only.
            if biz_domain == "billing" and not _supports_billing_route(route):
                continue
            result.append(
                PaymentOption(
                    id=f"{provider}:{route.channel}",
                    provider=provider,
                    channel=route.channel,
                    method=route.method,
                    scene=route.scene,
                    action=route.action,
                    billing_mode=definition.capabilities.billing_mode,
                    label_key=definition.label_key,
                    poll_provider=definition.capabilities.poll_provider,
                    requires_open_id=route.requires_open_id,
                    prefer_in_wechat=route.prefer_in_wechat,
                )
            )
    if biz_domain == "billing":
        priority = {
            provider: index
            for index, provider in enumerate(
                ("stripe", "alipay", "wechatpay", "pingxx")
            )
        }
        result.sort(key=lambda option: priority.get(option.provider, len(priority)))
    else:
        priority = {
            method: index
            for index, method in enumerate(("wechat", "alipay", "hosted", "card"))
        }
        result.sort(key=lambda option: priority.get(option.method, len(priority)))
    return result


def subscription_operations(
    provider: str,
    status: str,
    *,
    has_reference: bool,
    cancel_at_period_end: bool = False,
) -> dict[str, bool]:
    """Keep management of existing contracts independent from new-payment listing."""
    try:
        capabilities = payment_definition(provider).capabilities
    except ValueError:
        return {"cancel": False, "resume": False}
    manageable = status in {"active", "cancel_scheduled", "paused", "past_due"}
    local = historical_billing_mode(provider) == "platform_managed"
    return {
        "cancel": manageable
        and (local or (has_reference and capabilities.subscription_cancel)),
        "resume": (
            status in {"cancel_scheduled", "paused"}
            or (cancel_at_period_end and status in {"active", "past_due"})
        )
        and (local or (has_reference and capabilities.subscription_resume)),
    }


def resolve_payment_option_hint(
    value: object, *, biz_domain: str | None = None
) -> tuple[str, str]:
    """Validate selection metadata; callers still enforce context and eligibility."""
    from flaskr.service.common.models import raise_error

    if not isinstance(value, str) or ":" not in value:
        raise_error("server.pay.payChannelNotSupport")
    provider, channel = value.split(":", 1)
    try:
        definition = payment_definition(provider)
    except ValueError:
        raise_error("server.pay.payChannelNotSupport")
    if not any(
        route.channel == channel
        and (biz_domain != "billing" or _supports_billing_route(route))
        for route in definition.routes
    ):
        raise_error("server.pay.payChannelNotSupport")
    return provider, channel
