from __future__ import annotations

from datetime import datetime, timedelta

from flask import Flask
import pytest

import flaskr.dao as dao
import flaskr.common.public_urls as public_urls
from flaskr.route import config as config_route
from flaskr.service.billing.consts import (
    BILLING_DOMAIN_BINDING_STATUS_VERIFIED,
    BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT,
    CREDIT_SOURCE_TYPE_MANUAL,
)
from flaskr.service.billing.dtos import RuntimeBillingContextDTO, RuntimeConfigDTO
from flaskr.service.billing.models import BillingDomainBinding, BillingEntitlement
from flaskr.service.billing.runtime_config import (
    build_default_runtime_billing_context,
    build_runtime_billing_context,
)


@pytest.fixture
def runtime_config_client(monkeypatch):
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )

    dao.db.init_app(app)
    config_values = {
        "DEFAULT_COURSE_ID": "global-course-1",
        "DEFAULT_LLM_MODEL": "gpt-5.4",
        "WECHAT_APP_ID": "wechat-app-1",
        "BILL_ENABLED": True,
        "BILL_CREDIT_PRECISION": 4,
        "STRIPE_PUBLISHABLE_KEY": "pk_test_global",
        "STRIPE_ENABLED": True,
        "PAYMENT_CHANNELS_ENABLED": "pingxx,stripe",
        "PAY_ORDER_EXPIRE_TIME": 600,
        "UI_ALWAYS_SHOW_LESSON_TREE": False,
        "LOGO_WIDE_URL": "https://cdn.example.com/global-wide.png",
        "LOGO_SQUARE_URL": "https://cdn.example.com/global-square.png",
        "FAVICON_URL": "https://cdn.example.com/global-favicon.ico",
        "ANALYTICS_UMAMI_SCRIPT": "",
        "ANALYTICS_UMAMI_SITE_ID": "",
        "DEBUG_ERUDA_ENABLED": False,
        "LOGIN_METHODS_ENABLED": "phone",
        "DEFAULT_LOGIN_METHOD": "phone",
        "HOME_URL": "/",
        "HOST_URL": "https://app.example.com",
        "CURRENCY_SYMBOL": "¥",
        "LEGAL_AGREEMENT_URL_ZH_CN": "/legal/agreement/zh",
        "LEGAL_AGREEMENT_URL_EN_US": "/legal/agreement/en",
        "LEGAL_PRIVACY_URL_ZH_CN": "/legal/privacy/zh",
        "LEGAL_PRIVACY_URL_EN_US": "/legal/privacy/en",
        "GEN_MDF_API_URL": "",
    }

    monkeypatch.setattr(
        config_route,
        "get_config",
        lambda key, default="": config_values.get(key, default),
    )
    monkeypatch.setattr(
        public_urls,
        "get_config",
        lambda key, default="": config_values.get(key, default),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.primitives.get_config",
        lambda key, default="": config_values.get(key, default),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.primitives.get_common_config",
        lambda key, default=None: config_values.get(key, default),
    )
    monkeypatch.setattr(
        "flaskr.common.shifu_context._get_shifu_creator_bid_cached",
        lambda app, shifu_bid: "creator-1" if shifu_bid == "shifu-1" else None,
    )

    config_route.register_config_handler(app, "/api")

    now = datetime(2026, 4, 8, 12, 0, 0)
    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(
            [
                BillingEntitlement(
                    entitlement_bid="runtime-ent-1",
                    creator_bid="creator-1",
                    source_type=CREDIT_SOURCE_TYPE_MANUAL,
                    source_bid="manual-1",
                    branding_enabled=1,
                    custom_domain_enabled=1,
                    priority_class=7702,
                    analytics_tier=7712,
                    support_tier=7722,
                    feature_payload={
                        "branding": {
                            "logo_wide_url": "https://cdn.example.com/creator-wide.png",
                            "logo_square_url": "https://cdn.example.com/creator-square.png",
                            "favicon_url": "https://cdn.example.com/creator-favicon.ico",
                            "home_url": "https://creator.example.com/home",
                        }
                    },
                    effective_from=now - timedelta(days=2),
                    effective_to=None,
                ),
                BillingEntitlement(
                    entitlement_bid="runtime-ent-2",
                    creator_bid="creator-2",
                    source_type=CREDIT_SOURCE_TYPE_MANUAL,
                    source_bid="manual-2",
                    branding_enabled=0,
                    custom_domain_enabled=0,
                    priority_class=7701,
                    analytics_tier=7711,
                    support_tier=7721,
                    effective_from=now - timedelta(days=2),
                    effective_to=None,
                ),
                BillingDomainBinding(
                    domain_binding_bid="runtime-binding-1",
                    creator_bid="creator-1",
                    host="creator.example.com",
                    status=BILLING_DOMAIN_BINDING_STATUS_VERIFIED,
                    verification_method=BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT,
                    verification_token="token-runtime-1",
                    last_verified_at=now - timedelta(hours=1),
                ),
                BillingDomainBinding(
                    domain_binding_bid="runtime-binding-2",
                    creator_bid="creator-2",
                    host="inactive.example.com",
                    status=BILLING_DOMAIN_BINDING_STATUS_VERIFIED,
                    verification_method=BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT,
                    verification_token="token-runtime-2",
                    last_verified_at=now - timedelta(hours=1),
                ),
            ]
        )
        dao.db.session.commit()

        with app.test_client() as client:
            yield client

        dao.db.session.remove()
        dao.db.drop_all()


def test_runtime_config_returns_billing_extensions_for_custom_domain(
    runtime_config_client,
) -> None:
    response = runtime_config_client.get(
        "/api/runtime-config",
        headers={"Host": "creator.example.com"},
    )
    payload = response.get_json(force=True)["data"]

    assert payload["logoWideUrl"] == "https://cdn.example.com/creator-wide.png"
    assert payload["logoSquareUrl"] == "https://cdn.example.com/creator-square.png"
    assert payload["faviconUrl"] == "https://cdn.example.com/creator-favicon.ico"
    assert payload["homeUrl"] == "https://creator.example.com/home"
    assert payload["billingEnabled"] is True
    assert payload["billingCreditPrecision"] == 4
    assert payload["googleOauthRedirect"] == (
        "https://app.example.com/login/google-callback"
    )
    assert payload["entitlements"] == {
        "branding_enabled": True,
        "custom_domain_enabled": True,
        "priority_class": "priority",
        "analytics_tier": "advanced",
        "support_tier": "business_hours",
    }
    assert payload["branding"] == {
        "logo_wide_url": "https://cdn.example.com/creator-wide.png",
        "logo_square_url": "https://cdn.example.com/creator-square.png",
        "favicon_url": "https://cdn.example.com/creator-favicon.ico",
        "home_url": "https://creator.example.com/home",
    }
    assert payload["legalUrls"]["agreement"] == {
        "zh-CN": "/legal/agreement/zh",
        "en-US": "/legal/agreement/en",
    }
    assert payload["domain"] == {
        "request_host": "creator.example.com",
        "matched": True,
        "is_custom_domain": True,
        "creator_bid": "creator-1",
        "domain_binding_bid": "runtime-binding-1",
        "host": "creator.example.com",
        "binding_status": "verified",
    }


def test_runtime_config_keeps_global_branding_when_host_binding_is_not_effective(
    runtime_config_client,
) -> None:
    response = runtime_config_client.get(
        "/api/runtime-config",
        headers={"Host": "inactive.example.com"},
    )
    payload = response.get_json(force=True)["data"]

    assert payload["logoWideUrl"] == "https://cdn.example.com/global-wide.png"
    assert payload["logoSquareUrl"] == "https://cdn.example.com/global-square.png"
    assert payload["faviconUrl"] == "https://cdn.example.com/global-favicon.ico"
    assert payload["homeUrl"] == "/"
    assert payload["billingEnabled"] is True
    assert payload["billingCreditPrecision"] == 4
    assert payload["entitlements"] == {
        "branding_enabled": False,
        "custom_domain_enabled": False,
        "priority_class": "standard",
        "analytics_tier": "basic",
        "support_tier": "self_serve",
    }
    assert payload["branding"] == {
        "logo_wide_url": None,
        "logo_square_url": None,
        "favicon_url": None,
        "home_url": None,
    }
    assert payload["domain"] == {
        "request_host": "inactive.example.com",
        "matched": True,
        "is_custom_domain": False,
        "creator_bid": None,
        "domain_binding_bid": None,
        "host": None,
        "binding_status": "verified",
    }


def test_runtime_config_uses_shifu_context_for_creator_branding(
    runtime_config_client,
) -> None:
    response = runtime_config_client.get(
        "/api/runtime-config?shifu_bid=shifu-1",
        headers={"Host": "localhost"},
    )
    payload = response.get_json(force=True)["data"]

    assert payload["logoWideUrl"] == "https://cdn.example.com/creator-wide.png"
    assert payload["homeUrl"] == "https://creator.example.com/home"
    assert payload["billingEnabled"] is True
    assert payload["entitlements"]["branding_enabled"] is True
    assert payload["domain"] == {
        "request_host": None,
        "matched": False,
        "is_custom_domain": False,
        "creator_bid": "creator-1",
        "domain_binding_bid": None,
        "host": None,
        "binding_status": None,
    }


def test_runtime_billing_builder_and_route_config_use_dto_outputs(
    runtime_config_client,
) -> None:
    app = runtime_config_client.application

    billing_context = build_runtime_billing_context(
        app,
        creator_bid="creator-1",
        request_host="creator.example.com",
    )
    assert isinstance(billing_context, RuntimeBillingContextDTO)
    assert billing_context.__json__()["domain"]["binding_status"] == "verified"

    response = runtime_config_client.get(
        "/api/runtime-config",
        headers={"Host": "creator.example.com"},
    )
    route_payload = response.get_json(force=True)["data"]
    config = RuntimeConfigDTO(**route_payload)

    assert isinstance(config, RuntimeConfigDTO)
    assert config.billingEnabled is True
    assert config.__json__()["legalUrls"]["privacy"] == {
        "zh-CN": "/legal/privacy/zh",
        "en-US": "/legal/privacy/en",
    }


def test_default_runtime_billing_context_is_database_free(monkeypatch) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.runtime_config.resolve_creator_entitlement_state",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("entitlement resolver must not run in default builder")
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.runtime_config.resolve_runtime_domain_result",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("domain resolver must not run in default builder")
        ),
    )
    payload = build_default_runtime_billing_context(
        creator_bid="creator-1",
        request_host="creator.example.com",
    ).__json__()

    assert payload == {
        "entitlements": {
            "branding_enabled": False,
            "custom_domain_enabled": False,
            "priority_class": "standard",
            "analytics_tier": "basic",
            "support_tier": "self_serve",
        },
        "branding": {
            "logo_wide_url": None,
            "logo_square_url": None,
            "favicon_url": None,
            "home_url": None,
        },
        "domain": {
            "request_host": "creator.example.com",
            "matched": False,
            "is_custom_domain": False,
            "creator_bid": "creator-1",
            "domain_binding_bid": None,
            "host": None,
            "binding_status": None,
        },
    }


def test_runtime_config_reports_disabled_billing_flag(
    runtime_config_client,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.primitives.get_config",
        lambda key, default="": False if key == "BILL_ENABLED" else default,
    )
    monkeypatch.setattr(
        "flaskr.service.billing.primitives.get_common_config",
        lambda key, default=None: False if key == "BILL_ENABLED" else default,
    )
    monkeypatch.setattr(
        config_route,
        "build_runtime_billing_context",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("billing builder should not run when disabled")
        ),
    )

    response = runtime_config_client.get("/api/runtime-config")
    payload = response.get_json(force=True)["data"]

    assert payload["billingEnabled"] is False
    assert payload["entitlements"] == {
        "branding_enabled": False,
        "custom_domain_enabled": False,
        "priority_class": "standard",
        "analytics_tier": "basic",
        "support_tier": "self_serve",
    }
    assert payload["domain"] == {
        "request_host": None,
        "matched": False,
        "is_custom_domain": False,
        "creator_bid": None,
        "domain_binding_bid": None,
        "host": None,
        "binding_status": None,
    }


def test_runtime_config_falls_back_when_billing_context_build_fails(
    runtime_config_client,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        config_route,
        "build_runtime_billing_context",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = runtime_config_client.get(
        "/api/runtime-config?shifu_bid=shifu-1",
        headers={"Host": "creator.example.com"},
    )
    payload = response.get_json(force=True)["data"]

    assert payload["billingEnabled"] is True
    assert payload["logoWideUrl"] == "https://cdn.example.com/global-wide.png"
    assert payload["logoSquareUrl"] == "https://cdn.example.com/global-square.png"
    assert payload["faviconUrl"] == "https://cdn.example.com/global-favicon.ico"
    assert payload["homeUrl"] == "/"
    assert payload["entitlements"] == {
        "branding_enabled": False,
        "custom_domain_enabled": False,
        "priority_class": "standard",
        "analytics_tier": "basic",
        "support_tier": "self_serve",
    }
    assert payload["domain"] == {
        "request_host": "creator.example.com",
        "matched": False,
        "is_custom_domain": False,
        "creator_bid": "creator-1",
        "domain_binding_bid": None,
        "host": None,
        "binding_status": None,
    }
