"""Verify runtime config billing behavior."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from flask import Flask
from flaskr import dao
from flaskr.common import public_urls
from flaskr.common.config import ENV_VARS
from flaskr.route import config as config_route
from flaskr.service.billing.consts import (
    BILLING_DOMAIN_BINDING_STATUS_PENDING,
    BILLING_DOMAIN_BINDING_STATUS_VERIFIED,
    BILLING_DOMAIN_SSL_STATUS_ACTIVE,
    BILLING_DOMAIN_SSL_STATUS_NOT_REQUESTED,
    BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT,
    CREDIT_SOURCE_TYPE_MANUAL,
)
from flaskr.service.billing.dtos import RuntimeBillingContextDTO, RuntimeConfigDTO
from flaskr.service.billing.models import BillingDomainBinding, BillingEntitlement
from flaskr.service.billing.runtime_config import (
    build_default_runtime_billing_context,
    build_runtime_billing_context,
)
from flaskr.util.datetime import now_utc

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask.testing import FlaskClient


@pytest.fixture
def runtime_config_client(monkeypatch: object) -> Iterator[FlaskClient]:
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
        "CONTACT_US_URL": "",
        "OFFICIAL_SITE_URL": "https://official.example.com",
        "HOST_URL": "https://app.example.com",
        "CURRENCY_SYMBOL": "¥",
        "LEGAL_AGREEMENT_URL_ZH_CN": "/legal/agreement/zh",
        "LEGAL_AGREEMENT_URL_EN_US": "/legal/agreement/en",
        "LEGAL_AGREEMENT_URL_DE_DE": "/legal/agreement/de",
        "LEGAL_AGREEMENT_URL_ES_ES": "/legal/agreement/es",
        "LEGAL_AGREEMENT_URL_FR_FR": "/legal/agreement/fr",
        "LEGAL_AGREEMENT_URL_UR_PK": "/legal/agreement/ur",
        "LEGAL_PRIVACY_URL_ZH_CN": "/legal/privacy/zh",
        "LEGAL_PRIVACY_URL_EN_US": "/legal/privacy/en",
        "LEGAL_PRIVACY_URL_DE_DE": "/legal/privacy/de",
        "LEGAL_PRIVACY_URL_ES_ES": "/legal/privacy/es",
        "LEGAL_PRIVACY_URL_FR_FR": "",
        "LEGAL_PRIVACY_URL_UR_PK": "/legal/privacy/ur",
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
        "flaskr.service.billing.domains.get_config",
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
        lambda _app, shifu_bid: "creator-1" if shifu_bid == "shifu-1" else None,
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
                            "contact_us_url": "https://creator.example.com/contact",
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
                    ssl_status=BILLING_DOMAIN_SSL_STATUS_ACTIVE,
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
    runtime_config_client: object,
) -> None:
    response = runtime_config_client.get(
        "/api/runtime-config",
        headers={"Host": "creator.example.com"},
    )
    payload = response.get_json(force=True)["data"]

    assert "courseId" not in payload
    assert payload["logoWideUrl"] == "https://cdn.example.com/creator-wide.png"
    assert payload["logoSquareUrl"] == "https://cdn.example.com/creator-square.png"
    assert payload["faviconUrl"] == "https://cdn.example.com/creator-favicon.ico"
    assert payload["homeUrl"] == "https://creator.example.com/home"
    assert payload["contactUsUrl"] == "https://creator.example.com/contact"
    assert payload["officialSiteUrl"] == "https://official.example.com"
    assert payload["billingEnabled"] is True
    assert payload["billingCreditPrecision"] == 4
    # Custom domains cannot complete the WeChat OAuth redirect (error 10003),
    # so the WeChat code flow must be disabled and the app id hidden.
    assert payload["wechatAppId"] == ""
    assert payload["enableWechatCode"] is False
    assert payload["googleOauthRedirect"] == (
        "https://app.example.com/login/google-callback"
    )
    assert payload["entitlements"] == {
        "branding_enabled": True,
        "custom_domain_enabled": True,
        "custom_wechat_enabled": False,
        "custom_payment_enabled": False,
        "priority_class": "priority",
        "analytics_tier": "advanced",
        "support_tier": "business_hours",
    }
    assert payload["branding"] == {
        "logo_wide_url": "https://cdn.example.com/creator-wide.png",
        "logo_square_url": "https://cdn.example.com/creator-square.png",
        "favicon_url": "https://cdn.example.com/creator-favicon.ico",
        "home_url": "https://creator.example.com/home",
        "contact_us_url": "https://creator.example.com/contact",
    }
    assert payload["legalUrls"]["privacy"]["ur-PK"] == "/legal/privacy/ur"
    assert payload["legalUrls"]["agreement"] == {
        "zh-CN": "/legal/agreement/zh",
        "en-US": "/legal/agreement/en",
        "de-DE": "/legal/agreement/de",
        "es-ES": "/legal/agreement/es",
        "fr-FR": "/legal/agreement/fr",
        "ar-SA": "",
        "th-TH": "",
        "ur-PK": "/legal/agreement/ur",
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


def test_runtime_config_hides_creator_keys_without_matching_capability(
    runtime_config_client: object,
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(config_route, "is_creator_customization_enabled", lambda: True)
    monkeypatch.setattr(
        config_route,
        "resolve_creator_public_integrations",
        lambda _creator_bid: {
            "wechat_oauth": {"app_id": "wx-custom"},
            "stripe": {"publishable_key": "pk_creator"},
        },
    )

    response = runtime_config_client.get(
        "/api/runtime-config?shifu_bid=shifu-1",
        headers={"Host": "creator.example.com"},
    )
    payload = response.get_json(force=True)["data"]

    assert payload["entitlements"]["custom_wechat_enabled"] is False
    assert payload["entitlements"]["custom_payment_enabled"] is False
    assert payload["wechatAppId"] == ""
    assert payload["enableWechatCode"] is False
    assert payload["stripePublishableKey"] == "pk_test_global"
    assert payload["paymentChannels"] == ["pingxx", "stripe"]
    assert payload["paymentConfigurationReady"] is False


def test_runtime_config_uses_origin_header_for_google_redirect_when_host_url_missing(
    runtime_config_client: object,
    monkeypatch: object,
) -> None:
    original_route_get_config = config_route.get_config

    def get_config_override(key: object, default: object = "") -> object:
        if key == "HOST_URL":
            return ""
        return original_route_get_config(key, default)

    monkeypatch.setattr(config_route, "get_config", get_config_override)
    monkeypatch.setattr(public_urls, "get_config", get_config_override)

    response = runtime_config_client.get(
        "/api/runtime-config",
        headers={
            "Origin": "https://frontend-origin.example.com",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "forwarded.example.com",
        },
    )
    payload = response.get_json(force=True)["data"]

    assert response.status_code == 200
    assert payload["googleOauthRedirect"] == (
        "https://frontend-origin.example.com/login/google-callback"
    )


def test_runtime_config_returns_empty_official_site_url_when_unconfigured(
    runtime_config_client: object,
    monkeypatch: object,
) -> None:
    original_route_get_config = config_route.get_config

    def get_config_override(key: object, default: object = "") -> object:
        if key == "OFFICIAL_SITE_URL":
            return ""
        return original_route_get_config(key, default)

    monkeypatch.setattr(config_route, "get_config", get_config_override)

    response = runtime_config_client.get("/api/runtime-config")
    payload = response.get_json(force=True)["data"]

    assert response.status_code == 200
    assert payload["officialSiteUrl"] == ""


def test_runtime_config_uses_registered_home_url_default_on_config_lock_miss(
    runtime_config_client: object,
    monkeypatch: object,
) -> None:
    original_route_get_config = config_route.get_config

    def get_config_override(key: object, default: object = None) -> object:
        if key == "HOME_URL":
            return default
        return original_route_get_config(key, default)

    monkeypatch.setattr(config_route, "get_config", get_config_override)

    response = runtime_config_client.get("/api/runtime-config")
    payload = response.get_json(force=True)["data"]

    assert response.status_code == 200
    assert ENV_VARS["HOME_URL"].default == "/admin"
    assert payload["homeUrl"] == ENV_VARS["HOME_URL"].default


def test_runtime_config_keeps_global_branding_when_host_binding_is_not_effective(
    runtime_config_client: object,
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
    assert payload["contactUsUrl"] == ""
    assert payload["billingEnabled"] is True
    assert payload["billingCreditPrecision"] == 4
    # Not an effective custom domain -> the WeChat code flow stays enabled.
    assert payload["wechatAppId"] == "wechat-app-1"
    assert payload["enableWechatCode"] is True
    assert payload["entitlements"] == {
        "branding_enabled": False,
        "custom_domain_enabled": False,
        "custom_wechat_enabled": False,
        "custom_payment_enabled": False,
        "priority_class": "standard",
        "analytics_tier": "basic",
        "support_tier": "self_serve",
    }
    assert payload["branding"] == {
        "logo_wide_url": None,
        "logo_square_url": None,
        "favicon_url": None,
        "home_url": None,
        "contact_us_url": None,
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


def _assert_global_site_branding(payload: dict[str, object]) -> None:
    assert payload["logoWideUrl"] == "https://cdn.example.com/global-wide.png"
    assert payload["logoSquareUrl"] == "https://cdn.example.com/global-square.png"
    assert payload["faviconUrl"] == "https://cdn.example.com/global-favicon.ico"
    assert payload["homeUrl"] == "/"
    assert payload["contactUsUrl"] == ""
    assert all(value is None for value in payload["branding"].values())


def test_runtime_config_keeps_course_entitlements_without_changing_official_branding(
    runtime_config_client: object,
) -> None:
    response = runtime_config_client.get(
        "/api/runtime-config?shifu_bid=shifu-1",
        headers={"Host": "app.example.com"},
    )
    payload = response.get_json(force=True)["data"]

    _assert_global_site_branding(payload)
    assert payload["billingEnabled"] is True
    assert payload["entitlements"]["branding_enabled"] is True
    assert payload["domain"] == {
        "request_host": "app.example.com",
        "matched": False,
        "is_custom_domain": False,
        "creator_bid": "creator-1",
        "domain_binding_bid": None,
        "host": None,
        "binding_status": None,
    }


def test_runtime_config_keeps_account_entitlements_without_changing_official_branding(
    runtime_config_client: object,
) -> None:
    # Legacy account-specific requests must not replace the site's brand.
    response = runtime_config_client.get(
        "/api/runtime-config?creator_bid=creator-1",
        headers={"Host": "localhost"},
    )
    payload = response.get_json(force=True)["data"]

    _assert_global_site_branding(payload)
    assert payload["entitlements"]["branding_enabled"] is True


@pytest.mark.parametrize("creator_bid", ["creator-1", "creator-2"])
def test_customer_site_branding_does_not_depend_on_the_requested_account(
    runtime_config_client: object,
    creator_bid: str,
) -> None:
    response = runtime_config_client.get(
        "/api/runtime-config",
        query_string={"creator_bid": creator_bid},
        headers={"Host": "creator.example.com"},
    )
    payload = response.get_json(force=True)["data"]

    assert payload["logoWideUrl"] == "https://cdn.example.com/creator-wide.png"
    assert payload["logoSquareUrl"] == "https://cdn.example.com/creator-square.png"
    assert payload["faviconUrl"] == "https://cdn.example.com/creator-favicon.ico"
    assert payload["homeUrl"] == "https://creator.example.com/home"
    assert payload["contactUsUrl"] == "https://creator.example.com/contact"
    assert payload["domain"]["creator_bid"] == "creator-1"
    assert payload["entitlements"]["branding_enabled"] is True


@pytest.mark.parametrize("creator_bid", ["creator-1", "creator-2"])
@pytest.mark.parametrize("host", ["app.example.com", "creator.example.com"])
@pytest.mark.parametrize("host_context_available", [True, False])
@pytest.mark.parametrize("has_course_context", [True, False])
def test_domain_branding_preserves_the_validated_payment_context(
    runtime_config_client: object,
    monkeypatch: object,
    creator_bid: str,
    host: str,
    host_context_available: bool,
    has_course_context: bool,
) -> None:
    if not host_context_available:
        # Best-effort bootstrap lookup can fail before the billing lookup succeeds.
        monkeypatch.setattr(
            "flaskr.common.shifu_context._resolve_host_creator_bid",
            lambda _app, _host: None,
        )
    with runtime_config_client.application.app_context():
        for row in BillingEntitlement.query.all():
            row.feature_payload = {
                **(row.feature_payload or {}),
                "custom_payment_enabled": True,
            }
        dao.db.session.commit()
    monkeypatch.setattr(config_route, "is_creator_customization_enabled", lambda: True)
    monkeypatch.setattr(
        "flaskr.service.billing.customization.is_creator_customization_enabled",
        lambda: True,
    )
    requested_accounts = []

    def integrations(account_bid: str) -> dict[str, dict[str, str]]:
        requested_accounts.append(account_bid)
        return {"stripe": {"publishable_key": f"pk_{account_bid}"}}

    monkeypatch.setattr(
        config_route, "resolve_creator_public_integrations", integrations
    )
    query = {"creator_bid": creator_bid}
    if has_course_context:
        query["shifu_bid"] = "shifu-1"
    payload = runtime_config_client.get(
        "/api/runtime-config",
        query_string=query,
        headers={"Host": host},
    ).get_json(force=True)["data"]

    expected_creator_bid = (
        "creator-1"
        if host == "creator.example.com" or has_course_context
        else creator_bid
    )
    assert requested_accounts == [expected_creator_bid]
    assert payload["stripePublishableKey"] == f"pk_{expected_creator_bid}"
    assert payload["paymentChannels"] == ["stripe"]
    assert payload["paymentConfigurationReady"] is True
    assert payload["entitlements"]["branding_enabled"] is (
        expected_creator_bid == "creator-1"
    )
    if host == "app.example.com":
        _assert_global_site_branding(payload)
    else:
        assert payload["logoWideUrl"] == "https://cdn.example.com/creator-wide.png"


def test_legacy_account_selector_cannot_override_the_requested_course_owner(
    runtime_config_client: object,
) -> None:
    payload = runtime_config_client.get(
        "/api/runtime-config?shifu_bid=shifu-1&creator_bid=creator-2",
        headers={"Host": "app.example.com"},
    ).get_json(force=True)["data"]

    _assert_global_site_branding(payload)
    assert payload["entitlements"]["branding_enabled"] is True
    assert payload["domain"]["creator_bid"] == "creator-1"


@pytest.mark.parametrize("invalid_state", ["pending", "tls", "disabled", "expired"])
def test_ineffective_customer_domain_keeps_global_branding_even_with_a_branded_course(
    runtime_config_client: object,
    invalid_state: str,
) -> None:
    with runtime_config_client.application.app_context():
        binding = BillingDomainBinding.query.filter_by(host="creator.example.com").one()
        entitlement = BillingEntitlement.query.filter_by(creator_bid="creator-1").one()
        if invalid_state == "pending":
            binding.status = BILLING_DOMAIN_BINDING_STATUS_PENDING
        elif invalid_state == "tls":
            binding.ssl_status = BILLING_DOMAIN_SSL_STATUS_NOT_REQUESTED
        elif invalid_state == "disabled":
            entitlement.custom_domain_enabled = 0
        else:
            entitlement.effective_to = now_utc() - timedelta(days=1)
        dao.db.session.commit()

    payload = runtime_config_client.get(
        "/api/runtime-config?shifu_bid=shifu-1",
        headers={"Host": "creator.example.com"},
    ).get_json(force=True)["data"]

    _assert_global_site_branding(payload)
    assert payload["domain"]["is_custom_domain"] is False


def test_accidental_customer_binding_cannot_override_the_official_domain(
    runtime_config_client: object,
) -> None:
    from flaskr.service.billing.domains import resolve_creator_bid_by_host

    app = runtime_config_client.application
    with app.app_context():
        binding = BillingDomainBinding.query.filter_by(host="creator.example.com").one()
        binding.host = "app.example.com"
        dao.db.session.commit()
        assert resolve_creator_bid_by_host(app, "APP.EXAMPLE.COM:443") is None

    payload = runtime_config_client.get(
        "/api/runtime-config?shifu_bid=shifu-1",
        headers={"Host": "app.example.com"},
    ).get_json(force=True)["data"]

    _assert_global_site_branding(payload)
    assert payload["domain"]["is_custom_domain"] is False
    assert payload["entitlements"]["branding_enabled"] is True


def test_runtime_config_without_creator_param_keeps_global_defaults(
    runtime_config_client: object,
) -> None:
    # No shifu_bid and no creator_bid -> existing behavior unchanged (global).
    response = runtime_config_client.get(
        "/api/runtime-config",
        headers={"Host": "localhost"},
    )
    payload = response.get_json(force=True)["data"]

    assert payload["logoWideUrl"] != "https://cdn.example.com/creator-wide.png"
    assert payload["entitlements"]["branding_enabled"] is False


def test_runtime_billing_builder_and_route_config_use_dto_outputs(
    runtime_config_client: object,
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
    assert config.billing_enabled is True
    assert config.official_site_url == "https://official.example.com"
    assert config.__json__()["legalUrls"]["privacy"] == {
        "zh-CN": "/legal/privacy/zh",
        "en-US": "/legal/privacy/en",
        "de-DE": "/legal/privacy/de",
        "es-ES": "/legal/privacy/es",
        "fr-FR": "",
        "ar-SA": "",
        "th-TH": "",
        "ur-PK": "/legal/privacy/ur",
    }


def test_default_runtime_billing_context_is_database_free(monkeypatch: object) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.runtime_config.resolve_creator_entitlement_state",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("entitlement resolver must not run in default builder")
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.runtime_config.resolve_runtime_domain_result",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
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
            "custom_wechat_enabled": False,
            "custom_payment_enabled": False,
            "priority_class": "standard",
            "analytics_tier": "basic",
            "support_tier": "self_serve",
        },
        "branding": {
            "logo_wide_url": None,
            "logo_square_url": None,
            "favicon_url": None,
            "home_url": None,
            "contact_us_url": None,
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
    runtime_config_client: object,
    monkeypatch: object,
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
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("billing builder should not run when disabled")
        ),
    )

    response = runtime_config_client.get("/api/runtime-config")
    payload = response.get_json(force=True)["data"]

    assert payload["billingEnabled"] is False
    # Billing disabled means no custom-domain resolution, so the WeChat code
    # flow keeps its global configuration.
    assert payload["wechatAppId"] == "wechat-app-1"
    assert payload["enableWechatCode"] is True
    assert payload["entitlements"] == {
        "branding_enabled": False,
        "custom_domain_enabled": False,
        "custom_wechat_enabled": False,
        "custom_payment_enabled": False,
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
    runtime_config_client: object,
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(
        config_route,
        "build_runtime_billing_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
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
    assert payload["contactUsUrl"] == ""
    assert payload["entitlements"] == {
        "branding_enabled": False,
        "custom_domain_enabled": False,
        "custom_wechat_enabled": False,
        "custom_payment_enabled": False,
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
