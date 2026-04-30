from flask import Flask, request

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
        creator_bid = str(get_shifu_creator_bid() or "").strip()
        request_host = _extract_request_host()
        legal_urls = RuntimeLegalUrlsDTO(
            agreement=RuntimeLocalizedUrlDTO(
                **{
                    "zh-CN": get_config("LEGAL_AGREEMENT_URL_ZH_CN", "") or "",
                    "en-US": get_config("LEGAL_AGREEMENT_URL_EN_US", "") or "",
                }
            ),
            privacy=RuntimeLocalizedUrlDTO(
                **{
                    "zh-CN": get_config("LEGAL_PRIVACY_URL_ZH_CN", "") or "",
                    "en-US": get_config("LEGAL_PRIVACY_URL_EN_US", "") or "",
                }
            ),
        )
        billing_enabled = is_billing_enabled()
        if billing_enabled:
            try:
                runtime_billing = build_runtime_billing_context(
                    app,
                    creator_bid=creator_bid,
                    request_host=request_host,
                )
            except Exception:
                app.logger.exception(
                    "Failed to build billing runtime config; using default payload"
                )
                runtime_billing = build_default_runtime_billing_context(
                    creator_bid=creator_bid,
                    request_host=request_host,
                )
        else:
            runtime_billing = build_default_runtime_billing_context(
                creator_bid=creator_bid,
                request_host=request_host,
            )
        branding = runtime_billing.branding
        logo_wide_url = branding.logo_wide_url or get_config("LOGO_WIDE_URL", "")
        logo_square_url = branding.logo_square_url or get_config("LOGO_SQUARE_URL", "")
        favicon_url = branding.favicon_url or get_config("FAVICON_URL", "")
        home_url = branding.home_url or get_config("HOME_URL", "/")

        config = RuntimeConfigDTO(
            courseId=get_config("DEFAULT_COURSE_ID", ""),
            defaultLlmModel=get_config("DEFAULT_LLM_MODEL", ""),
            wechatAppId=get_config("WECHAT_APP_ID", ""),
            enableWechatCode=bool(get_config("WECHAT_APP_ID", "")),
            billingEnabled=billing_enabled,
            billingCreditPrecision=get_billing_credit_precision(),
            stripePublishableKey=get_config("STRIPE_PUBLISHABLE_KEY", ""),
            stripeEnabled=_to_bool(get_config("STRIPE_ENABLED", False), False),
            paymentChannels=_to_list(
                get_config("PAYMENT_CHANNELS_ENABLED", "pingxx,stripe"),
                ["pingxx", "stripe"],
            ),
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
            currencySymbol=get_config("CURRENCY_SYMBOL", "¥"),
            legalUrls=legal_urls,
            genMdfApiUrl=get_config("GEN_MDF_API_URL", ""),
            entitlements=runtime_billing.entitlements,
            branding=runtime_billing.branding,
            domain=runtime_billing.domain,
        )
        return make_common_response(config)

    return app
