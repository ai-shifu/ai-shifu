"""Verify provider selection and unsupported capabilities fail predictably."""

from unittest.mock import Mock

import pytest
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.order import payment_channel_resolution as channels
from flaskr.service.order import payment_providers as providers
from flaskr.service.order.payment_providers.base import (
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentProvider,
    PaymentRequest,
)


class ChargeOnlyProvider(PaymentProvider):
    """A minimal provider intentionally implementing only charge creation."""

    channel = "test-charge-only"

    def create_payment(
        self, *, request: PaymentRequest, app: object
    ) -> PaymentCreationResult:
        del app
        return PaymentCreationResult(request.order_bid, {})


@pytest.mark.parametrize(
    ("operation", "kwargs", "capability"),
    [
        ("create_subscription", {"request": None}, "subscriptions"),
        (
            "cancel_subscription",
            {"subscription_bid": "sub", "provider_subscription_id": "provider-sub"},
            "subscription cancellation",
        ),
        (
            "resume_subscription",
            {"subscription_bid": "sub", "provider_subscription_id": "provider-sub"},
            "subscription resumption",
        ),
        ("verify_webhook", {"headers": {}, "raw_body": b"{}"}, "webhook verification"),
        ("refund_payment", {"request": None}, "refunds"),
        (
            "cancel_payment",
            {"provider_reference": "ref", "reference_type": "payment"},
            "payment cancellation",
        ),
        (
            "sync_reference",
            {"provider_reference": "ref", "reference_type": "payment"},
            "reference sync",
        ),
        (
            "expire_checkout_session",
            {"session_id": "cs-test"},
            "checkout session expiry",
        ),
    ],
)
def test_charge_only_provider_rejects_unsupported_lifecycle_operations(
    operation: str, kwargs: dict, capability: str
) -> None:
    with pytest.raises(NotImplementedError, match=f"does not support {capability}"):
        getattr(ChargeOnlyProvider(), operation)(app=object(), **kwargs)


def test_charge_only_provider_rejects_unsupported_jsapi() -> None:
    with pytest.raises(NotImplementedError, match="does not support JSAPI payments"):
        ChargeOnlyProvider().build_jsapi_params(prepay_id="prepay")


def test_provider_notification_and_sync_adapters_preserve_verification_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ChargeOnlyProvider()
    expected = PaymentNotificationResult("order", "paid", {})
    verify = Mock(return_value=expected)
    sync = Mock(return_value=expected)
    monkeypatch.setattr(provider, "verify_webhook", verify)
    monkeypatch.setattr(provider, "sync_reference", sync)
    app = object()
    assert (
        provider.handle_notification(
            payload={"headers": None, "raw_body": b"signed"}, app=app
        )
        is expected
    )
    verify.assert_called_once_with(headers={}, raw_body=b"signed", app=app)
    assert (
        provider.sync_payment_status(
            order_bid="order", provider_reference="attempt", app=app
        )
        is expected
    )
    sync.assert_called_once_with(
        provider_reference="attempt", reference_type="payment", app=app
    )


def test_provider_registry_constructs_fresh_instances_and_rejects_unknown_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(providers, "_PROVIDER_REGISTRY", {})
    providers.register_payment_provider(ChargeOnlyProvider)
    first = providers.get_payment_provider("test-charge-only")
    second = providers.get_payment_provider("test-charge-only")
    assert isinstance(first, ChargeOnlyProvider)
    assert first is not second
    with pytest.raises(ValueError, match="Unsupported payment channel: unknown"):
        providers.get_payment_provider("unknown")
    monkeypatch.setattr(ChargeOnlyProvider, "channel", "")
    with pytest.raises(ValueError, match="non-empty channel"):
        providers.register_payment_provider(ChargeOnlyProvider)
    assert set(providers._PROVIDER_REGISTRY) == {"test-charge-only"}


@pytest.mark.parametrize(
    ("enabled", "hint", "channel", "stored", "default", "expected"),
    [
        ("alipay,wechatpay", None, None, None, None, ("alipay", "alipay_qr")),
        ("wechatpay,pingxx", None, None, None, None, ("wechatpay", "wx_pub_qr")),
        (
            "stripe,alipay",
            None,
            None,
            None,
            "unsupported",
            ("stripe", "checkout_session"),
        ),
        ("stripe,alipay", None, "STRIPE", None, None, ("stripe", "checkout_session")),
        ("stripe", "stripe", "stripe:intent", None, None, ("stripe", "payment_intent")),
        ("stripe", "stripe", "unknown", None, None, ("stripe", "checkout_session")),
        ("stripe", "stripe", "stripe:", None, None, ("stripe", "checkout_session")),
        ("wechatpay", None, "wechatpay:wx_pub", None, None, ("wechatpay", "wx_pub")),
        ("pingxx", None, "wx_wap", None, None, ("pingxx", "wx_wap")),
        ("pingxx", None, "custom-channel", None, None, ("pingxx", "custom-channel")),
        ("alipay,wechatpay", None, None, "disabled", "wx_pub", ("wechatpay", "wx_pub")),
    ],
)
def test_channel_resolution_applies_enabled_fallbacks_and_explicit_subchannel_rules(
    monkeypatch: pytest.MonkeyPatch,
    enabled: str,
    hint: str | None,
    channel: str | None,
    stored: str | None,
    default: str | None,
    expected: tuple,
) -> None:
    monkeypatch.setattr(
        channels,
        "get_config",
        lambda key, fallback=None: (
            enabled if key == "PAYMENT_CHANNELS_ENABLED" else fallback
        ),
    )
    assert (
        channels.resolve_payment_channel(
            payment_channel_hint=hint,
            channel_hint=channel,
            stored_channel=stored,
            default_pingxx_channel=default,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("enabled", "hint", "channel"),
    [
        ("unknown", None, None),
        ("stripe", "unknown", None),
        ("wechatpay", "wechatpay", "alipay_qr"),
        ("alipay", "stripe", None),
    ],
)
def test_channel_resolution_never_uses_unavailable_or_incompatible_provider(
    monkeypatch: pytest.MonkeyPatch, enabled: str, hint: str | None, channel: str | None
) -> None:
    monkeypatch.setattr(
        channels,
        "get_config",
        lambda key, fallback=None: (
            enabled if key == "PAYMENT_CHANNELS_ENABLED" else fallback
        ),
    )
    with pytest.raises(AppError) as error:
        channels.resolve_payment_channel(
            payment_channel_hint=hint, channel_hint=channel, stored_channel=None
        )
    assert error.value.code == ERROR_CODE["server.pay.payChannelNotSupport"]
