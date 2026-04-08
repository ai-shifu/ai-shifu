from flask import Flask, request

from flaskr.common.shifu_context import get_shifu_creator_bid, with_shifu_context
from flaskr.service.billing.runtime_config import build_runtime_billing_context
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
        origin = request.host_url.rstrip("/")
        creator_bid = str(get_shifu_creator_bid() or "").strip()
        legal_urls = {
            "agreement": {
                "zh-CN": get_config("LEGAL_AGREEMENT_URL_ZH_CN", "") or "",
                "en-US": get_config("LEGAL_AGREEMENT_URL_EN_US", "") or "",
            },
            "privacy": {
                "zh-CN": get_config("LEGAL_PRIVACY_URL_ZH_CN", "") or "",
                "en-US": get_config("LEGAL_PRIVACY_URL_EN_US", "") or "",
            },
        }

        config = {
            # Content & Course Configuration
            "courseId": get_config("DEFAULT_COURSE_ID", ""),
            "defaultLlmModel": get_config("DEFAULT_LLM_MODEL", ""),
            # WeChat Integration
            "wechatAppId": get_config("WECHAT_APP_ID", ""),
            "enableWechatCode": bool(get_config("WECHAT_APP_ID", "")),
            # Payment Configuration
            "stripePublishableKey": get_config("STRIPE_PUBLISHABLE_KEY", ""),
            "stripeEnabled": _to_bool(get_config("STRIPE_ENABLED", False), False),
            "paymentChannels": _to_list(
                get_config("PAYMENT_CHANNELS_ENABLED", "pingxx,stripe"),
                ["pingxx", "stripe"],
            ),
            "payOrderExpireSeconds": _to_int(
                get_config("PAY_ORDER_EXPIRE_TIME", 600),
                600,
            ),
            # UI Configuration
            "alwaysShowLessonTree": _to_bool(
                get_config("UI_ALWAYS_SHOW_LESSON_TREE", False),
                False,
            ),
            "logoWideUrl": get_config("LOGO_WIDE_URL", ""),
            "logoSquareUrl": get_config("LOGO_SQUARE_URL", ""),
            "faviconUrl": get_config("FAVICON_URL", ""),
            # Analytics & Tracking
            "umamiScriptSrc": get_config(
                "ANALYTICS_UMAMI_SCRIPT",
                "",
            ),
            "umamiWebsiteId": get_config(
                "ANALYTICS_UMAMI_SITE_ID",
                "",
            ),
            # Development & Debugging Tools
            "enableEruda": _to_bool(
                get_config("DEBUG_ERUDA_ENABLED", False),
                False,
            ),
            # Authentication Configuration
            "loginMethodsEnabled": _to_list(
                get_config("LOGIN_METHODS_ENABLED", "phone"),
                ["phone"],
            ),
            "defaultLoginMethod": get_config("DEFAULT_LOGIN_METHOD", "phone"),
            "googleOauthRedirect": f"{origin}/login/google-callback",
            # Redirect Configuration
            "homeUrl": get_config("HOME_URL", "/"),
            "currencySymbol": get_config("CURRENCY_SYMBOL", "¥"),
            # Legal Documents Configuration
            "legalUrls": legal_urls,
            # External API Configuration
            "genMdfApiUrl": get_config("GEN_MDF_API_URL", ""),
        }
        runtime_billing = build_runtime_billing_context(
            app,
            creator_bid=creator_bid,
            request_host=_extract_request_host(),
        )
        branding = runtime_billing["branding"]
        if branding.get("logo_wide_url"):
            config["logoWideUrl"] = branding["logo_wide_url"]
        if branding.get("logo_square_url"):
            config["logoSquareUrl"] = branding["logo_square_url"]
        if branding.get("favicon_url"):
            config["faviconUrl"] = branding["favicon_url"]
        if branding.get("home_url"):
            config["homeUrl"] = branding["home_url"]
        config.update(runtime_billing)
        return make_common_response(config)

    return app
