import os
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Dict, List, Type
from flask import Flask
from flask import Config as FlaskConfig


class EnvironmentConfigError(Exception):
    """Exception raised for environment configuration errors."""

    pass


@dataclass
class EnvVar:
    """Environment variable definition with metadata."""

    name: str
    required: bool = False  # Whether variable must be explicitly set in environment
    default: Any = None  # Default value if not set (only if required=False)
    example: Any = None  # Optional value to emit in generated example files
    type: Type = str  # Using Type annotation to avoid conflict
    description: str = ""
    validator: Optional[Callable[[Any], bool]] = None
    secret: bool = False
    group: str = "general"
    depends_on: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate EnvVar configuration after initialization."""
        if self.required and self.default is not None:
            raise ValueError(
                f"Environment variable '{self.name}' is marked as required "
                "but has a default value. Required variables must not have defaults."
            )

    def validate_value(self, value: Any) -> bool:
        """Validate the environment variable value."""
        if self.validator:
            return self.validator(value)
        return True

    def convert_type(self, value: Any) -> Any:
        """Convert string value to the specified type."""
        # Trim whitespace from string values before conversion
        if isinstance(value, str):
            value = value.strip()
        if value is None or value == "":
            return self.default
        # If value is already the correct type, return it
        if isinstance(value, self.type):
            return value
        if self.type is bool:
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)
        elif self.type is int:
            try:
                return int(value)
            except ValueError:
                raise EnvironmentConfigError(
                    f"Invalid integer value for {self.name}: {value}"
                )
        elif self.type is float:
            try:
                return float(value)
            except ValueError:
                raise EnvironmentConfigError(
                    f"Invalid float value for {self.name}: {value}"
                )
        elif self.type is list:
            if isinstance(value, str):
                return [item.strip() for item in value.split(",") if item.strip()]
            return list(value)
        else:
            return str(value)


# Environment variable registry
ENV_VARS: Dict[str, EnvVar] = {
    # Application Configuration
    "LOGGING_PATH": EnvVar(
        name="LOGGING_PATH",
        default="logs/ai-shifu.log",
        description="Path of log file",
        group="app",
    ),
    "ASK_MAX_HISTORY_LEN": EnvVar(
        name="ASK_MAX_HISTORY_LEN",
        default=10,
        type=int,
        description="The count of history messages to append to LLM's context in ask",
        group="app",
    ),
    "SHIFU_PERMISSION_CACHE_EXPIRE": EnvVar(
        name="SHIFU_PERMISSION_CACHE_EXPIRE",
        default=300,
        type=int,
        description="Shifu permission cache expiration time in seconds",
        group="app",
    ),
    "TZ": EnvVar(
        name="TZ",
        default="UTC",
        description="Timezone setting for the application",
        group="app",
    ),
    # Frontend Configuration
    "PORT": EnvVar(
        name="PORT",
        default=5000,
        type=int,
        description="Frontend server port",
        group="frontend",
        validator=lambda x: 1 <= int(x) <= 65535,
    ),
    "CURRENCY_SYMBOL": EnvVar(
        name="CURRENCY_SYMBOL",
        default="\u00a5",
        description="Currency symbol used in Cook Web (default: ¥)",
        group="frontend",
    ),
    "HOME_URL": EnvVar(
        name="HOME_URL",
        default="/admin",
        description="Default redirect path after login",
        group="frontend",
    ),
    "LOGO_WIDE_URL": EnvVar(
        name="LOGO_WIDE_URL",
        default="",
        description="Custom wide logo URL override returned by /api/config",
        group="frontend",
    ),
    "LOGO_SQUARE_URL": EnvVar(
        name="LOGO_SQUARE_URL",
        default="",
        description="Custom square logo URL override returned by /api/config",
        group="frontend",
    ),
    "FAVICON_URL": EnvVar(
        name="FAVICON_URL",
        default="",
        description="Custom favicon URL override returned by /api/config",
        group="frontend",
    ),
    "ANALYTICS_UMAMI_SCRIPT": EnvVar(
        name="ANALYTICS_UMAMI_SCRIPT",
        default="",
        description="Umami analytics script URL",
        group="frontend",
    ),
    "ANALYTICS_UMAMI_SITE_ID": EnvVar(
        name="ANALYTICS_UMAMI_SITE_ID",
        default="",
        description="Umami analytics site identifier",
        group="frontend",
    ),
    "DEFAULT_COURSE_ID": EnvVar(
        name="DEFAULT_COURSE_ID",
        default="",
        description="Default course id for Cook Web",
        group="frontend",
    ),
    "DEFAULT_LOGIN_METHOD": EnvVar(
        name="DEFAULT_LOGIN_METHOD",
        default="phone",
        description='Default login method tab. Values: "phone" | "email" | "google"',
        group="frontend",
    ),
    "DEBUG_ERUDA_ENABLED": EnvVar(
        name="DEBUG_ERUDA_ENABLED",
        default=False,
        type=bool,
        description="Enable Eruda debug console",
        group="frontend",
    ),
    "LOGIN_METHODS_ENABLED": EnvVar(
        name="LOGIN_METHODS_ENABLED",
        default="phone",
        description="""Login methods exposed to users.
Values: "phone" | "email" | "google" combinations (comma-separated)
Default: "phone".""",
        group="frontend",
    ),
    "STRIPE_ENABLED": EnvVar(
        name="STRIPE_ENABLED",
        default=False,
        type=bool,
        description="Enable Stripe payment entry points on Cook Web",
        group="frontend",
    ),
    "UI_ALWAYS_SHOW_LESSON_TREE": EnvVar(
        name="UI_ALWAYS_SHOW_LESSON_TREE",
        default=False,
        type=bool,
        description="Always show lesson tree in Cook Web",
        group="frontend",
    ),
    "UI_LOGO_HORIZONTAL": EnvVar(
        name="UI_LOGO_HORIZONTAL",
        default="",
        description="Horizontal logo URL for Cook Web",
        group="frontend",
    ),
    "UI_LOGO_VERTICAL": EnvVar(
        name="UI_LOGO_VERTICAL",
        default="",
        description="Vertical logo URL for Cook Web",
        group="frontend",
    ),
    "GEN_MDF_API_URL": EnvVar(
        name="GEN_MDF_API_URL",
        default="",
        description="API URL for generating MDF (Markdown Flow) content",
        group="integrations",
    ),
    "GEN_MDF_APP_ID": EnvVar(
        name="GEN_MDF_APP_ID",
        default="",
        description="Application ID for MDF API authentication (X-App-Id header)",
        secret=True,
        group="integrations",
    ),
    "WECHAT_APP_ID": EnvVar(
        name="WECHAT_APP_ID",
        default="",
        description="WeChat App ID for OAuth / QR login",
        group="auth",
    ),
    "WECHAT_APP_SECRET": EnvVar(
        name="WECHAT_APP_SECRET",
        default="",
        description="WeChat App secret for server-side exchanges",
        group="auth",
        secret=True,
    ),
    # Legal Documents Configuration
    "LEGAL_AGREEMENT_URL_ZH_CN": EnvVar(
        name="LEGAL_AGREEMENT_URL_ZH_CN",
        default="",
        description="Service agreement URL for Chinese (zh-CN) users. Leave empty to disable the link.",
        group="legal",
    ),
    "LEGAL_AGREEMENT_URL_EN_US": EnvVar(
        name="LEGAL_AGREEMENT_URL_EN_US",
        default="",
        description="Service agreement URL for English (en-US) users. Leave empty to disable the link.",
        group="legal",
    ),
    "LEGAL_PRIVACY_URL_ZH_CN": EnvVar(
        name="LEGAL_PRIVACY_URL_ZH_CN",
        default="",
        description="Privacy policy URL for Chinese (zh-CN) users. Leave empty to disable the link.",
        group="legal",
    ),
    "LEGAL_PRIVACY_URL_EN_US": EnvVar(
        name="LEGAL_PRIVACY_URL_EN_US",
        default="",
        description="Privacy policy URL for English (en-US) users. Leave empty to disable the link.",
        group="legal",
    ),
    # LLM Configuration
    "OPENAI_API_KEY": EnvVar(
        name="OPENAI_API_KEY",
        default="",
        description="OpenAI API key for GPT models",
        secret=True,
        group="llm",
    ),
    "OPENAI_BASE_URL": EnvVar(
        name="OPENAI_BASE_URL",
        description="OpenAI API base URL",
        group="llm",
    ),
    "ERNIE_API_ID": EnvVar(
        name="ERNIE_API_ID",
        default="",
        description="Baidu ERNIE API ID",
        secret=True,
        group="llm",
    ),
    "ERNIE_API_SECRET": EnvVar(
        name="ERNIE_API_SECRET",
        default="",
        description="Baidu ERNIE API Secret",
        secret=True,
        group="llm",
    ),
    "ERNIE_API_KEY": EnvVar(
        name="ERNIE_API_KEY",
        default="",
        description="Baidu ERNIE API Key",
        secret=True,
        group="llm",
    ),
    "ARK_API_KEY": EnvVar(
        name="ARK_API_KEY",
        default="",
        description="ByteDance Volcengine Ark API Key",
        secret=True,
        group="llm",
    ),
    "ARK_ACCESS_KEY_ID": EnvVar(
        name="ARK_ACCESS_KEY_ID",
        default="",
        description="ByteDance Volcengine Ark access key ID (used for Volcengine TTS WebSocket auth)",
        secret=True,
        group="llm",
    ),
    "ARK_SECRET_ACCESS_KEY": EnvVar(
        name="ARK_SECRET_ACCESS_KEY",
        default="",
        description="ByteDance Volcengine Ark secret access key (used for Volcengine TTS WebSocket auth)",
        secret=True,
        group="llm",
    ),
    "SILICON_API_KEY": EnvVar(
        name="SILICON_API_KEY",
        default="",
        description="SiliconFlow API Key",
        secret=True,
        group="llm",
    ),
    "GLM_API_KEY": EnvVar(
        name="GLM_API_KEY",
        default="",
        description="Zhipu BigModel GLM API Key",
        secret=True,
        group="llm",
    ),
    "BIGMODEL_API_KEY": EnvVar(
        name="BIGMODEL_API_KEY",
        default="",
        description="Zhipu BigModel API Key (alternative format)",
        secret=True,
        group="llm",
    ),
    "DEEPSEEK_API_KEY": EnvVar(
        name="DEEPSEEK_API_KEY",
        default="",
        description="DeepSeek API Key",
        secret=True,
        group="llm",
    ),
    "DEEPSEEK_API_URL": EnvVar(
        name="DEEPSEEK_API_URL",
        default="https://api.deepseek.com",
        description="DeepSeek API URL",
        group="llm",
    ),
    "GEMINI_API_KEY": EnvVar(
        name="GEMINI_API_KEY",
        default="",
        description="Google Gemini API key",
        secret=True,
        group="llm",
    ),
    "GEMINI_API_URL": EnvVar(
        name="GEMINI_API_URL",
        default="",
        description="Optional Google Gemini API base URL (leave blank to use default)",
        group="llm",
    ),
    "QWEN_API_KEY": EnvVar(
        name="QWEN_API_KEY",
        default="",
        description="Alibaba Cloud Qwen API Key",
        secret=True,
        group="llm",
    ),
    "QWEN_API_URL": EnvVar(
        name="QWEN_API_URL",
        default="",
        description="Alibaba Cloud Qwen API URL",
        group="llm",
    ),
    "DEFAULT_LLM_MODEL": EnvVar(
        name="DEFAULT_LLM_MODEL",
        default="",
        description="""Default LLM model. Supported models:
OpenAI: gpt-4o-latest, gpt-4o-mini, gpt-4, gpt-3.5-turbo, chatgpt-4o-latest
ERNIE: ERNIE-4.0-8K, ERNIE-3.5-8K, ERNIE-3.5-128K, ERNIE-Speed-8K, ERNIE-Speed-128K
GLM: glm-4, glm-4-air, glm-4-airx, glm-4-flash, glm-4v, glm-3-turbo
Qwen: qwen-long, qwen-max, qwen-max-longcontext, qwen-plus, qwen-turbo, qwen2-*
DeepSeek: deepseek-chat
Gemini: gemini-1.5-flash, gemini-1.5-flash-8b, gemini-1.5-pro""",
        group="llm",
    ),
    "LLM_ALLOWED_MODELS": EnvVar(
        name="LLM_ALLOWED_MODELS",
        default=[],
        type=list,
        description=(
            "Comma separated list of allowed LLM models to expose in UI. "
            "When empty, all detected models are shown."
        ),
        group="llm",
        required=False,
    ),
    "LLM_ALLOWED_MODEL_DISPLAY_NAMES": EnvVar(
        name="LLM_ALLOWED_MODEL_DISPLAY_NAMES",
        default=[],
        type=list,
        description=(
            "Optional display names for allowed LLM models. Must match the "
            "length and order of LLM_ALLOWED_MODELS. Ignored otherwise."
        ),
        group="llm",
        required=False,
    ),
    "DEFAULT_LLM_TEMPERATURE": EnvVar(
        name="DEFAULT_LLM_TEMPERATURE",
        default=0.3,
        type=float,
        description="Default temperature for LLM generation",
        group="llm",
        validator=lambda x: 0.0 <= float(x) <= 2.0,
    ),
    # Database Configuration
    "SQLALCHEMY_DATABASE_URI": EnvVar(
        name="SQLALCHEMY_DATABASE_URI",
        required=True,
        example="mysql://root:ai-shifu@ai-shifu-mysql:3306/ai-shifu?charset=utf8mb4",
        description="""MySQL database connection URI
Example: mysql://username:password@hostname:3306/database_name?charset=utf8mb4""",
        secret=True,
        group="database",
    ),
    "SQLALCHEMY_POOL_SIZE": EnvVar(
        name="SQLALCHEMY_POOL_SIZE",
        default=20,
        type=int,
        description="SQLAlchemy connection pool size",
        group="database",
    ),
    "SQLALCHEMY_POOL_TIMEOUT": EnvVar(
        name="SQLALCHEMY_POOL_TIMEOUT",
        default=30,
        type=int,
        description="SQLAlchemy pool timeout in seconds",
        group="database",
    ),
    "SQLALCHEMY_POOL_RECYCLE": EnvVar(
        name="SQLALCHEMY_POOL_RECYCLE",
        default=3600,
        type=int,
        description="SQLAlchemy pool recycle time in seconds",
        group="database",
    ),
    "SQLALCHEMY_MAX_OVERFLOW": EnvVar(
        name="SQLALCHEMY_MAX_OVERFLOW",
        default=20,
        type=int,
        description="SQLAlchemy max overflow connections",
        group="database",
    ),
    # Redis Configuration
    "REDIS_HOST": EnvVar(
        name="REDIS_HOST",
        default="ai-shifu-redis",
        description="Redis server host (docker-compose service name by default)",
        group="redis",
    ),
    "REDIS_PORT": EnvVar(
        name="REDIS_PORT",
        default=6379,
        type=int,
        description="Redis server port",
        group="redis",
        validator=lambda x: 1 <= int(x) <= 65535,
    ),
    "REDIS_DB": EnvVar(
        name="REDIS_DB",
        default=0,
        type=int,
        description="Redis database number",
        group="redis",
    ),
    "REDIS_PASSWORD": EnvVar(
        name="REDIS_PASSWORD",
        default="",
        description="Redis password",
        secret=True,
        group="redis",
    ),
    "REDIS_USER": EnvVar(
        name="REDIS_USER", default="", description="Redis username", group="redis"
    ),
    "REDIS_KEY_PREFIX": EnvVar(
        name="REDIS_KEY_PREFIX",
        default="ai-shifu:",
        description="Redis key prefix",
        group="redis",
    ),
    # Authentication Configuration
    "SECRET_KEY": EnvVar(
        name="SECRET_KEY",
        required=True,
        example="ai-shifu",
        description="""Secret key for JWT token signing and verification
CRITICAL: Used to encrypt/decrypt user authentication tokens
- Must be a strong random string (at least 32 characters recommended)
- DO NOT change in production (will invalidate all user sessions)
- Keep different values for dev/test/prod environments
- Never commit to version control
Generate secure key: python -c "import secrets; print(secrets.token_urlsafe(32))" """,
        secret=True,
        group="auth",
        validator=lambda value: bool(value and str(value).strip()),
    ),
    "TOKEN_EXPIRE_TIME": EnvVar(
        name="TOKEN_EXPIRE_TIME",
        default=604800,
        type=int,
        description="Token expiration time in seconds",
        group="auth",
    ),
    "RESET_PWD_CODE_EXPIRE_TIME": EnvVar(
        name="RESET_PWD_CODE_EXPIRE_TIME",
        default=300,
        type=int,
        description="Expire time for password reset code in seconds",
        group="auth",
    ),
    "PHONE_CODE_EXPIRE_TIME": EnvVar(
        name="PHONE_CODE_EXPIRE_TIME",
        default=300,
        type=int,
        description="Expire time for phone verification code in seconds",
        group="auth",
    ),
    "GOOGLE_OAUTH_CLIENT_ID": EnvVar(
        name="GOOGLE_OAUTH_CLIENT_ID",
        default="",
        description="OAuth client ID issued by Google",
        group="auth",
    ),
    "GOOGLE_OAUTH_CLIENT_SECRET": EnvVar(
        name="GOOGLE_OAUTH_CLIENT_SECRET",
        default="",
        description="OAuth client secret issued by Google",
        secret=True,
        group="auth",
    ),
    "GOOGLE_OAUTH_TOKEN_ENDPOINT": EnvVar(
        name="GOOGLE_OAUTH_TOKEN_ENDPOINT",
        default="https://oauth2.googleapis.com/token",
        description=(
            "Google OAuth token endpoint URL used by the backend to exchange auth codes."
        ),
        group="auth",
    ),
    "GOOGLE_OAUTH_USERINFO_ENDPOINT": EnvVar(
        name="GOOGLE_OAUTH_USERINFO_ENDPOINT",
        default="https://openidconnect.googleapis.com/v1/userinfo",
        description="Google OpenID Connect userinfo endpoint URL used by the backend.",
        group="auth",
    ),
    "MAIL_CODE_EXPIRE_TIME": EnvVar(
        name="MAIL_CODE_EXPIRE_TIME",
        default=300,
        type=int,
        description="The expiration time of the email verification code (seconds)",
        group="auth",
    ),
    "MAIL_CODE_INTERVAL": EnvVar(
        name="MAIL_CODE_INTERVAL",
        default=60,
        type=int,
        description="The interval time for sending emails",
        group="auth",
    ),
    "SMS_CODE_INTERVAL": EnvVar(
        name="SMS_CODE_INTERVAL",
        default=60,
        type=int,
        description="The minimum interval time for sending text messages to the same mobile phone number",
        group="auth",
    ),
    "IP_MAIL_LIMIT_COUNT": EnvVar(
        name="IP_MAIL_LIMIT_COUNT",
        default=10,
        type=int,
        description="The maximum number of allowed sends",
        group="auth",
    ),
    "IP_MAIL_LIMIT_TIME": EnvVar(
        name="IP_MAIL_LIMIT_TIME",
        default=3600,
        type=int,
        description="The time window for statistics of the number of sends by IP (seconds)",
        group="auth",
    ),
    "IP_SMS_LIMIT_COUNT": EnvVar(
        name="IP_SMS_LIMIT_COUNT",
        default=10,
        type=int,
        description="The maximum number of times IP can send text messages",
        group="auth",
    ),
    "IP_SMS_LIMIT_TIME": EnvVar(
        name="IP_SMS_LIMIT_TIME",
        default=3600,
        type=int,
        description="The time window for statistics of the number of text messages sent by IP (seconds)",
        group="auth",
    ),
    "IP_BAN_TIME": EnvVar(
        name="IP_BAN_TIME",
        default=86400,
        type=int,
        description="IP ban time (seconds)",
        group="auth",
    ),
    "UNIVERSAL_VERIFICATION_CODE": EnvVar(
        name="UNIVERSAL_VERIFICATION_CODE",
        required=False,
        example="1024",
        description=(
            "Universal verification code for testing.\n"
            "**SECURITY WARNING:** Do NOT set this in production environments.\n"
            "If set, it will allow anyone to bypass verification.\n"
            "Only use for local development or testing."
        ),
        group="auth",
    ),
    "ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO": EnvVar(
        name="ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO",
        default=True,
        type=bool,
        description=(
            "When enabled, users logging in from the admin interface are "
            "automatically marked as creators and granted demo course "
            "permissions (DEMO_SHIFU_BID / DEMO_EN_SHIFU_BID if configured). "
            "Intended for demo and staging environments only."
        ),
        group="auth",
    ),
    # Payment Providers
    "PINGXX_SECRET_KEY": EnvVar(
        name="PINGXX_SECRET_KEY",
        default="",
        description="Ping++ API secret key used for charge creation",
        secret=True,
        group="payment",
    ),
    "PINGXX_PRIVATE_KEY_PATH": EnvVar(
        name="PINGXX_PRIVATE_KEY_PATH",
        default="",
        description="Filesystem path to the Ping++ RSA private key",
        group="payment",
    ),
    "PINGXX_APP_ID": EnvVar(
        name="PINGXX_APP_ID",
        default="",
        description="Ping++ application identifier",
        group="payment",
    ),
    "STRIPE_SECRET_KEY": EnvVar(
        name="STRIPE_SECRET_KEY",
        default="",
        description="Stripe secret API key for server-side requests",
        secret=True,
        group="payment",
    ),
    "STRIPE_PUBLISHABLE_KEY": EnvVar(
        name="STRIPE_PUBLISHABLE_KEY",
        default="",
        description="Stripe publishable key shared with client applications",
        group="payment",
    ),
    "STRIPE_WEBHOOK_SECRET": EnvVar(
        name="STRIPE_WEBHOOK_SECRET",
        default="",
        description="Stripe webhook signing secret",
        secret=True,
        group="payment",
    ),
    "STRIPE_API_VERSION": EnvVar(
        name="STRIPE_API_VERSION",
        default="",
        description="Stripe API version to lock requests against",
        group="payment",
    ),
    "STRIPE_SUCCESS_URL": EnvVar(
        name="STRIPE_SUCCESS_URL",
        default="",
        description="Stripe Checkout success redirect URL",
        group="payment",
    ),
    "STRIPE_CANCEL_URL": EnvVar(
        name="STRIPE_CANCEL_URL",
        default="",
        description="Stripe Checkout cancellation redirect URL",
        group="payment",
    ),
    "STRIPE_DEFAULT_CURRENCY": EnvVar(
        name="STRIPE_DEFAULT_CURRENCY",
        default="usd",
        description="Default currency code used for Stripe payments",
        group="payment",
    ),
    "STRIPE_WECHAT_PAY_ENABLED": EnvVar(
        name="STRIPE_WECHAT_PAY_ENABLED",
        default=False,
        type=bool,
        description="Enable WeChat Pay",
        group="payment",
    ),
    "STRIPE_ALIPAY_ENABLED": EnvVar(
        name="STRIPE_ALIPAY_ENABLED",
        default=False,
        type=bool,
        description="Enable Alipay for Stripe",
        group="payment",
    ),
    "PAYMENT_CHANNELS_ENABLED": EnvVar(
        name="PAYMENT_CHANNELS_ENABLED",
        default="pingxx,stripe",
        description="Comma-separated list of enabled payment providers (e.g., pingxx,stripe)",
        group="payment",
    ),
    "PAY_ORDER_EXPIRE_TIME": EnvVar(
        name="PAY_ORDER_EXPIRE_TIME",
        default=600,
        type=int,
        description="Order expiration time in seconds before a new order is created",
        group="payment",
    ),
    # Alibaba Cloud Configuration
    "ALIBABA_CLOUD_SMS_ACCESS_KEY_ID": EnvVar(
        name="ALIBABA_CLOUD_SMS_ACCESS_KEY_ID",
        default="",
        description="Alibaba Cloud settings for sending SMS and uploading files",
        secret=True,
        group="alibaba_cloud",
    ),
    "ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET": EnvVar(
        name="ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET",
        default="",
        description="Alibaba Cloud SMS Access Key Secret",
        secret=True,
        group="alibaba_cloud",
    ),
    "ALIBABA_CLOUD_SMS_SIGN_NAME": EnvVar(
        name="ALIBABA_CLOUD_SMS_SIGN_NAME",
        default="",
        description="Alibaba Cloud SMS sign name",
        group="alibaba_cloud",
    ),
    "ALIBABA_CLOUD_SMS_TEMPLATE_CODE": EnvVar(
        name="ALIBABA_CLOUD_SMS_TEMPLATE_CODE",
        default="",
        description="Alibaba Cloud SMS template code",
        group="alibaba_cloud",
    ),
    "ALIBABA_CLOUD_OSS_ACCESS_KEY_ID": EnvVar(
        name="ALIBABA_CLOUD_OSS_ACCESS_KEY_ID",
        default="",
        description="Alibaba Cloud OSS Access Key ID",
        secret=True,
        group="alibaba_cloud",
    ),
    "ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET": EnvVar(
        name="ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET",
        default="",
        description="Alibaba Cloud OSS Access Key Secret",
        secret=True,
        group="alibaba_cloud",
    ),
    "ALIBABA_CLOUD_OSS_ENDPOINT": EnvVar(
        name="ALIBABA_CLOUD_OSS_ENDPOINT",
        default="oss-cn-beijing.aliyuncs.com",
        description="Alibaba Cloud OSS endpoint",
        group="alibaba_cloud",
    ),
    "ALIBABA_CLOUD_OSS_BUCKET": EnvVar(
        name="ALIBABA_CLOUD_OSS_BUCKET",
        default="",
        description="Alibaba Cloud OSS bucket name",
        group="alibaba_cloud",
    ),
    "ALIBABA_CLOUD_OSS_BASE_URL": EnvVar(
        name="ALIBABA_CLOUD_OSS_BASE_URL",
        default="",
        description="Alibaba Cloud OSS base URL",
        group="alibaba_cloud",
    ),
    "ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_ID": EnvVar(
        name="ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_ID",
        default="",
        description="Alibaba Cloud OSS Courses Access Key ID",
        secret=True,
        group="alibaba_cloud",
    ),
    "ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_SECRET": EnvVar(
        name="ALIBABA_CLOUD_OSS_COURSES_ACCESS_KEY_SECRET",
        default="",
        description="Alibaba Cloud OSS Courses Access Key Secret",
        secret=True,
        group="alibaba_cloud",
    ),
    "ALIBABA_CLOUD_OSS_COURSES_ENDPOINT": EnvVar(
        name="ALIBABA_CLOUD_OSS_COURSES_ENDPOINT",
        default="oss-cn-beijing.aliyuncs.com",
        description="Alibaba Cloud OSS Courses endpoint",
        group="alibaba_cloud",
    ),
    "ALIBABA_CLOUD_OSS_COURSES_BUCKET": EnvVar(
        name="ALIBABA_CLOUD_OSS_COURSES_BUCKET",
        default="",
        description="Alibaba Cloud OSS Courses bucket name",
        group="alibaba_cloud",
    ),
    "ALIBABA_CLOUD_OSS_COURSES_URL": EnvVar(
        name="ALIBABA_CLOUD_OSS_COURSES_URL",
        default="",
        description="Alibaba Cloud OSS Courses URL",
        group="alibaba_cloud",
    ),
    # Monitoring and Tracking
    "LANGFUSE_PUBLIC_KEY": EnvVar(
        name="LANGFUSE_PUBLIC_KEY",
        default="",
        description="Langfuse settings for tracking LLM",
        secret=True,
        group="monitoring",
    ),
    "LANGFUSE_SECRET_KEY": EnvVar(
        name="LANGFUSE_SECRET_KEY",
        default="",
        description="Langfuse secret key for LLM tracking",
        secret=True,
        group="monitoring",
    ),
    "LANGFUSE_HOST": EnvVar(
        name="LANGFUSE_HOST",
        default="",
        description="Langfuse host URL",
        group="monitoring",
    ),
    # Content Detection
    "CHECK_PROVIDER": EnvVar(
        name="CHECK_PROVIDER",
        default="ilivedata",
        description="Content detection provider",
        group="content_detection",
    ),
    "ILIVEDATA_PID": EnvVar(
        name="ILIVEDATA_PID",
        default="",
        description="ILIVEDATA project ID",
        group="content_detection",
    ),
    "ILIVEDATA_SECRET_KEY": EnvVar(
        name="ILIVEDATA_SECRET_KEY",
        default="",
        description="ILIVEDATA secret key",
        secret=True,
        group="content_detection",
    ),
    "NETEASE_YIDUN_SECRET_ID": EnvVar(
        name="NETEASE_YIDUN_SECRET_ID",
        default="",
        description="Netease Yidun secret ID",
        secret=True,
        group="content_detection",
    ),
    "NETEASE_YIDUN_SECRET_KEY": EnvVar(
        name="NETEASE_YIDUN_SECRET_KEY",
        default="",
        description="Netease Yidun secret key",
        secret=True,
        group="content_detection",
    ),
    "NETEASE_YIDUN_BUSINESS_ID": EnvVar(
        name="NETEASE_YIDUN_BUSINESS_ID",
        default="",
        description="Netease Yidun business ID",
        group="content_detection",
    ),
    # Lark/Feishu Integration
    "LARK_APP_ID": EnvVar(
        name="LARK_APP_ID",
        default="",
        description="Lark (Feishu) app ID",
        group="integrations",
    ),
    "LARK_APP_SECRET": EnvVar(
        name="LARK_APP_SECRET",
        default="",
        description="Lark (Feishu) app secret",
        secret=True,
        group="integrations",
    ),
    # Email Configuration
    "SMTP_PORT": EnvVar(
        name="SMTP_PORT",
        default=25,
        type=int,
        description="SMTP server port",
        group="email",
        validator=lambda x: 1 <= int(x) <= 65535,
    ),
    "SMTP_USERNAME": EnvVar(
        name="SMTP_USERNAME", default="", description="SMTP username", group="email"
    ),
    "SMTP_SERVER": EnvVar(
        name="SMTP_SERVER", default="", description="SMTP server address", group="email"
    ),
    "SMTP_PASSWORD": EnvVar(
        name="SMTP_PASSWORD",
        default="",
        description="SMTP password",
        secret=True,
        group="email",
    ),
    "SMTP_SENDER": EnvVar(
        name="SMTP_SENDER",
        default="",
        description="SMTP sender email address",
        group="email",
    ),
    # Flask Configuration
    "FLASK_APP": EnvVar(
        name="FLASK_APP",
        default="app.py",
        description="Flask application entry point",
        group="flask",
    ),
    "SERVER_SOFTWARE": EnvVar(
        name="SERVER_SOFTWARE",
        default="",
        description="Server software identification (e.g., gunicorn)",
        group="flask",
    ),
    "PATH_PREFIX": EnvVar(
        name="PATH_PREFIX", default="/api", description="API path prefix", group="flask"
    ),
    "SWAGGER_ENABLED": EnvVar(
        name="SWAGGER_ENABLED",
        default=False,
        type=bool,
        description="Enable Swagger API documentation",
        group="flask",
    ),
    "MODE": EnvVar(
        name="MODE", default="api", description="Application mode", group="flask"
    ),
    "ENV": EnvVar(
        name="ENV",
        default="production",
        description="Environment (development/production)",
        group="flask",
    ),
    # Testing Configuration
    "DJANGO_SETTINGS_MODULE": EnvVar(
        name="DJANGO_SETTINGS_MODULE",
        default="api.settings",
        description="Django settings module for testing",
        group="testing",
    ),
    # Minimum Shifu Price
    "MIN_SHIFU_PRICE": EnvVar(
        name="MIN_SHIFU_PRICE",
        default=0.5,
        type=float,
        description="Minimum price of shifu",
        group="shifu",
    ),
    # TTS Configuration
    "MINIMAX_API_KEY": EnvVar(
        name="MINIMAX_API_KEY",
        default="",
        description="Minimax API key for TTS synthesis",
        secret=True,
        group="tts",
    ),
    "MINIMAX_GROUP_ID": EnvVar(
        name="MINIMAX_GROUP_ID",
        default="",
        description="Minimax group ID for API access",
        group="tts",
    ),
    "TTS_MAX_SEGMENT_CHARS": EnvVar(
        name="TTS_MAX_SEGMENT_CHARS",
        default=300,
        type=int,
        description="Maximum characters per TTS segment",
        group="tts",
    ),
    "MINIMAX_TTS_SAMPLE_RATE": EnvVar(
        name="MINIMAX_TTS_SAMPLE_RATE",
        default=24000,
        type=int,
        description="TTS audio sample rate (8000-44100)",
        group="tts",
    ),
    "MINIMAX_TTS_BITRATE": EnvVar(
        name="MINIMAX_TTS_BITRATE",
        default=128000,
        type=int,
        description="TTS audio bitrate (32000-256000)",
        group="tts",
    ),
    # Volcengine TTS Configuration
    # Note: Uses ARK_ACCESS_KEY_ID and ARK_SECRET_ACCESS_KEY for authentication.
    "VOLCENGINE_TTS_SAMPLE_RATE": EnvVar(
        name="VOLCENGINE_TTS_SAMPLE_RATE",
        default=24000,
        type=int,
        description="Volcengine TTS audio sample rate (8000-48000)",
        group="tts",
    ),
    "VOLCENGINE_TTS_BITRATE": EnvVar(
        name="VOLCENGINE_TTS_BITRATE",
        default=128000,
        type=int,
        description="Volcengine TTS audio bitrate",
        group="tts",
    ),
    # Baidu TTS Configuration
    "BAIDU_TTS_API_KEY": EnvVar(
        name="BAIDU_TTS_API_KEY",
        default="",
        description="Baidu TTS API Key",
        secret=True,
        group="tts",
    ),
    "BAIDU_TTS_SECRET_KEY": EnvVar(
        name="BAIDU_TTS_SECRET_KEY",
        default="",
        description="Baidu TTS Secret Key",
        secret=True,
        group="tts",
    ),
    # Aliyun TTS Configuration
    "ALIYUN_TTS_APPKEY": EnvVar(
        name="ALIYUN_TTS_APPKEY",
        default="",
        description="Aliyun TTS Appkey from Intelligent Speech Interaction console",
        secret=True,
        group="tts",
    ),
    "ALIYUN_TTS_TOKEN": EnvVar(
        name="ALIYUN_TTS_TOKEN",
        default="",
        description="Aliyun NLS access token (required for RESTful TTS authentication)",
        secret=True,
        group="tts",
    ),
    "ALIYUN_TTS_REGION": EnvVar(
        name="ALIYUN_TTS_REGION",
        default="shanghai",
        description="Aliyun TTS region (shanghai, beijing, shenzhen)",
        group="tts",
    ),
    "ALIYUN_TTS_SAMPLE_RATE": EnvVar(
        name="ALIYUN_TTS_SAMPLE_RATE",
        default=16000,
        type=int,
        description="Aliyun TTS sample rate (8000, 16000, 24000)",
        group="tts",
    ),
}

# Derived Redis prefixes built from REDIS_KEY_PREFIX
REDIS_KEY_SUFFIXES: Dict[str, str] = {
    "REDIS_KEY_PREFIX_USER": "user:",
    "REDIS_KEY_PREFIX_RESET_PWD": "reset_pwd:",
    "REDIS_KEY_PREFIX_PHONE": "phone:",
    "REDIS_KEY_PREFIX_PHONE_CODE": "phone_code:",
    "REDIS_KEY_PREFIX_MAIL_CODE": "mail_code:",
    "REDIS_KEY_PREFIX_MAIL_LIMIT": "mail_limit:",
    "REDIS_KEY_PREFIX_PHONE_LIMIT": "phone_limit:",
    "REDIS_KEY_PREFIX_IP_BAN": "ip_ban:",
    "REDIS_KEY_PREFIX_IP_LIMIT": "ip_limit:",
}


class EnhancedConfig:
    """Enhanced configuration management with validation and type safety."""

    def __init__(self, env_vars: Dict[str, EnvVar]):
        self.env_vars = env_vars
        self._cache: Dict[str, Any] = {}
        self._validated = False

    def validate_environment(self, allow_conversion_errors: bool = False) -> None:
        """Validate all required environment variables at startup."""
        errors = []
        missing_required = []
        validation_errors = []
        # Check if at least one LLM is configured
        llm_vars = [
            "OPENAI_API_KEY",
            "ERNIE_API_KEY",
            "ERNIE_API_ID",
            "ARK_API_KEY",
            "SILICON_API_KEY",
            "GLM_API_KEY",
            "GEMINI_API_KEY",
            "DEEPSEEK_API_KEY",
            "QWEN_API_KEY",
            "BIGMODEL_API_KEY",
        ]
        has_llm = any(self.get(var) not in (None, "") for var in llm_vars)
        if not has_llm:
            errors.append("At least one LLM API key must be configured")
        for var_name, env_var in self.env_vars.items():
            # Check required variables (those with required=True)
            raw_value = os.environ.get(var_name)
            # Trim whitespace from environment variable values during validation
            if isinstance(raw_value, str):
                raw_value = raw_value.strip()

            if env_var.required and not raw_value:
                missing_required.append(f"- {var_name}: {env_var.description}")
                continue
            # Get value (from environment or default)
            value = raw_value if raw_value else env_var.default
            # Validate value if present
            if value is not None and value != "":
                try:
                    converted_value = env_var.convert_type(value)
                    if not env_var.validate_value(converted_value):
                        validation_errors.append(
                            f"- {var_name}: Invalid value '{value}' - {env_var.description}"
                        )
                except Exception as e:
                    # For optional fields, log and continue; required fields remain fatal
                    if env_var.required or not allow_conversion_errors:
                        validation_errors.append(f"- {var_name}: {str(e)}")
                    else:
                        logging.getLogger(__name__).warning(
                            "Non-fatal config conversion issue for %s: %s",
                            var_name,
                            str(e),
                        )
        if missing_required:
            errors.append(
                "Missing required environment variables (must be set in environment):\n"
                + "\n".join(missing_required)
            )
        if validation_errors:
            errors.append(
                "Invalid environment variable values:\n" + "\n".join(validation_errors)
            )
        if errors:
            raise EnvironmentConfigError("\n\n".join(errors))
        self._validated = True

    def get(self, key: str) -> Any:
        """Get configuration value with type conversion."""
        if key in self._cache:
            return self._cache[key]
        if key in self.env_vars:
            env_var = self.env_vars[key]
            value = os.environ.get(key, env_var.default)
            # Trim whitespace from environment variable values
            if isinstance(value, str):
                value = value.strip()
            if value is None or value == "":
                value = env_var.default
            else:
                try:
                    value = env_var.convert_type(value)
                except Exception as e:
                    # Log warning about type conversion failure
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"Failed to convert environment variable '{key}' with value '{value}' "
                        f"to type {env_var.type.__name__}. Using default value '{env_var.default}'. "
                        f"Error: {str(e)}"
                    )
                    value = env_var.default
            # Apply interpolation
            if isinstance(value, str):
                value = self._interpolate(value)
            self._cache[key] = value
            return value
        # Return None for unknown keys to allow fallback in Config class
        return None

    def get_str(self, key: str) -> str:
        """Get string configuration value."""
        value = self.get(key)
        return str(value) if value is not None else ""

    def get_int(self, key: str) -> int:
        """Get integer configuration value."""
        value = self.get(key)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def get_bool(self, key: str) -> bool:
        """Get boolean configuration value."""
        value = self.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value) if value is not None else False

    def get_float(self, key: str) -> float:
        """Get float configuration value."""
        value = self.get(key)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def get_list(self, key: str) -> List[str]:
        """Get list configuration value (comma-separated)."""
        value = self.get(key)
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return []

    def _interpolate(self, value: str) -> str:
        """Interpolate environment variables in format ${VAR_NAME}."""
        pattern = re.compile(r"\$\{([^}]+)\}")

        def replacer(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))

        return pattern.sub(replacer, value)

    def debug_print(self) -> None:
        """Print all configuration values (excluding secrets) for debugging."""
        print("\n=== Configuration Values ===")
        groups = {}
        for var_name, env_var in self.env_vars.items():
            if env_var.group not in groups:
                groups[env_var.group] = []
            value = self.get(var_name)
            if env_var.secret and value:
                display_value = "[REDACTED]"
            else:
                display_value = str(value)
            groups[env_var.group].append(f"  {var_name}: {display_value}")
        for group, items in sorted(groups.items()):
            print(f"\n[{group.upper()}]")
            for item in sorted(items):
                print(item)
        print("\n" + "=" * 30 + "\n")

    def export_env_example(self) -> str:
        """Export full environment variable definitions as .env.example format."""
        return self.export_env_example_filtered(filter_type="all")

    def export_env_example_filtered(self, filter_type: str = "all") -> str:
        """Export environment variable definitions as .env.example format with filtering.

        Args:
            filter_type: "all" for all variables, "required" for only required variables

        Returns:
            Formatted .env.example content as string
        """

        # Format values for .env output, handling lists as comma-separated strings
        def format_value(env_var: EnvVar, value: Any) -> str:
            if value is None:
                return ""
            if env_var.type is list:
                if isinstance(value, list):
                    return ",".join(str(item) for item in value)
                return str(value)
            return str(value)

        if filter_type == "required":
            header_lines = [
                "# AI-Shifu Environment Configuration - REQUIRED VARIABLES",
                "# These are the bare minimum values that must be set.",
                "# Start from docker/.env.example.full and configure at least one LLM API key.\n",
            ]
        else:
            header_lines = [
                "# AI-Shifu Environment Configuration - COMPLETE SET",
                "# Copy this file to docker/.env (or .env) to boot the Docker stack with sane defaults",
                "# Set at least one LLM API key (e.g., OPENAI_API_KEY) before using in production.\n",
            ]

        lines = header_lines
        groups = {}

        # Filter and group variables
        for var_name, env_var in self.env_vars.items():
            # Apply filter
            if filter_type == "required" and not env_var.required:
                continue

            if env_var.group not in groups:
                groups[env_var.group] = []
            groups[env_var.group].append(env_var)

        # Generate output for each group
        for group, vars in sorted(groups.items()):
            # Skip empty groups
            if not vars:
                continue

            lines.append(f"\n#{'=' * 60}")
            lines.append(f"# {group.replace('_', ' ').title()}")
            lines.append(f"#{'=' * 60}\n")

            for env_var in sorted(vars, key=lambda x: x.name):
                example_value = (
                    env_var.example if env_var.example is not None else env_var.default
                )
                if env_var.description:
                    # Handle multi-line descriptions
                    description_lines = env_var.description.strip().split("\n")
                    for desc_line in description_lines:
                        lines.append(f"# {desc_line.strip()}")

                # Add metadata comments
                metadata = []
                if env_var.required:
                    metadata.append("REQUIRED - must be set")
                elif env_var.default is None:
                    metadata.append("Optional - handled by libraries")
                else:
                    # Avoid leaking secret defaults
                    default_display = ""
                    if not (
                        env_var.secret
                        and env_var.example is None
                        and env_var.default not in (None, "")
                    ):
                        default_display = format_value(env_var, env_var.default)
                    metadata.append(f"Optional - default: {default_display}")

                # Emit metadata on separate lines for readability and testing expectations
                for item in metadata:
                    lines.append(f"# ({item})")
                if env_var.type is not str:
                    lines.append(f"# Type: {env_var.type.__name__}")
                if env_var.validator:
                    lines.append("# (Has validation)")
                if env_var.secret:
                    lines.append("# Secret value")

                # Set the value
                if env_var.required:
                    # Required variables can expose a sample value if provided
                    value = example_value if example_value is not None else ""
                else:
                    value = example_value if example_value is not None else ""
                    if (
                        env_var.secret
                        and env_var.example is None
                        and env_var.default not in (None, "")
                    ):
                        value = ""

                value_str = format_value(env_var, value)
                lines.append(f'{env_var.name}="{value_str}"')
                lines.append("")

        # Add footer
        if filter_type == "required":
            lines.append("\n# ========== END OF REQUIRED VARIABLES ==========")
            lines.append("# Make sure all the above variables are properly configured")
        else:
            lines.append("\n# ========== END OF CONFIGURATION ==========")
            lines.append(
                "# Remember to keep your .env file secure and never commit it to version control"
            )

        return "\n".join(lines)


# Global instance
__INSTANCE__ = None
__ENHANCED_CONFIG__ = EnhancedConfig(ENV_VARS)


class Config(FlaskConfig):
    """Flask configuration wrapper with enhanced environment variable support."""

    def __init__(self, parent: FlaskConfig, app: Flask, defaults: dict = {}):
        global __INSTANCE__
        self.parent = parent
        self.app = app
        self.enhanced = __ENHANCED_CONFIG__
        # Reset shared cache per initialization to avoid cross-app contamination
        self.enhanced._cache.clear()
        self.enhanced._validated = False
        __INSTANCE__ = self
        # Validate environment on initialization
        try:
            self.enhanced.validate_environment(allow_conversion_errors=True)
            app.logger.info("Environment configuration validated successfully")
        except EnvironmentConfigError as e:
            app.logger.error(f"Environment configuration error: {e}")
            raise
        self._populate_redis_prefixes()

    def __getitem__(self, key: Any) -> Any:
        """Get configuration value using enhanced config first, with fallback to parent."""
        return self.get(key)

    def __getattr__(self, key: Any) -> Any:
        """Get configuration attribute using enhanced config first."""
        try:
            return self.enhanced.get(key)
        except EnvironmentConfigError:
            # Fall back to parent on validation errors
            return getattr(self.parent, key)
        except Exception:
            return getattr(self.parent, key)

    def __setitem__(self, key: Any, value: Any) -> None:
        """Set configuration value."""
        self.parent.__setitem__(key, value)
        os.environ[key] = str(value)
        # Clear cache
        if key in self.enhanced._cache:
            del self.enhanced._cache[key]

    def _populate_redis_prefixes(self) -> None:
        """Populate derived Redis key prefixes from the global prefix."""
        base_prefix = self.enhanced.get_str("REDIS_KEY_PREFIX")
        for key, suffix in REDIS_KEY_SUFFIXES.items():
            env_value = os.environ.get(key)
            derived_value = (
                env_value.strip()
                if env_value is not None and env_value.strip()
                else f"{base_prefix}{suffix}"
            )
            self.parent.setdefault(key, derived_value)

    def get(self, key: Any, default: Any = None) -> Any:
        """Get configuration value with fallback to parent and optional default.

        This method maintains compatibility with Flask's Config.get() API.

        Args:
            key: Configuration key to look up
            default: Default value to return if key is not found (default: None)

        Returns:
            The configuration value, or default if not found
        """
        # Try enhanced config first
        try:
            value = self.enhanced.get(key)
            if value is not None:
                return value
        except EnvironmentConfigError:
            # Defer to parent/default when enhanced config refuses
            # Try parent __getitem__ as next priority
            try:
                return self.parent.__getitem__(key)
            except Exception:
                return default

        # Fallback to parent Flask config
        try:
            value = self.parent.get(key, None)
        except Exception:
            value = None
        if value is not None:
            return value

        # Fallback to environment variable as last resort
        env_value = os.environ.get(key)
        if env_value is not None:
            self.app.logger.warning(
                f"Configuration key '{key}' not defined in ENV_VARS registry. "
                f"Falling back to environment variable value. "
                f"Consider adding this to ENV_VARS in config.py for proper type conversion and validation."
            )
            return env_value

        # Return default if nothing found
        return default

    def get_str(self, key: str) -> str:
        """Get string configuration value."""
        return self.enhanced.get_str(key)

    def get_int(self, key: str) -> int:
        """Get integer configuration value."""
        return self.enhanced.get_int(key)

    def get_bool(self, key: str) -> bool:
        """Get boolean configuration value."""
        return self.enhanced.get_bool(key)

    def get_float(self, key: str) -> float:
        """Get float configuration value."""
        return self.enhanced.get_float(key)

    def get_list(self, key: str) -> List[str]:
        """Get list configuration value."""
        return self.enhanced.get_list(key)

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self.parent.__call__(*args, **kwds)

    def setdefault(self, key: Any, default: Any = None) -> Any:
        """Set default value if key doesn't exist.

        This method maintains compatibility with Flask's Config.setdefault() API.
        """
        # Check enhanced config first
        try:
            value = self.enhanced.get(key)
            if value is not None:
                return value
        except EnvironmentConfigError:
            pass

        # Use parent's setdefault for consistency
        return self.parent.setdefault(key, default)


def get_config(key: str, default: Any = None) -> Any:
    """Get configuration value.

    Args:
        key: Configuration key to look up
        default: Default value if key not found or config not initialized

    Returns:
        Configuration value or default
    """
    if __INSTANCE__ is None:
        # Before initialization, try to get from environment directly
        # This is needed for module-level calls like timezone setup
        if key in ENV_VARS:
            env_var = ENV_VARS[key]
            value = os.environ.get(key, env_var.default)
            if value is None:
                return default
            return value
        # For unknown keys, check environment directly
        return os.environ.get(key, default)
    return __INSTANCE__.get(key, default)
