"""
Test data for configuration tests.
"""

from flaskr.common.config import EnvVar


def port_validator(value):
    """Validate port number is in valid range."""
    try:
        port = int(value)
        return 1 <= port <= 65535
    except (ValueError, TypeError):
        return False


def email_validator(value):
    """Simple email validator for testing."""
    import re

    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, str(value)))


# Minimal valid configuration for testing
MINIMAL_ENV_VARS = {
    "SQLALCHEMY_DATABASE_URI": EnvVar(
        name="SQLALCHEMY_DATABASE_URI",
        required=True,
        description="Test database URI",
        secret=True,
        group="database",
    ),
    "SECRET_KEY": EnvVar(
        name="SECRET_KEY",
        required=True,
        description="Test secret key",
        secret=True,
        group="auth",
    ),
    "UNIVERSAL_VERIFICATION_CODE": EnvVar(
        name="UNIVERSAL_VERIFICATION_CODE",
        required=True,
        description="Universal verification code",
        secret=True,
        group="auth",
    ),
    "OPENAI_API_KEY": EnvVar(
        name="OPENAI_API_KEY",
        default="",
        description="OpenAI API key",
        secret=True,
        group="llm",
    ),
}

# Full test configuration with various types
FULL_TEST_ENV_VARS = {
    # Required variables
    "SQLALCHEMY_DATABASE_URI": EnvVar(
        name="SQLALCHEMY_DATABASE_URI",
        required=True,
        description="MySQL database connection URI",
        secret=True,
        group="database",
    ),
    "SECRET_KEY": EnvVar(
        name="SECRET_KEY",
        required=True,
        description="Secret key for JWT",
        secret=True,
        group="auth",
    ),
    "UNIVERSAL_VERIFICATION_CODE": EnvVar(
        name="UNIVERSAL_VERIFICATION_CODE",
        required=True,
        description="Universal verification code",
        secret=True,
        group="auth",
    ),
    # String with default
    "REDIS_HOST": EnvVar(
        name="REDIS_HOST",
        default="ai-shifu-redis",
        description="Redis server host",
        group="redis",
    ),
    # Integer with default
    "REDIS_PORT": EnvVar(
        name="REDIS_PORT",
        default=6379,
        type=int,
        description="Redis server port",
        group="redis",
        validator=port_validator,
    ),
    # Float with default
    "DEFAULT_LLM_TEMPERATURE": EnvVar(
        name="DEFAULT_LLM_TEMPERATURE",
        default=0.3,
        type=float,
        description="LLM temperature setting",
        group="llm",
        validator=lambda x: 0.0 <= float(x) <= 2.0,
    ),
    # Boolean with default
    "SWAGGER_ENABLED": EnvVar(
        name="SWAGGER_ENABLED",
        default=False,
        type=bool,
        description="Enable Swagger documentation",
        group="flask",
    ),
    # Multi-line description
    "DEFAULT_LLM_MODEL": EnvVar(
        name="DEFAULT_LLM_MODEL",
        default="gpt-3.5-turbo",
        description="""Default LLM model to use.
Supported models:
- OpenAI: gpt-4, gpt-3.5-turbo
- Claude: claude-3-opus""",
        group="llm",
    ),
    # Optional without default (handled by libraries)
    "SERVER_SOFTWARE": EnvVar(
        name="SERVER_SOFTWARE",
        required=False,
        description="Server software (set by runtime)",
        group="flask",
    ),
    # LLM API keys for validation
    "OPENAI_API_KEY": EnvVar(
        name="OPENAI_API_KEY",
        default="",
        description="OpenAI API key",
        secret=True,
        group="llm",
    ),
    "ERNIE_API_KEY": EnvVar(
        name="ERNIE_API_KEY",
        default="",
        description="ERNIE API key",
        secret=True,
        group="llm",
    ),
}

# Invalid configuration examples for error testing
# Note: We don't create the invalid EnvVar directly as it will raise an error
# Instead, we'll create it in the test where we expect the error
INVALID_CONFIGS = [
    {
        "description": "Required with default value",
        "config_params": {
            "name": "INVALID_VAR",
            "required": True,
            "default": "should_fail",  # This should cause ValueError
            "description": "Invalid: required with default",
        },
        "expected_error": ValueError,
    },
]

# Docker environment configuration
DOCKER_ENV_CONFIG = {
    "SQLALCHEMY_DATABASE_URI": "mysql://root:ai-shifu@ai-shifu-mysql:3306/ai-shifu?charset=utf8mb4",
    "SECRET_KEY": "docker-secret-key-123456",
    "UNIVERSAL_VERIFICATION_CODE": "docker-123456",
    "REDIS_HOST": "ai-shifu-redis",
    "REDIS_PORT": "6379",
    "OPENAI_API_KEY": "sk-docker-test-key",
    "DEFAULT_LLM_TEMPERATURE": "0.5",
    "SWAGGER_ENABLED": "true",
}

# Production environment configuration
PRODUCTION_ENV_CONFIG = {
    "SQLALCHEMY_DATABASE_URI": "mysql://prod_user:prod_pass@prod-db:3306/prod_db?charset=utf8mb4",
    "SECRET_KEY": "production-secret-key-very-long-and-secure",
    "UNIVERSAL_VERIFICATION_CODE": "prod-verification-code",
    "REDIS_HOST": "redis.production.internal",
    "REDIS_PORT": "6379",
    "OPENAI_API_KEY": "sk-prod-real-key",
    "DEFAULT_LLM_TEMPERATURE": "0.3",
    "SWAGGER_ENABLED": "false",
}

# Test environment with missing required variables
MISSING_REQUIRED_ENV = {
    "REDIS_HOST": "localhost",
    "REDIS_PORT": "6379",
    # Missing: SQLALCHEMY_DATABASE_URI, SECRET_KEY
}

# Test environment with invalid values
INVALID_VALUES_ENV = {
    "SQLALCHEMY_DATABASE_URI": "mysql://test:test@localhost:3306/test",
    "SECRET_KEY": "test-key",
    "UNIVERSAL_VERIFICATION_CODE": "test-code",
    "REDIS_PORT": "99999",  # Invalid port number
    "DEFAULT_LLM_TEMPERATURE": "5.0",  # Out of range
    "SWAGGER_ENABLED": "maybe",  # Invalid boolean
}

# Test environment with no LLM keys
NO_LLM_ENV = {
    "SQLALCHEMY_DATABASE_URI": "mysql://test:test@localhost:3306/test",
    "SECRET_KEY": "test-key",
    "UNIVERSAL_VERIFICATION_CODE": "test-code",
    "REDIS_HOST": "localhost",
    "REDIS_PORT": "6379",
    # No LLM API keys provided
}
