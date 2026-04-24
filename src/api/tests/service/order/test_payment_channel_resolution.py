import json

import pytest

from flaskr.route import order as order_route
from flaskr.service.common.models import AppException
from flaskr.service.order.funs import (
    _extract_pingxx_redirect_url,
    _resolve_payment_channel,
    normalize_pingxx_return_url,
)


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

    def test_extract_pingxx_redirect_url_from_channel_key(self):
        assert (
            _extract_pingxx_redirect_url(
                "wx_wap",
                {"wx_wap": "https://pay.example.com/wx-wap-session"},
            )
            == "https://pay.example.com/wx-wap-session"
        )

    def test_extract_pingxx_redirect_url_from_alipay_wap_channel_key(self):
        assert (
            _extract_pingxx_redirect_url(
                "alipay_wap",
                {"alipay_wap": "https://pay.example.com/alipay-wap-session"},
            )
            == "https://pay.example.com/alipay-wap-session"
        )

    def test_extract_pingxx_redirect_url_from_fallback_key(self):
        assert (
            _extract_pingxx_redirect_url(
                "wx_wap",
                {"redirect_url": "https://pay.example.com/redirect"},
            )
            == "https://pay.example.com/redirect"
        )

    def test_normalize_pingxx_return_url_allows_same_origin_absolute_url(self):
        assert (
            normalize_pingxx_return_url(
                "https://cook.example.com/payment/pingxx/result?order_id=1",
                allowed_origins=["https://cook.example.com"],
            )
            == "https://cook.example.com/payment/pingxx/result?order_id=1"
        )

    def test_normalize_pingxx_return_url_builds_absolute_url_from_path(self):
        assert (
            normalize_pingxx_return_url(
                "/payment/pingxx/result?order_id=1",
                allowed_origins=["https://cook.example.com"],
            )
            == "https://cook.example.com/payment/pingxx/result?order_id=1"
        )

    def test_normalize_pingxx_return_url_rejects_cross_origin_url(self):
        assert (
            normalize_pingxx_return_url(
                "https://evil.example.com/payment/pingxx/result?order_id=1",
                allowed_origins=["https://cook.example.com"],
            )
            == ""
        )

    def test_normalize_pingxx_return_url_rejects_absolute_url_without_trusted_origin(
        self,
    ):
        assert (
            normalize_pingxx_return_url(
                "https://cook.example.com/payment/pingxx/result?order_id=1",
                allowed_origins=[],
            )
            == ""
        )

    def test_build_pingxx_allowed_origins_uses_absolute_home_url_origin_only(
        self, app, monkeypatch
    ):
        monkeypatch.setattr(
            order_route,
            "get_config",
            lambda key, default="": (
                "https://cook.example.com/c/course-1" if key == "HOME_URL" else default
            ),
        )

        with app.test_request_context(
            "/api/order/reqiure-to-pay",
            base_url="https://api.example.com/",
        ):
            assert order_route.build_pingxx_allowed_origins() == [
                "https://cook.example.com"
            ]

    def test_build_pingxx_allowed_origins_uses_server_name_when_available(
        self, app, monkeypatch
    ):
        monkeypatch.setattr(
            order_route,
            "get_config",
            lambda key, default="": "/" if key == "HOME_URL" else default,
        )
        monkeypatch.setitem(app.config, "SERVER_NAME", "cook.example.com")
        monkeypatch.setitem(app.config, "PREFERRED_URL_SCHEME", "https")

        with app.test_request_context(
            "/api/order/reqiure-to-pay",
            base_url="https://api.example.com/",
        ):
            assert order_route.build_pingxx_allowed_origins() == [
                "https://cook.example.com"
            ]

    def test_build_pingxx_allowed_origins_ignores_relative_home_url_without_server_name(
        self, app, monkeypatch
    ):
        monkeypatch.setattr(
            order_route,
            "get_config",
            lambda key, default="": "/" if key == "HOME_URL" else default,
        )
        monkeypatch.setitem(app.config, "SERVER_NAME", "")

        with app.test_request_context(
            "/api/order/reqiure-to-pay",
            base_url="https://api.example.com/",
        ):
            assert order_route.build_pingxx_allowed_origins() == []

    def test_resolve_pingxx_return_url_rejects_relative_path_without_trusted_origin(
        self, app, monkeypatch
    ):
        monkeypatch.setattr(
            order_route,
            "get_config",
            lambda key, default="": "/" if key == "HOME_URL" else default,
        )
        monkeypatch.setitem(app.config, "SERVER_NAME", "")

        with app.test_request_context(
            "/api/order/reqiure-to-pay",
            base_url="https://api.example.com/",
        ):
            assert order_route.resolve_pingxx_return_url(
                "/payment/pingxx/result?order_id=1"
            ) == ""

    def test_resolve_pingxx_return_url_rejects_absolute_url_without_trusted_origin(
        self, app, monkeypatch
    ):
        monkeypatch.setattr(
            order_route,
            "get_config",
            lambda key, default="": "/" if key == "HOME_URL" else default,
        )
        monkeypatch.setitem(app.config, "SERVER_NAME", "")

        with app.test_request_context(
            "/api/order/reqiure-to-pay",
            base_url="https://api.example.com/",
        ):
            assert (
                order_route.resolve_pingxx_return_url(
                    "https://evil.example.com/payment/pingxx/result?order_id=1"
                )
                == ""
            )

    def test_require_to_pay_rejects_invalid_cancel_url(self, app, monkeypatch):
        monkeypatch.setattr(
            order_route,
            "get_config",
            lambda key, default="": (
                "https://cook.example.com/c/course-1" if key == "HOME_URL" else default
            ),
        )
        reqiure_to_pay = app.view_functions["reqiure_to_pay"]

        with app.test_request_context(
            "/api/order/reqiure-to-pay",
            method="POST",
            json={
                "order_id": "order-1",
                "channel": "alipay_wap",
                "return_url": "/payment/pingxx/result?order_id=1",
                "cancel_url": "https://evil.example.com/c/course-1",
            },
        ):
            with pytest.raises(AppException) as exc_info:
                reqiure_to_pay()

        assert "cancel_url" in str(exc_info.value)

    def test_require_to_pay_requires_return_url_for_alipay_wap(self, app, monkeypatch):
        monkeypatch.setattr(
            order_route,
            "get_config",
            lambda key, default="": (
                "https://cook.example.com/c/course-1" if key == "HOME_URL" else default
            ),
        )
        reqiure_to_pay = app.view_functions["reqiure_to_pay"]

        with app.test_request_context(
            "/api/order/reqiure-to-pay",
            method="POST",
            json={
                "order_id": "order-1",
                "channel": "alipay_wap",
                "cancel_url": "/c/course-1",
            },
        ):
            with pytest.raises(AppException) as exc_info:
                reqiure_to_pay()

        assert "return_url" in str(exc_info.value)

    def test_require_to_pay_passes_resolved_urls_to_generate_charge(
        self, app, monkeypatch
    ):
        monkeypatch.setattr(
            order_route,
            "get_config",
            lambda key, default="": (
                "https://cook.example.com/c/course-1" if key == "HOME_URL" else default
            ),
        )
        captured = {}
        reqiure_to_pay = app.view_functions["reqiure_to_pay"]

        def fake_generate_charge(
            app,
            order_id,
            channel,
            client_ip,
            payment_channel=None,
            return_url="",
            cancel_url="",
        ):
            _ = app
            captured.update(
                {
                    "order_id": order_id,
                    "channel": channel,
                    "client_ip": client_ip,
                    "payment_channel": payment_channel,
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                }
            )
            return {
                "order_id": order_id,
                "channel": channel,
            }

        monkeypatch.setattr(order_route, "generate_charge", fake_generate_charge)

        with app.test_request_context(
            "/api/order/reqiure-to-pay",
            method="POST",
            json={
                "order_id": "order-1",
                "channel": "alipay_wap",
                "payment_channel": "pingxx",
                "return_url": "/payment/pingxx/result?order_id=1",
                "cancel_url": "/c/course-1",
            },
        ):
            request = order_route.request._get_current_object()
            request.client_ip = "127.0.0.1"
            payload = json.loads(reqiure_to_pay())

        assert payload["code"] == 0
        assert captured["order_id"] == "order-1"
        assert captured["channel"] == "alipay_wap"
        assert captured["payment_channel"] == "pingxx"
        assert (
            captured["return_url"]
            == "https://cook.example.com/payment/pingxx/result?order_id=1"
        )
        assert captured["cancel_url"] == "https://cook.example.com/c/course-1"
