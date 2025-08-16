import os
import re
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
    default: Any = None  # If None, variable is required
    type: Type = str  # Using Type annotation to avoid conflict
    description: str = ""
    validator: Optional[Callable[[Any], bool]] = None
    secret: bool = False
    group: str = "general"
    depends_on: List[str] = field(default_factory=list)

    def validate_value(self, value: Any) -> bool:
        """Validate the environment variable value."""
        if self.validator:
            return self.validator(value)
        return True

    def convert_type(self, value: Any) -> Any:
        """Convert string value to the specified type."""
        if value is None or value == "":
            return self.default
        # If value is already the correct type, return it
        if isinstance(value, self.type):
            return value
        if self.type == bool:
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)
        elif self.type == int:
            try:
                return int(value)
            except ValueError:
                raise EnvironmentConfigError(
                    f"Invalid integer value for {self.name}: {value}"
                )
        elif self.type == float:
            try:
                return float(value)
            except ValueError:
                raise EnvironmentConfigError(
                    f"Invalid float value for {self.name}: {value}"
                )
        elif self.type == list:
            if isinstance(value, str):
                return [item.strip() for item in value.split(",") if item.strip()]
            return list(value)
        else:
            return str(value)


# Environment variable registry
ENV_VARS: Dict[str, EnvVar] = {
    # Application Configuration
    "WEB_URL": EnvVar(
        name="WEB_URL",
        default="UNCONFIGURED",
        description="Website access domain name",
        group="app",
    ),
    "NEXT_PUBLIC_LOGIN_METHODS_ENABLED": EnvVar(
        name="NEXT_PUBLIC_LOGIN_METHODS_ENABLED",
        default="phone",
        description="Enabled login methods (phone, email, or phone,email)",
        group="app",
    ),
    "NEXT_PUBLIC_DEFAULT_LOGIN_METHOD": EnvVar(
        name="NEXT_PUBLIC_DEFAULT_LOGIN_METHOD",
        default="phone",
        description="Default login method tab",
        group="app",
    ),
    "REACT_APP_ALWAYS_SHOW_LESSON_TREE": EnvVar(
        name="REACT_APP_ALWAYS_SHOW_LESSON_TREE",
        default="true",
        description="Always show lesson tree in UI",
        group="app",
    ),
    "LOGGING_PATH": EnvVar(
        name="LOGGING_PATH",
        default="logs/ai-shifu.log",
        description="Path for log file",
        group="app",
    ),
    "ASK_MAX_HISTORY_LEN": EnvVar(
        name="ASK_MAX_HISTORY_LEN",
        default=10,
        type=int,
        description="Maximum number of history messages in ask context",
        group="app",
    ),
    "SHIFU_PERMISSION_CACHE_EXPIRE": EnvVar(
        name="SHIFU_PERMISSION_CACHE_EXPIRE",
        default="1",
        description="Shifu permission cache expiration time in seconds",
        group="app",
    ),
    "TZ": EnvVar(
        name="TZ",
        default="UTC",
        description="System timezone setting",
        group="app",
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
        default="https://api.openai.com/v1",
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
        description="ByteDance Volcengine Ark Access Key ID",
        secret=True,
        group="llm",
    ),
    "ARK_SECRET_ACCESS_KEY": EnvVar(
        name="ARK_SECRET_ACCESS_KEY",
        default="",
        description="ByteDance Volcengine Ark Secret Access Key",
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
        description="Default LLM model to use",
        group="llm",
    ),
    "DEFAULT_LLM_TEMPERATURE": EnvVar(
        name="DEFAULT_LLM_TEMPERATURE",
        default=0.3,
        type=float,
        description="Default temperature for LLM generation",
        group="llm",
        validator=lambda x: 0.0 <= float(x) <= 2.0,
    ),
    # Knowledge Base
    "DEFAULT_KB_ID": EnvVar(
        name="DEFAULT_KB_ID",
        default="default",
        description="Default knowledge base ID",
        group="knowledge_base",
    ),
    "EMBEDDING_MODEL_BASE_URL": EnvVar(
        name="EMBEDDING_MODEL_BASE_URL",
        default="",
        description="Base URL for embedding model API",
        group="knowledge_base",
    ),
    "EMBEDDING_MODEL_API_KEY": EnvVar(
        name="EMBEDDING_MODEL_API_KEY",
        default="",
        description="API key for embedding model",
        secret=True,
        group="knowledge_base",
    ),
    "DEFAULT_EMBEDDING_MODEL": EnvVar(
        name="DEFAULT_EMBEDDING_MODEL",
        default="BAAI/bge-large-zh-v1.5",
        description="Default embedding model name",
        group="knowledge_base",
    ),
    "DEFAULT_EMBEDDING_MODEL_DIM": EnvVar(
        name="DEFAULT_EMBEDDING_MODEL_DIM",
        default="1024",
        description="Dimension of default embedding model",
        group="knowledge_base",
    ),
    # Database Configuration
    "SQLALCHEMY_DATABASE_URI": EnvVar(
        name="SQLALCHEMY_DATABASE_URI",
        description="MySQL database connection URI",
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
        default="localhost",
        description="Redis server host",
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
    "REDIS_KEY_PREFIX_USER": EnvVar(
        name="REDIS_KEY_PREFIX_USER",
        default="ai-shifu:user:",
        description="Redis key prefix for user data",
        group="redis",
    ),
    "REDIS_KEY_PREFIX_RESET_PWD": EnvVar(
        name="REDIS_KEY_PREFIX_RESET_PWD",
        default="ai-shifu:reset_pwd:",
        description="Redis key prefix for password reset",
        group="redis",
    ),
    "REDIS_KEY_PREFIX_CAPTCHA": EnvVar(
        name="REDIS_KEY_PREFIX_CAPTCHA",
        default="ai-shifu:captcha:",
        description="Redis key prefix for captcha",
        group="redis",
    ),
    "REDIS_KEY_PREFIX_PHONE": EnvVar(
        name="REDIS_KEY_PREFIX_PHONE",
        default="ai-shifu:phone:",
        description="Redis key prefix for phone",
        group="redis",
    ),
    "REDIS_KEY_PREFIX_PHONE_CODE": EnvVar(
        name="REDIS_KEY_PREFIX_PHONE_CODE",
        default="ai-shifu:phone_code:",
        description="Redis key prefix for phone verification code",
        group="redis",
    ),
    "REDIS_KEY_PREFIX_MAIL_CODE": EnvVar(
        name="REDIS_KEY_PREFIX_MAIL_CODE",
        default="ai-shifu:mail_code:",
        description="Redis key prefix for email verification code",
        group="redis",
    ),
    "REDIS_KEY_PREFIX_MAIL_LIMIT": EnvVar(
        name="REDIS_KEY_PREFIX_MAIL_LIMIT",
        default="ai-shifu:mail_limit:",
        description="Redis key prefix for email sending restrictions",
        group="redis",
    ),
    "REDIS_KEY_PREFIX_PHONE_LIMIT": EnvVar(
        name="REDIS_KEY_PREFIX_PHONE_LIMIT",
        default="ai-shifu:phone_limit:",
        description="Redis key prefix for phone SMS restrictions",
        group="redis",
    ),
    "REDIS_KEY_PREFIX_IP_BAN": EnvVar(
        name="REDIS_KEY_PREFIX_IP_BAN",
        default="ai-shifu:ip_ban:",
        description="Redis key prefix for IP ban state",
        group="redis",
    ),
    "REDIS_KEY_PREFIX_IP_LIMIT": EnvVar(
        name="REDIS_KEY_PREFIX_IP_LIMIT",
        default="ai-shifu:ip_limit:",
        description="Redis key prefix for IP rate limiting",
        group="redis",
    ),
    # Authentication Configuration
    "SECRET_KEY": EnvVar(
        name="SECRET_KEY",
        description="Secret key for JWT and session encryption",
        secret=True,
        group="auth",
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
        description="Password reset code expiration time in seconds",
        group="auth",
    ),
    "CAPTCHA_CODE_EXPIRE_TIME": EnvVar(
        name="CAPTCHA_CODE_EXPIRE_TIME",
        default=300,
        type=int,
        description="Captcha expiration time in seconds",
        group="auth",
    ),
    "PHONE_CODE_EXPIRE_TIME": EnvVar(
        name="PHONE_CODE_EXPIRE_TIME",
        default=300,
        type=int,
        description="Phone verification code expiration time in seconds",
        group="auth",
    ),
    "MAIL_CODE_EXPIRE_TIME": EnvVar(
        name="MAIL_CODE_EXPIRE_TIME",
        default=300,
        type=int,
        description="Email verification code expiration time in seconds",
        group="auth",
    ),
    "MAIL_CODE_INTERVAL": EnvVar(
        name="MAIL_CODE_INTERVAL",
        default=60,
        type=int,
        description="Interval time for sending emails in seconds",
        group="auth",
    ),
    "SMS_CODE_INTERVAL": EnvVar(
        name="SMS_CODE_INTERVAL",
        default=60,
        type=int,
        description="Minimum interval for sending SMS to same phone number in seconds",
        group="auth",
    ),
    "IP_MAIL_LIMIT_COUNT": EnvVar(
        name="IP_MAIL_LIMIT_COUNT",
        default=10,
        type=int,
        description="Maximum number of emails allowed per IP",
        group="auth",
    ),
    "IP_MAIL_LIMIT_TIME": EnvVar(
        name="IP_MAIL_LIMIT_TIME",
        default=3600,
        type=int,
        description="Time window for IP email rate limiting in seconds",
        group="auth",
    ),
    "IP_SMS_LIMIT_COUNT": EnvVar(
        name="IP_SMS_LIMIT_COUNT",
        default=10,
        type=int,
        description="Maximum number of SMS allowed per IP",
        group="auth",
    ),
    "IP_SMS_LIMIT_TIME": EnvVar(
        name="IP_SMS_LIMIT_TIME",
        default=3600,
        type=int,
        description="Time window for IP SMS rate limiting in seconds",
        group="auth",
    ),
    "IP_BAN_TIME": EnvVar(
        name="IP_BAN_TIME",
        default=86400,
        type=int,
        description="IP ban duration in seconds",
        group="auth",
    ),
    "UNIVERSAL_VERIFICATION_CODE": EnvVar(
        name="UNIVERSAL_VERIFICATION_CODE",
        description="Universal verification code for testing",
        secret=True,
        group="auth",
    ),
    # Alibaba Cloud Configuration
    "ALIBABA_CLOUD_SMS_ACCESS_KEY_ID": EnvVar(
        name="ALIBABA_CLOUD_SMS_ACCESS_KEY_ID",
        default="",
        description="Alibaba Cloud SMS Access Key ID",
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
        description="Langfuse public key for LLM tracking",
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
    # Frontend Configuration
    "REACT_APP_BASEURL": EnvVar(
        name="REACT_APP_BASEURL",
        default="",
        description="React app base URL",
        group="frontend",
    ),
    "PORT": EnvVar(
        name="PORT",
        default=5000,
        type=int,
        description="Frontend server port",
        group="frontend",
        validator=lambda x: 1 <= int(x) <= 65535,
    ),
    "SITE_HOST": EnvVar(
        name="SITE_HOST",
        default="http://localhost:8081/",
        description="Site host URL",
        group="frontend",
    ),
    "REACT_APP_ENABLE_ERUDA": EnvVar(
        name="REACT_APP_ENABLE_ERUDA",
        default="",
        description="Enable Eruda console for debugging",
        group="frontend",
    ),
    # Testing Configuration
    "DJANGO_SETTINGS_MODULE": EnvVar(
        name="DJANGO_SETTINGS_MODULE",
        default="api.settings",
        description="Django settings module for testing",
        group="testing",
    ),
}


class EnhancedConfig:
    """Enhanced configuration management with validation and type safety."""

    def __init__(self, env_vars: Dict[str, EnvVar]):
        self.env_vars = env_vars
        self._cache: Dict[str, Any] = {}
        self._validated = False

    def validate_environment(self) -> None:
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
            "DEEPSEEK_API_KEY",
            "QWEN_API_KEY",
            "BIGMODEL_API_KEY",
        ]
        has_llm = any(os.environ.get(var, "") != "" for var in llm_vars)
        if not has_llm:
            errors.append("At least one LLM API key must be configured")
        for var_name, env_var in self.env_vars.items():
            # Check required variables (those with no default value)
            if env_var.default is None and var_name not in os.environ:
                missing_required.append(f"- {var_name}: {env_var.description}")
                continue
            # Get value (from environment or default)
            value = os.environ.get(var_name, env_var.default)
            # Validate value if present
            if value is not None and value != "":
                try:
                    converted_value = env_var.convert_type(value)
                    if not env_var.validate_value(converted_value):
                        validation_errors.append(
                            f"- {var_name}: Invalid value '{value}' - {env_var.description}"
                        )
                except Exception as e:
                    validation_errors.append(f"- {var_name}: {str(e)}")
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
            if value is None or value == "":
                value = env_var.default
            else:
                try:
                    value = env_var.convert_type(value)
                except Exception:
                    value = env_var.default
            # Apply interpolation
            if isinstance(value, str):
                value = self._interpolate(value)
            self._cache[key] = value
            return value
        # No fallback - key must be defined in ENV_VARS
        raise EnvironmentConfigError(f"Unknown configuration key: {key}")

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
        """Export environment variable definitions as .env.example format."""
        lines = ["# AI-Shifu Environment Configuration\n"]
        groups = {}
        for var_name, env_var in self.env_vars.items():
            if env_var.group not in groups:
                groups[env_var.group] = []
            groups[env_var.group].append(env_var)
        for group, vars in sorted(groups.items()):
            lines.append(f"\n#{'=' * 20}")
            lines.append(f"# {group.replace('_', ' ').title()}")
            lines.append(f"#{'=' * 20}\n")
            for env_var in sorted(vars, key=lambda x: x.name):
                if env_var.description:
                    lines.append(f"# {env_var.description}")
                if env_var.default is None:
                    lines.append("# (REQUIRED - must be set)")
                if env_var.type != str:
                    lines.append(f"# Type: {env_var.type.__name__}")
                if env_var.validator:
                    lines.append("# (Has validation)")
                default_value = env_var.default if env_var.default is not None else ""
                if env_var.secret and default_value:
                    default_value = ""
                lines.append(f'{env_var.name}="{default_value}"')
                lines.append("")
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
        __INSTANCE__ = self
        # Validate environment on initialization
        try:
            self.enhanced.validate_environment()
            app.logger.info("Environment configuration validated successfully")
        except EnvironmentConfigError as e:
            app.logger.error(f"Environment configuration error: {e}")
            raise

    def __getitem__(self, key: Any) -> Any:
        """Get configuration value using enhanced config first."""
        value = self.enhanced.get(key)
        if value is not None:
            return value
        try:
            return self.parent.__getitem__(key)
        except KeyError:
            # Return None for missing keys instead of raising
            return None

    def __getattr__(self, key: Any) -> Any:
        """Get configuration attribute using enhanced config first."""
        try:
            return self.enhanced.get(key)
        except:
            return self.parent.__getattr__(key)

    def __setitem__(self, key: Any, value: Any) -> None:
        """Set configuration value."""
        self.parent.__setitem__(key, value)
        os.environ[key] = str(value)
        # Clear cache
        if key in self.enhanced._cache:
            del self.enhanced._cache[key]

    def get(self, key: Any) -> Any:
        """Get configuration value."""
        return self.enhanced.get(key)

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
        """Set default value if key doesn't exist."""
        value = self.enhanced.get(key)
        if value is not None:
            return value
        return self.parent.setdefault(key, default)


def get_config(key: str) -> Any:
    """Get configuration value."""
    if __INSTANCE__ is None:
        # If not initialized, raise an error - no backward compatibility
        raise EnvironmentConfigError(
            f"Configuration not initialized. Cannot access {key}"
        )
    return __INSTANCE__.get(key)
