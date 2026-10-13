"""Describe payment capabilities, client actions and provider-reported facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Literal

PaymentState = Literal["pending", "paid", "failed", "canceled", "refunded", "unknown"]
BillingMode = Literal["platform_managed", "provider_managed"]
ActionType = Literal["qr", "redirect", "jsapi", "sdk_confirm", "none"]


@dataclass(frozen=True, slots=True)
class PaymentAction:
    """An explicit client operation; completing it does not prove payment."""

    type: ActionType
    url: str | None = None
    parameters: dict[str, str] = field(default_factory=dict)
    sdk: str | None = None
    client_secret: str | None = None
    publishable_key: str | None = None
    session_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize only the browser-facing action contract."""
        return asdict(self)


def stored_payment_action(value: object) -> PaymentAction | None:
    """Recover known action fields while tolerating malformed or newer snapshots."""
    if not isinstance(value, dict):
        return None
    known = {item.name for item in fields(PaymentAction)}
    values = {key: item for key, item in value.items() if key in known}
    action_type = values.get("type")
    if not isinstance(action_type, str) or action_type not in {
        "qr",
        "redirect",
        "jsapi",
        "sdk_confirm",
        "none",
    }:
        return None
    if values.get("url") is not None and not isinstance(values["url"], str):
        return None
    if values["type"] in {"qr", "redirect"} and not values.get("url"):
        return None
    return PaymentAction(**values)


@dataclass(frozen=True, slots=True)
class PaymentFacts:
    """Reported payment evidence, kept separate from local business state."""

    state: PaymentState = "unknown"
    order_amount: int | None = None
    payer_amount: int | None = None
    provider_reference: str | None = None
    currency: str | None = None
    raw_status: str = ""
    validation_amount_source: Literal["order", "payer"] = "order"
    invalid_validation_amount: bool = False
    event_type: str = ""
    event_id: str | None = None
    event_time: int | None = None
    source: Literal["notification", "query"] = "notification"


@dataclass(frozen=True, slots=True)
class SubscriptionFacts:
    """Contract state and period evidence, independent from a single payment."""

    provider_reference: str
    status: str
    customer_reference: str = ""
    period_start: int | None = None
    period_end: int | None = None
    billing_anchor: int | None = None
    cancel_at_period_end: bool = False

    def to_state_dict(self) -> dict[str, object]:
        """Provide the existing lifecycle sink with normalized contract fields."""
        return {
            "id": self.provider_reference,
            "customer": self.customer_reference,
            "status": self.status,
            "current_period_start": self.period_start,
            "current_period_end": self.period_end,
            "billing_cycle_anchor": self.billing_anchor,
            "cancel_at_period_end": self.cancel_at_period_end,
        }


@dataclass(frozen=True, slots=True)
class PaymentRoute:
    """A provider's existing payment method and client scene."""

    channel: str
    method: str
    action: ActionType
    scene: str
    requires_open_id: bool = False
    prefer_in_wechat: bool = False


@dataclass(frozen=True, slots=True)
class PaymentCapabilities:
    """Protocol capabilities; configuration and business policy still gate use."""

    billing_mode: BillingMode = "platform_managed"
    query: bool = False
    close: bool = False
    refund: bool = False
    subscription_create: bool = False
    subscription_cancel: bool = False
    subscription_resume: bool = False
    catalog: bool = False
    discounts: bool = False
    poll_provider: bool = False


@dataclass(frozen=True, slots=True)
class PaymentDefinition:
    """Concentrate routing and presentation metadata for one integration."""

    capabilities: PaymentCapabilities = field(default_factory=PaymentCapabilities)
    routes: tuple[PaymentRoute, ...] = ()
    default_channel: str = ""
    label_key: str = ""
    channel_aliases: tuple[tuple[str, str], ...] = ()
    unknown_channel_uses_default: bool = False
    accepts_custom_channels: bool = False
    snapshot_kind: str = "native"
    subject_limit: int = 64
    body_limit: int = 128

    def normalize_channel(self, channel: str, default: str = "") -> str | None:
        """Preserve each integration's current subchannel compatibility."""
        if self.accepts_custom_channels:
            return channel or default or None
        value = channel.split(":", 1)[-1].strip().lower()
        if not value:
            supported = {route.channel for route in self.routes}
            value = default if default in supported else self.default_channel
        value = dict(self.channel_aliases).get(value, value)
        if value in {route.channel for route in self.routes}:
            return value
        return self.default_channel if self.unknown_channel_uses_default else None


BUILTIN_DEFINITIONS = {
    "pingxx": PaymentDefinition(
        snapshot_kind="pingxx",
        capabilities=PaymentCapabilities(query=True, close=True),
        routes=(
            PaymentRoute("wx_pub_qr", "wechat", "qr", "qr"),
            PaymentRoute("alipay_qr", "alipay", "qr", "qr"),
            PaymentRoute("wx_pub", "wechat", "jsapi", "wechat", requires_open_id=True),
            PaymentRoute("wx_wap", "wechat", "redirect", "mobile_browser"),
        ),
        label_key="module.billing.catalog.labels.providerPingxx",
        accepts_custom_channels=True,
    ),
    "stripe": PaymentDefinition(
        snapshot_kind="stripe",
        capabilities=PaymentCapabilities(
            billing_mode="provider_managed",
            query=True,
            close=True,
            refund=True,
            subscription_create=True,
            subscription_cancel=True,
            subscription_resume=True,
            catalog=True,
            discounts=True,
        ),
        routes=(
            PaymentRoute("checkout_session", "hosted", "redirect", "hosted"),
            PaymentRoute("payment_intent", "card", "sdk_confirm", "embedded"),
        ),
        default_channel="checkout_session",
        label_key="module.billing.catalog.labels.providerStripe",
        channel_aliases=(
            ("checkout", "checkout_session"),
            ("intent", "payment_intent"),
        ),
        unknown_channel_uses_default=True,
    ),
    "alipay": PaymentDefinition(
        capabilities=PaymentCapabilities(query=True, close=True, poll_provider=True),
        routes=(PaymentRoute("alipay_qr", "alipay", "qr", "qr"),),
        default_channel="alipay_qr",
        label_key="module.billing.catalog.labels.providerAlipay",
    ),
    "wechatpay": PaymentDefinition(
        subject_limit=127,
        body_limit=127,
        capabilities=PaymentCapabilities(query=True, close=True, poll_provider=True),
        routes=(
            PaymentRoute("wx_pub_qr", "wechat", "qr", "qr"),
            PaymentRoute(
                "wx_pub",
                "wechat",
                "jsapi",
                "wechat",
                requires_open_id=True,
                prefer_in_wechat=True,
            ),
        ),
        default_channel="wx_pub_qr",
        label_key="module.billing.catalog.labels.providerWechatpay",
    ),
}

# Historical mode resolution is independent of active provider registration.
HISTORICAL_BILLING_MODES: dict[str, BillingMode] = {
    name: definition.capabilities.billing_mode
    for name, definition in BUILTIN_DEFINITIONS.items()
}


@dataclass(frozen=True, slots=True)
class PaymentOption:
    """A configured route in the current business context, not a permission grant."""

    id: str
    provider: str
    channel: str
    method: str
    scene: str
    action: ActionType
    billing_mode: BillingMode
    label_key: str
    poll_provider: bool = False
    requires_open_id: bool = False
    prefer_in_wechat: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize public selection metadata without merchant credentials."""
        return asdict(self)
