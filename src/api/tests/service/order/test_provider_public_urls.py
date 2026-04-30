from __future__ import annotations

import json

from flask import Flask
import pytest

import flaskr.common.config as common_config
from flaskr.service.order.payment_providers.alipay import AlipayProvider
from flaskr.service.order.payment_providers.base import PaymentRequest
from flaskr.service.order.payment_providers.wechatpay import WechatPayProvider


def _reset_config_cache(*keys: str) -> None:
    for key in keys:
        common_config.__ENHANCED_CONFIG__._cache.pop(key, None)  # noqa: SLF001


@pytest.fixture(autouse=True)
def clear_provider_public_url_config_cache():
    keys = (
        "HOST_URL",
        "PATH_PREFIX",
        "WECHATPAY_APP_ID",
        "WECHATPAY_MCH_ID",
    )
    _reset_config_cache(*keys)
    yield
    _reset_config_cache(*keys)


def test_alipay_precreate_uses_host_url_notify_url(monkeypatch):
    monkeypatch.setenv("HOST_URL", "https://pay.example.com")
    monkeypatch.setenv("PATH_PREFIX", "/api")
    _reset_config_cache("HOST_URL", "PATH_PREFIX")

    captured: dict[str, str] = {}

    class FakeBizModel:
        pass

    class FakePrecreateRequest:
        def __init__(self, *, biz_model):
            self.biz_model = biz_model

    class FakeClient:
        def execute(self, precreate_request):
            captured["notify_url"] = precreate_request.notify_url
            return {
                "alipay_trade_precreate_response": {
                    "code": "10000",
                    "qr_code": "https://alipay.test/qr",
                }
            }

    provider = AlipayProvider()
    monkeypatch.setattr(provider, "_ensure_client", lambda _app: FakeClient())
    monkeypatch.setattr(
        provider,
        "_load_sdk",
        lambda _app: {
            "AlipayTradePrecreateModel": FakeBizModel,
            "AlipayTradePrecreateRequest": FakePrecreateRequest,
        },
    )

    result = provider.create_payment(
        request=PaymentRequest(
            order_bid="alipay-order-1",
            user_bid="user-1",
            shifu_bid="course-1",
            amount=100,
            channel="alipay_qr",
            currency="CNY",
            subject="Course",
            body="Course",
            client_ip="127.0.0.1",
            extra={"notify_url": "https://wrong.example.com/notify"},
        ),
        app=Flask(__name__),
    )

    assert captured["notify_url"] == (
        "https://pay.example.com/api/callback/alipay-notify"
    )
    assert result.extra["raw_request"]["notify_url"] == captured["notify_url"]


def test_wechatpay_native_uses_host_url_notify_url(monkeypatch):
    monkeypatch.setenv("HOST_URL", "https://pay.example.com")
    monkeypatch.setenv("PATH_PREFIX", "/api")
    monkeypatch.setenv("WECHATPAY_APP_ID", "wx-app-1")
    monkeypatch.setenv("WECHATPAY_MCH_ID", "mch-1")
    _reset_config_cache(
        "HOST_URL",
        "PATH_PREFIX",
        "WECHATPAY_APP_ID",
        "WECHATPAY_MCH_ID",
    )

    captured: dict[str, str] = {}

    provider = WechatPayProvider()

    def fake_request(*, method, path, body, app):
        del method, path, app
        captured.update(json.loads(body))
        return {"code_url": "https://wechatpay.test/qr"}

    monkeypatch.setattr(provider, "_request", fake_request)

    result = provider.create_payment(
        request=PaymentRequest(
            order_bid="wechat-order-1",
            user_bid="user-1",
            shifu_bid="course-1",
            amount=100,
            channel="wx_pub_qr",
            currency="CNY",
            subject="Course",
            body="Course",
            client_ip="127.0.0.1",
            extra={"notify_url": "https://wrong.example.com/notify"},
        ),
        app=Flask(__name__),
    )

    assert captured["notify_url"] == (
        "https://pay.example.com/api/callback/wechatpay-notify"
    )
    assert result.extra["raw_request"]["notify_url"] == captured["notify_url"]
