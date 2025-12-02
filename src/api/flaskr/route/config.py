from flask import Flask, request

from flaskr.common.config import get_config

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
    @app.route(path_prefix + "/config", methods=["GET"])
    @bypass_token_validation
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
            # Core API Configuration
            "apiBaseUrl": get_config(
                "NEXT_PUBLIC_API_BASE_URL", "http://localhost:8080"
            ),
            # Content & Course Configuration
            "courseId": get_config("NEXT_PUBLIC_DEFAULT_COURSE_ID", ""),
            "defaultLlmModel": get_config("DEFAULT_LLM_MODEL", ""),
            # WeChat Integration
            "wechatAppId": get_config("NEXT_PUBLIC_WECHAT_APP_ID", ""),
            "enableWechatCode": _to_bool(
                get_config("NEXT_PUBLIC_WECHAT_CODE_ENABLED", True), True
            ),
            # Payment Configuration
            "stripePublishableKey": get_config(
                "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY", ""
            ),
            "stripeEnabled": _to_bool(
                get_config("NEXT_PUBLIC_STRIPE_ENABLED", False), False
            ),
            "paymentChannels": _to_list(
                get_config("NEXT_PUBLIC_PAYMENT_CHANNELS_ENABLED", "pingxx,stripe"),
                ["pingxx", "stripe"],
            ),
            # UI Configuration
            "alwaysShowLessonTree": _to_bool(
                get_config("NEXT_PUBLIC_UI_ALWAYS_SHOW_LESSON_TREE", False), False
            ),
            "logoHorizontal": get_config("NEXT_PUBLIC_UI_LOGO_HORIZONTAL", ""),
            "logoVertical": get_config("NEXT_PUBLIC_UI_LOGO_VERTICAL", ""),
            "logoUrl": get_config("LOGO_URL", ""),
            # Analytics & Tracking
            "umamiScriptSrc": get_config("NEXT_PUBLIC_ANALYTICS_UMAMI_SCRIPT", ""),
            "umamiWebsiteId": get_config("NEXT_PUBLIC_ANALYTICS_UMAMI_SITE_ID", ""),
            # Development & Debugging Tools
            "enableEruda": _to_bool(
                get_config("NEXT_PUBLIC_DEBUG_ERUDA_ENABLED", False), False
            ),
            # Authentication Configuration
            "loginMethodsEnabled": _to_list(
                get_config("NEXT_PUBLIC_LOGIN_METHODS_ENABLED", "phone"), ["phone"]
            ),
            "defaultLoginMethod": get_config(
                "NEXT_PUBLIC_DEFAULT_LOGIN_METHOD", "phone"
            ),
            "googleOauthRedirect": f"{origin}/login/google-callback",
            # Redirect Configuration
            "homeUrl": get_config("HOME_URL", "/admin"),
            "currencySymbol": get_config("CURRENCY_SYMBOL", "¥"),
            # Legal Documents Configuration
            "legalUrls": legal_urls,
        }
        return make_common_response(config)

    return app
