"""Verify payment channel resolution behavior."""

from __future__ import annotations

import pytest
from flaskr.service.common.models import AppError
from flaskr.service.common.payment_channels import (
    enabled_payment_provider_list,
    resolve_market_payment_provider,
)
from flaskr.service.order.funs import _resolve_payment_channel


def _configure(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    monkeypatch.setattr(
        "flaskr.service.common.payment_channels.get_config",
        lambda key, default="": values.get(key, default),
    )


class TestEnabledProviders:
    """Verify which providers configuration enables."""

    def test_explicit_list_keeps_order_and_ignores_retired_names(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="wechatpay, pingxx,alipay")

        assert enabled_payment_provider_list() == ["wechatpay", "alipay"]

    def test_unset_list_enables_providers_with_complete_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(
            monkeypatch,
            ALIPAY_APP_ID="alipay-app",
            ALIPAY_APP_PRIVATE_KEY_PATH="/keys/alipay-private.pem",
            ALIPAY_PUBLIC_KEY="alipay-public",
            WECHAT_APP_ID="wx-app",
            WECHATPAY_MCH_ID="mch",
            WECHATPAY_MERCHANT_SERIAL_NO="serial",
            WECHATPAY_API_V3_KEY="v3",
            WECHATPAY_PRIVATE_KEY="private",
            WECHATPAY_PUBLIC_KEY_PATH="/keys/wechatpay-public.pem",
            WECHATPAY_PUBLIC_KEY_ID="PUB_KEY_ID_0123",
            STRIPE_SECRET_KEY="sk",
        )

        assert enabled_payment_provider_list() == ["alipay", "wechatpay", "stripe"]

    @pytest.mark.parametrize(
        "settings",
        [
            {"ALIPAY_APP_ID": "alipay-app"},
            {"ALIPAY_APP_ID": "alipay-app", "ALIPAY_APP_PRIVATE_KEY": "private"},
            {"WECHATPAY_MCH_ID": "mch"},
            {
                "WECHATPAY_APP_ID": "wx-app",
                "WECHATPAY_MCH_ID": "mch",
                "WECHATPAY_MERCHANT_SERIAL_NO": "serial",
                "WECHATPAY_API_V3_KEY": "v3",
                "WECHATPAY_PRIVATE_KEY": "private",
            },
            # A WeChat Pay public key cannot verify notifications without its ID.
            {
                "WECHATPAY_APP_ID": "wx-app",
                "WECHATPAY_MCH_ID": "mch",
                "WECHATPAY_MERCHANT_SERIAL_NO": "serial",
                "WECHATPAY_API_V3_KEY": "v3",
                "WECHATPAY_PRIVATE_KEY": "private",
                "WECHATPAY_PUBLIC_KEY": "public",
            },
        ],
    )
    def test_unset_list_skips_providers_with_partial_credentials(
        self, monkeypatch: pytest.MonkeyPatch, settings: dict[str, str]
    ) -> None:
        _configure(monkeypatch, **settings)

        assert enabled_payment_provider_list() == []

    def test_undecryptable_credential_leaves_the_provider_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def get_config(key: str, default: str = "") -> str:
            if key == "ALIPAY_APP_PRIVATE_KEY":
                message = "cannot decrypt stored credential"
                raise ValueError(message)
            return {"ALIPAY_APP_ID": "app", "STRIPE_SECRET_KEY": "sk"}.get(key, default)

        monkeypatch.setattr(
            "flaskr.service.common.payment_channels.get_config", get_config
        )

        assert enabled_payment_provider_list() == ["stripe"]

    def test_unset_list_without_credentials_enables_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch)

        assert enabled_payment_provider_list() == []
        assert resolve_market_payment_provider() == ""


class TestResolvePaymentChannel:
    """Verify resolve payment channel behavior."""

    def test_retired_pingxx_is_not_selectable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="pingxx")

        with pytest.raises(AppError):
            _resolve_payment_channel(
                payment_channel_hint="pingxx",
                channel_hint="alipay_qr",
                stored_channel=None,
            )
        with pytest.raises(AppError):
            _resolve_payment_channel(
                payment_channel_hint=None,
                channel_hint="alipay_qr",
                stored_channel="pingxx",
            )

    def test_stored_retired_provider_falls_back_to_enabled_native(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="alipay,wechatpay")

        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint=None,
            channel_hint="wx_pub_qr",
            stored_channel="pingxx",
        )
        assert provider == "wechatpay"
        assert sub_channel == "wx_pub_qr"

    @pytest.mark.parametrize("enabled", ["alipay,wechatpay", "alipay,wechatpay,stripe"])
    def test_unknown_channel_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, enabled: str
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED=enabled)

        with pytest.raises(AppError):
            _resolve_payment_channel(
                payment_channel_hint=None,
                channel_hint="wx_wap",
                stored_channel=None,
            )

    @pytest.mark.parametrize(
        ("channel", "expected"),
        [("checkout_session", "checkout_session"), ("intent", "payment_intent")],
    )
    def test_bare_stripe_channel_resolves_to_stripe(
        self, monkeypatch: pytest.MonkeyPatch, channel: str, expected: str
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="alipay,stripe")

        assert _resolve_payment_channel(
            payment_channel_hint=None, channel_hint=channel, stored_channel=None
        ) == ("stripe", expected)

    def test_stripe_checkout_resolution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="stripe")

        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint=None,
            channel_hint="stripe:checkout_session",
            stored_channel=None,
        )
        assert provider == "stripe"
        assert sub_channel == "checkout_session"

    def test_stripe_hint_defaults_to_checkout_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="stripe")

        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint="stripe",
            channel_hint="",
            stored_channel=None,
        )
        assert provider == "stripe"
        assert sub_channel == "checkout_session"

    def test_stripe_with_stored_channel_defaults(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="alipay,stripe")

        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint=None,
            channel_hint="",
            stored_channel="stripe",
        )
        assert provider == "stripe"
        assert sub_channel == "checkout_session"

    def test_disabled_payment_channel_raises_for_explicit_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="stripe")

        with pytest.raises(AppError):
            _resolve_payment_channel(
                payment_channel_hint="alipay",
                channel_hint="alipay_qr",
                stored_channel=None,
            )

    def test_alipay_qr_uses_native_alipay(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="alipay,wechatpay")

        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint=None,
            channel_hint="alipay_qr",
            stored_channel=None,
        )
        assert provider == "alipay"
        assert sub_channel == "alipay_qr"

    def test_alipay_qr_is_rejected_when_alipay_is_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="wechatpay")

        with pytest.raises(AppError):
            _resolve_payment_channel(
                payment_channel_hint=None,
                channel_hint="alipay_qr",
                stored_channel=None,
            )

    def test_wechat_jsapi_uses_native_wechatpay(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="wechatpay")

        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint=None,
            channel_hint="wx_pub",
            stored_channel=None,
        )
        assert provider == "wechatpay"
        assert sub_channel == "wx_pub"

    def test_explicit_wechatpay_defaults_to_qr_channel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="wechatpay")

        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint="wechatpay",
            channel_hint="",
            stored_channel=None,
        )
        assert provider == "wechatpay"
        assert sub_channel == "wx_pub_qr"

    def test_scoped_provider_allows_custom_wechat_when_platform_disables_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="stripe")

        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint="wechatpay",
            channel_hint="wx_pub_qr",
            stored_channel=None,
            additional_enabled_providers={"wechatpay"},
        )
        assert provider == "wechatpay"
        assert sub_channel == "wx_pub_qr"

    def test_explicit_native_provider_rejects_unsupported_channel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="alipay")

        with pytest.raises(AppError):
            _resolve_payment_channel(
                payment_channel_hint="alipay",
                channel_hint="wx_pub_qr",
                stored_channel=None,
            )

    def test_market_provider_prefers_alipay_for_free_orders(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, PAYMENT_CHANNELS_ENABLED="wechatpay,alipay")

        assert resolve_market_payment_provider() == "alipay"

    def test_market_provider_accepts_a_single_use_scoped_provider_iterable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch)

        assert (
            resolve_market_payment_provider(
                additional_enabled_providers=iter(["wechatpay"])
            )
            == "wechatpay"
        )
