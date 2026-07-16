from flask import Flask, request

from flaskr.common.config import ENV_VARS
from flaskr.common.public_urls import build_google_oauth_callback_url
from flaskr.common.shifu_context import get_shifu_creator_bid, with_shifu_context
from flaskr.service.billing.dtos import (
    RuntimeConfigDTO,
    RuntimeLegalUrlsDTO,
    RuntimeLocalizedUrlDTO,
)
from flaskr.service.billing.primitives import (
    get_billing_credit_precision,
    is_billing_enabled,
)
from flaskr.service.billing.runtime_config import (
    build_default_runtime_billing_context,
    build_runtime_billing_context,
)
from flaskr.service.billing.customization import (
    build_customization_capabilities,
    is_creator_customization_enabled,
    resolve_creator_public_integrations,
)
from flaskr.service.config.funcs import get_config

from .common import bypass_token_validation, make_common_response


def _to_bool(value, default=False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    value_str = str(value).strip().lower()
    if value_str in {"true", "1", "yes", "y", "on"}:
        return True
    if value_str in {"false", "0", "no", "n", "off"}:
        return False
    return default


def _to_list(value, default=None):
    default = default or []
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",") if item.strip()]
        return items or default
    return default


def _to_int(value, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_request_host() -> str:
    forwarded_host = str(request.headers.get("X-Forwarded-Host", "") or "").strip()
    if forwarded_host:
        return forwarded_host.split(",", 1)[0].strip()
    return str(request.host or "").strip()


def register_config_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/runtime-config", methods=["GET"])
    @bypass_token_validation
    @with_shifu_context()
    def get_runtime_config():
        # An explicit creator_bid lets surfaces without a shifu in the path
        # (e.g. the /admin backend) fetch a creator's branding. Falls back to
        # the shifu-context creator when absent, so existing callers are
        # unaffected. Branding here is public display data already served to
        # learners, so no sensitive data is exposed.
        explicit_creator_bid = str(request.args.get("creator_bid", "") or "").strip()
        creator_bid = explicit_creator_bid or str(get_shifu_creator_bid() or "").strip()
        request_host = _extract_request_host()
        legal_urls = RuntimeLegalUrlsDTO(
            agreement=RuntimeLocalizedUrlDTO(
                **{
                    "zh-CN": get_config("LEGAL_AGREEMENT_URL_ZH_CN", "") or "",
                    "en-US": get_config("LEGAL_AGREEMENT_URL_EN_US", "") or "",
                    "fr-FR": get_config("LEGAL_AGREEMENT_URL_FR_FR", "") or "",
                }
            ),
            privacy=RuntimeLocalizedUrlDTO(
                **{
                    "zh-CN": get_config("LEGAL_PRIVACY_URL_ZH_CN", "") or "",
                    "en-US": get_config("LEGAL_PRIVACY_URL_EN_US", "") or "",
                    "fr-FR": get_config("LEGAL_PRIVACY_URL_FR_FR", "") or "",
                }
            ),
        )
        runtime_billing = None
        billing_enabled = is_billing_enabled()
        if billing_enabled:
            try:
                runtime_billing = build_runtime_billing_context(
                    app,
                    creator_bid=creator_bid,
                    request_host=request_host,
                )
            except Exception:
                # Runtime config is a shared bootstrap dependency. Fall back
                # to a stable empty billing payload instead of failing the
                # whole endpoint when billing data is unavailable.
                app.logger.exception(
                    "Failed to build billing runtime config; using default payload "
                    "creator_bid=%s request_host=%s",
                    creator_bid or "-",
                    request_host or "-",
                )

        if runtime_billing is None:
            runtime_billing = build_default_runtime_billing_context(
                creator_bid=creator_bid,
                request_host=request_host,
            )

        domain_owner_bid = str(
            getattr(runtime_billing.domain, "creator_bid", None) or ""
        ).strip()
        if (
            domain_owner_bid
            and getattr(runtime_billing.domain, "is_custom_domain", False)
            and domain_owner_bid != creator_bid
        ):
            try:
                runtime_billing = build_runtime_billing_context(
                    app,
                    creator_bid=domain_owner_bid,
                    request_host=request_host,
                )
            except Exception:
                app.logger.exception(
                    "Failed to re-resolve billing runtime config for domain "
                    "owner; domain_owner_bid=%s request_host=%s",
                    domain_owner_bid,
                    request_host or "-",
                )
                runtime_billing = build_default_runtime_billing_context(
                    creator_bid=domain_owner_bid,
                    request_host=request_host,
                )

        branding = runtime_billing.branding
        logo_wide_url = branding.logo_wide_url or get_config("LOGO_WIDE_URL", "")
        logo_square_url = branding.logo_square_url or get_config("LOGO_SQUARE_URL", "")
        favicon_url = branding.favicon_url or get_config("FAVICON_URL", "")
        home_url = branding.home_url or get_config(
            "HOME_URL", ENV_VARS["HOME_URL"].default
        )
        contact_us_url = branding.contact_us_url or get_config("CONTACT_US_URL", "")
        official_site_url = get_config("OFFICIAL_SITE_URL", "")

        resolved_creator_bid = domain_owner_bid or creator_bid
        customization_capabilities = build_customization_capabilities(
            runtime_billing.entitlements
        )
        public_integrations = {}
        if resolved_creator_bid and is_creator_customization_enabled():
            try:
                public_integrations = resolve_creator_public_integrations(
                    resolved_creator_bid
                )
            except Exception:
                app.logger.exception(
                    "Failed to resolve creator public integrations; creator_bid=%s",
                    resolved_creator_bid,
                )

        custom_wechat = public_integrations.get("wechat_oauth", {})
        custom_payment_enabled = customization_capabilities.get("custom_payment", False)
        custom_payment_channels = [
            provider
            for provider in ("pingxx", "stripe", "alipay", "wechatpay")
            if provider in public_integrations
        ]
        wechat_app_id = str(custom_wechat.get("app_id") or "") or get_config(
            "WECHAT_APP_ID", ""
        )
        payment_channels = (
            custom_payment_channels
            if custom_payment_enabled
            else _to_list(
                get_config("PAYMENT_CHANNELS_ENABLED", "pingxx,stripe"),
                ["pingxx", "stripe"],
            )
        )
        stripe_publishable_key = str(
            public_integrations.get("stripe", {}).get("publishable_key") or ""
        ) or get_config("STRIPE_PUBLISHABLE_KEY", "")

        config = RuntimeConfigDTO(
            defaultLlmModel=get_config("DEFAULT_LLM_MODEL", ""),
            wechatAppId=wechat_app_id,
            enableWechatCode=bool(wechat_app_id),
            billingEnabled=billing_enabled,
            billingCreditPrecision=get_billing_credit_precision(),
            stripePublishableKey=stripe_publishable_key,
            stripeEnabled=(
                "stripe" in custom_payment_channels
                if custom_payment_enabled
                else _to_bool(get_config("STRIPE_ENABLED", False), False)
            ),
            paymentChannels=payment_channels,
            payOrderExpireSeconds=_to_int(
                get_config("PAY_ORDER_EXPIRE_TIME", 600),
                600,
            ),
            alwaysShowLessonTree=_to_bool(
                get_config("UI_ALWAYS_SHOW_LESSON_TREE", False),
                False,
            ),
            logoWideUrl=logo_wide_url,
            logoSquareUrl=logo_square_url,
            faviconUrl=favicon_url,
            umamiScriptSrc=get_config(
                "ANALYTICS_UMAMI_SCRIPT",
                "",
            ),
            umamiWebsiteId=get_config(
                "ANALYTICS_UMAMI_SITE_ID",
                "",
            ),
            enableEruda=_to_bool(
                get_config("DEBUG_ERUDA_ENABLED", False),
                False,
            ),
            loginMethodsEnabled=_to_list(
                get_config("LOGIN_METHODS_ENABLED", "phone"),
                ["phone"],
            ),
            defaultLoginMethod=get_config("DEFAULT_LOGIN_METHOD", "phone"),
            googleOauthRedirect=build_google_oauth_callback_url(),
            homeUrl=home_url,
            contactUsUrl=contact_us_url,
            officialSiteUrl=official_site_url,
            currencySymbol=get_config("CURRENCY_SYMBOL", "¥"),
            legalUrls=legal_urls,
            genMdfApiUrl=get_config("GEN_MDF_API_URL", ""),
            entitlements=runtime_billing.entitlements,
            branding=runtime_billing.branding,
            domain=runtime_billing.domain,
            customizationCapabilities=customization_capabilities,
            paymentConfigurationReady=bool(custom_payment_channels),
        )
        return make_common_response(config)

    return app
