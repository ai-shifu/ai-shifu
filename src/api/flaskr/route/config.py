from flask import Flask, request

from flaskr.common.shifu_context import with_shifu_context
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


def register_config_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/runtime-config", methods=["GET"])
    @bypass_token_validation
    @with_shifu_context()
    def get_runtime_config():
        origin = request.host_url.rstrip("/")
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
            "homeUrl": get_config("HOME_URL", "/admin"),
            "currencySymbol": get_config("CURRENCY_SYMBOL", "¥"),
            # Legal Documents Configuration
            "legalUrls": legal_urls,
        }
        return make_common_response(config)

    return app
