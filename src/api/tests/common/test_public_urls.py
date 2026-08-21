from __future__ import annotations

import flaskr.common.config as common_config
import pytest
from flask import Flask
from flaskr.common.public_urls import (
    build_alipay_notify_url,
    build_google_oauth_callback_url,
    build_stripe_billing_result_url,
    build_stripe_learner_result_url,
    build_wechatpay_notify_url,
    resolve_request_origin,
)


def _reset_config_cache(*keys: str) -> None:
    for key in keys:
        common_config.__ENHANCED_CONFIG__._cache.pop(key, None)


@pytest.fixture(autouse=True)
def clear_public_url_config_cache():
    keys = (
        "HOST_URL",
        "PATH_PREFIX",
        "WECHATPAY_APP_ID",
        "WECHATPAY_MCH_ID",
        "GOOGLE_OAUTH_REDIRECT_URI",
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


def test_public_urls_include_non_standard_port_from_forwarded_port(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("HOST_URL", raising=False)
    monkeypatch.setenv("PATH_PREFIX", "/api")
    _reset_config_cache("HOST_URL", "PATH_PREFIX")

    app = Flask(__name__)
    with app.test_request_context(
        "/api/orders",
        headers={
            "X-Forwarded-Proto": "http",
            "X-Forwarded-Host": "app.example.com",
            "X-Forwarded-Port": "8080",
        },
    ):
        assert (
            build_google_oauth_callback_url()
            == "http://app.example.com:8080/login/google-callback"
        )


def test_public_urls_omit_standard_port_from_forwarded_port(
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
            "X-Forwarded-Host": "app.example.com",
            "X-Forwarded-Port": "443",
        },
    ):
        assert (
            build_google_oauth_callback_url()
            == "https://app.example.com/login/google-callback"
        )


def test_google_callback_can_be_pinned_to_one_shared_url(
    monkeypatch: pytest.MonkeyPatch,
):
    """One callback for every domain, so Google needs no per-domain entry."""
    monkeypatch.setenv("HOST_URL", "https://app.example.com")
    monkeypatch.setenv(
        "GOOGLE_OAUTH_REDIRECT_URI", "https://app.example.com/login/google-callback"
    )
    _reset_config_cache("HOST_URL", "GOOGLE_OAUTH_REDIRECT_URI")

    assert (
        build_google_oauth_callback_url()
        == "https://app.example.com/login/google-callback"
    )


def test_pinned_google_callback_wins_over_the_request_origin(
    monkeypatch: pytest.MonkeyPatch,
):
    """A white-label domain must still send Google the shared callback."""
    monkeypatch.delenv("HOST_URL", raising=False)
    monkeypatch.setenv(
        "GOOGLE_OAUTH_REDIRECT_URI", "https://app.example.com/login/google-callback"
    )
    _reset_config_cache("HOST_URL", "GOOGLE_OAUTH_REDIRECT_URI")

    app = Flask(__name__)
    with app.test_request_context(
        "/", headers={"Origin": "https://learn.customer.example"}
    ):
        assert (
            build_google_oauth_callback_url()
            == "https://app.example.com/login/google-callback"
        )


def test_google_callback_falls_back_to_the_request_origin_when_unpinned(
    monkeypatch: pytest.MonkeyPatch,
):
    """Without the setting the historical per-origin behavior is kept."""
    monkeypatch.delenv("HOST_URL", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_REDIRECT_URI", raising=False)
    _reset_config_cache("HOST_URL", "GOOGLE_OAUTH_REDIRECT_URI")

    app = Flask(__name__)
    with app.test_request_context(
        "/", headers={"Origin": "https://learn.customer.example"}
    ):
        assert (
            build_google_oauth_callback_url()
            == "https://learn.customer.example/login/google-callback"
        )


def test_malformed_pinned_google_callback_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("HOST_URL", "https://app.example.com")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "app.example.com/callback")
    _reset_config_cache("HOST_URL", "GOOGLE_OAUTH_REDIRECT_URI")

    with pytest.raises(RuntimeError):
        build_google_oauth_callback_url()


class TestResolveRequestOrigin:
    """The OAuth return origin comes from here, so it must not be caller-driven."""

    def test_a_query_parameter_cannot_nominate_another_domain(self):
        # The attack this guards: starting a login on one domain while naming
        # another customer's verified domain as where to hand the code back.
        app = Flask(__name__)
        with app.test_request_context(
            "/api/user/oauth/google?origin=https://other-customer.example",
            headers={"Origin": "https://learn.customer.example"},
        ):
            assert resolve_request_origin() == "https://learn.customer.example"

    def test_falls_back_to_the_forwarded_host(self):
        # Same-origin calls send no Origin header; the ingress sets these.
        app = Flask(__name__)
        with app.test_request_context(
            "/api/user/oauth/google?origin=https://other-customer.example",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "learn.customer.example",
            },
        ):
            assert resolve_request_origin() == "https://learn.customer.example"
