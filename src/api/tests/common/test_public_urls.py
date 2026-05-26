from __future__ import annotations

import pytest
from flask import Flask

import flaskr.common.config as common_config
from flaskr.common.public_urls import (
    build_alipay_notify_url,
    build_google_oauth_callback_url,
    build_stripe_billing_result_url,
    build_stripe_learner_result_url,
    build_wechatpay_notify_url,
)


def _reset_config_cache(*keys: str) -> None:
    for key in keys:
        common_config.__ENHANCED_CONFIG__._cache.pop(key, None)  # noqa: SLF001


@pytest.fixture(autouse=True)
def clear_public_url_config_cache():
    keys = (
        "HOST_URL",
        "PATH_PREFIX",
        "WECHATPAY_APP_ID",
        "WECHATPAY_MCH_ID",
    )
    _reset_config_cache(*keys)
    yield
    _reset_config_cache(*keys)


def test_public_urls_are_derived_from_host_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOST_URL", "https://app.example.com/")
    monkeypatch.setenv("PATH_PREFIX", "/api")
    _reset_config_cache("HOST_URL", "PATH_PREFIX")

    assert (
        build_google_oauth_callback_url()
        == "https://app.example.com/login/google-callback"
    )
    assert (
        build_alipay_notify_url()
        == "https://app.example.com/api/callback/alipay-notify"
    )
    assert (
        build_wechatpay_notify_url()
        == "https://app.example.com/api/callback/wechatpay-notify"
    )
    assert (
        build_stripe_learner_result_url()
        == "https://app.example.com/payment/stripe/result"
    )
    assert (
        build_stripe_billing_result_url(canceled=True)
        == "https://app.example.com/payment/stripe/billing-result?canceled=1"
    )


def test_public_urls_use_path_prefix_for_backend_callbacks(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("HOST_URL", "https://app.example.com")
    monkeypatch.setenv("PATH_PREFIX", "/service-api")
    _reset_config_cache("HOST_URL", "PATH_PREFIX")

    assert (
        build_alipay_notify_url()
        == "https://app.example.com/service-api/callback/alipay-notify"
    )
    assert (
        build_wechatpay_notify_url()
        == "https://app.example.com/service-api/callback/wechatpay-notify"
    )


def test_public_urls_fall_back_to_forwarded_request_origin(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("HOST_URL", raising=False)
    monkeypatch.setenv("PATH_PREFIX", "/api")
    _reset_config_cache("HOST_URL", "PATH_PREFIX")

    app = Flask(__name__)
    with app.test_request_context(
        "/api/orders",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "forwarded.example.com",
        },
    ):
        assert (
            build_google_oauth_callback_url()
            == "https://forwarded.example.com/login/google-callback"
        )
        assert (
            build_alipay_notify_url()
            == "https://forwarded.example.com/api/callback/alipay-notify"
        )
        assert (
            build_wechatpay_notify_url()
            == "https://forwarded.example.com/api/callback/wechatpay-notify"
        )
        assert (
            build_stripe_learner_result_url()
            == "https://forwarded.example.com/payment/stripe/result"
        )
        assert (
            build_stripe_billing_result_url(canceled=True)
            == "https://forwarded.example.com/payment/stripe/billing-result"
            "?canceled=1"
        )


def test_public_urls_prefer_origin_header_when_host_url_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("HOST_URL", raising=False)
    _reset_config_cache("HOST_URL")

    app = Flask(__name__)
    with app.test_request_context(
        "/api/runtime-config",
        headers={
            "Origin": "https://frontend.example.com",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "forwarded.example.com",
        },
    ):
        assert (
            build_stripe_learner_result_url()
            == "https://frontend.example.com/payment/stripe/result"
        )


def test_public_urls_reject_host_url_with_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOST_URL", "https://app.example.com/base")
    _reset_config_cache("HOST_URL")

    with pytest.raises(RuntimeError, match="without path"):
        build_google_oauth_callback_url()
