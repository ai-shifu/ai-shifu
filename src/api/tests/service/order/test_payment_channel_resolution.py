import pytest

from flaskr.service.common.models import AppException
from flaskr.service.order.funs import _resolve_payment_channel


class TestResolvePaymentChannel:
    def test_pingxx_channel_requires_sub_channel(self):
        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint=None,
            channel_hint="wx_pub_qr",
            stored_channel=None,
        )
        assert provider == "pingxx"
        assert sub_channel == "wx_pub_qr"

    def test_pingxx_channel_missing_sub_channel_raises(self):
        with pytest.raises(AppException):
            _resolve_payment_channel(
                payment_channel_hint=None,
                channel_hint="",
                stored_channel="pingxx",
            )

    def test_stripe_checkout_resolution(self):
        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint=None,
            channel_hint="stripe:checkout_session",
            stored_channel="pingxx",
        )
        assert provider == "stripe"
        assert sub_channel == "checkout_session"

    def test_stripe_hint_defaults_to_payment_intent(self):
        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint="stripe",
            channel_hint="",
            stored_channel="pingxx",
        )
        assert provider == "stripe"
        assert sub_channel == "checkout_session"

    def test_stripe_with_stored_channel_defaults(self):
        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint=None,
            channel_hint="",
            stored_channel="stripe",
        )
        assert provider == "stripe"
        assert sub_channel == "checkout_session"

    def test_stripe_only_configuration_overrides_pingxx_default(self, monkeypatch):
        def fake_get_config(key, default=None):
            if key == "PAYMENT_CHANNELS_ENABLED":
                return "stripe"
            return default

        monkeypatch.setattr(
            "flaskr.service.order.payment_channel_resolution.get_config",
            fake_get_config,
        )

        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint=None,
            channel_hint="",
            stored_channel="pingxx",
        )
        assert provider == "stripe"
        # Sub-channel is determined by Stripe defaults (implementation detail).
        assert sub_channel in {"checkout_session", "payment_intent"}

    def test_disabled_payment_channel_raises_for_explicit_request(self, monkeypatch):
        def fake_get_config(key, default=None):
            if key == "PAYMENT_CHANNELS_ENABLED":
                return "stripe"
            return default

        monkeypatch.setattr(
            "flaskr.service.order.payment_channel_resolution.get_config",
            fake_get_config,
        )

        with pytest.raises(AppException):
            _resolve_payment_channel(
                payment_channel_hint="pingxx",
                channel_hint="wx_pub_qr",
                stored_channel="pingxx",
            )

    def test_alipay_qr_prefers_native_when_enabled(self, monkeypatch):
        def fake_get_config(key, default=None):
            if key == "PAYMENT_CHANNELS_ENABLED":
                return "alipay,pingxx"
            return default

        monkeypatch.setattr(
            "flaskr.service.order.payment_channel_resolution.get_config",
            fake_get_config,
        )

        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint=None,
            channel_hint="alipay_qr",
            stored_channel=None,
        )
        assert provider == "alipay"
        assert sub_channel == "alipay_qr"

    def test_alipay_qr_falls_back_to_pingxx_when_native_disabled(self, monkeypatch):
        def fake_get_config(key, default=None):
            if key == "PAYMENT_CHANNELS_ENABLED":
                return "pingxx"
            return default

        monkeypatch.setattr(
            "flaskr.service.order.payment_channel_resolution.get_config",
            fake_get_config,
        )

        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint=None,
            channel_hint="alipay_qr",
            stored_channel=None,
        )
        assert provider == "pingxx"
        assert sub_channel == "alipay_qr"

    def test_wechat_jsapi_prefers_native_when_enabled(self, monkeypatch):
        def fake_get_config(key, default=None):
            if key == "PAYMENT_CHANNELS_ENABLED":
                return "wechatpay,pingxx"
            return default

        monkeypatch.setattr(
            "flaskr.service.order.payment_channel_resolution.get_config",
            fake_get_config,
        )

        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint=None,
            channel_hint="wx_pub",
            stored_channel=None,
        )
        assert provider == "wechatpay"
        assert sub_channel == "wx_pub"

    def test_explicit_wechatpay_defaults_to_qr_channel(self, monkeypatch):
        def fake_get_config(key, default=None):
            if key == "PAYMENT_CHANNELS_ENABLED":
                return "wechatpay"
            return default

        monkeypatch.setattr(
            "flaskr.service.order.payment_channel_resolution.get_config",
            fake_get_config,
        )

        provider, sub_channel = _resolve_payment_channel(
            payment_channel_hint="wechatpay",
            channel_hint="",
            stored_channel=None,
        )
        assert provider == "wechatpay"
        assert sub_channel == "wx_pub_qr"

    def test_explicit_native_provider_rejects_unsupported_channel(self, monkeypatch):
        def fake_get_config(key, default=None):
            if key == "PAYMENT_CHANNELS_ENABLED":
                return "alipay"
            return default

        monkeypatch.setattr(
            "flaskr.service.order.payment_channel_resolution.get_config",
            fake_get_config,
        )

        with pytest.raises(AppException):
            _resolve_payment_channel(
                payment_channel_hint="alipay",
                channel_hint="wx_pub_qr",
                stored_channel=None,
            )
