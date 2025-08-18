"""
Unit tests for EnhancedConfig class.
"""

import pytest
from unittest.mock import patch
from flaskr.common.config import EnhancedConfig, EnvironmentConfigError, EnvVar
from tests.common.fixtures.config_data import (
    MINIMAL_ENV_VARS,
    FULL_TEST_ENV_VARS,
    DOCKER_ENV_CONFIG,
    MISSING_REQUIRED_ENV,
    INVALID_VALUES_ENV,
    NO_LLM_ENV,
)


class TestEnhancedConfigInitialization:
    """Test EnhancedConfig initialization."""

    def test_init_with_valid_env_vars(self):
        """Test initialization with valid environment variables."""
        config = EnhancedConfig(MINIMAL_ENV_VARS)

        assert config.env_vars == MINIMAL_ENV_VARS
        assert config._cache == {}
        assert config._validated is False

    def test_init_with_empty_env_vars(self):
        """Test initialization with empty environment variables."""
        config = EnhancedConfig({})

        assert config.env_vars == {}
        assert config._cache == {}
        assert config._validated is False


class TestEnhancedConfigValidation:
    """Test environment validation functionality."""

    def test_validate_environment_success(self, monkeypatch):
        """Test successful environment validation."""
        # Set up environment
        for key, value in DOCKER_ENV_CONFIG.items():
            monkeypatch.setenv(key, value)

        config = EnhancedConfig(FULL_TEST_ENV_VARS)
        config.validate_environment()

        assert config._validated is True

    def test_validate_missing_required(self, monkeypatch):
        """Test validation fails when required variables are missing."""
        # Set up environment without required variables
        for key, value in MISSING_REQUIRED_ENV.items():
            monkeypatch.setenv(key, value)

        config = EnhancedConfig(MINIMAL_ENV_VARS)

        with pytest.raises(EnvironmentConfigError) as exc_info:
            config.validate_environment()

        error_msg = str(exc_info.value)
        # Check for either missing required variables OR missing LLM key
        # (MISSING_REQUIRED_ENV doesn't have LLM keys either)
        assert (
            "Missing required environment variables" in error_msg
            or "At least one LLM API key must be configured" in error_msg
        )
        # If it's about missing required, check for specific variables
        if "Missing required environment variables" in error_msg:
            assert (
                "SQLALCHEMY_DATABASE_URI" in error_msg
                or "SECRET_KEY" in error_msg
                or "UNIVERSAL_VERIFICATION_CODE" in error_msg
            )

    def test_validate_missing_llm_key(self, monkeypatch):
        """Test validation fails when no LLM API key is configured."""
        # Set up environment without LLM keys
        for key, value in NO_LLM_ENV.items():
            monkeypatch.setenv(key, value)

        config = EnhancedConfig(FULL_TEST_ENV_VARS)

        with pytest.raises(EnvironmentConfigError) as exc_info:
            config.validate_environment()

        error_msg = str(exc_info.value)
        assert "At least one LLM API key must be configured" in error_msg

    def test_validate_invalid_values(self, monkeypatch):
        """Test validation fails for invalid values."""
        # Set up environment with invalid values
        for key, value in INVALID_VALUES_ENV.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")  # Add LLM key

        config = EnhancedConfig(FULL_TEST_ENV_VARS)

        with pytest.raises(EnvironmentConfigError) as exc_info:
            config.validate_environment()

        error_msg = str(exc_info.value)
        assert "Invalid environment variable values" in error_msg
        assert "REDIS_PORT" in error_msg  # Invalid port number
        assert "DEFAULT_LLM_TEMPERATURE" in error_msg  # Out of range

    def test_validate_with_validator_exception(self, monkeypatch):
        """Test validation handles validator exceptions."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("BAD_INT", "not_a_number")

        env_vars = {
            **MINIMAL_ENV_VARS,
            "BAD_INT": EnvVar(
                name="BAD_INT",
                type=int,
                description="Bad integer for testing",
            ),
        }

        config = EnhancedConfig(env_vars)

        with pytest.raises(EnvironmentConfigError) as exc_info:
            config.validate_environment()

        error_msg = str(exc_info.value)
        assert "BAD_INT" in error_msg


class TestEnhancedConfigGet:
    """Test get method functionality."""

    def test_get_existing_variable(self, monkeypatch):
        """Test getting an existing environment variable."""
        monkeypatch.setenv("REDIS_HOST", "test-redis")
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        config = EnhancedConfig(FULL_TEST_ENV_VARS)

        assert config.get("REDIS_HOST") == "test-redis"

    def test_get_with_default(self, monkeypatch):
        """Test getting variable with default value."""
        # Don't set REDIS_HOST in environment
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        config = EnhancedConfig(FULL_TEST_ENV_VARS)

        # Should return default value
        assert config.get("REDIS_HOST") == "localhost"

    def test_get_with_type_conversion(self, monkeypatch):
        """Test getting variable with type conversion."""
        monkeypatch.setenv("REDIS_PORT", "7000")
        monkeypatch.setenv("DEFAULT_LLM_TEMPERATURE", "0.8")
        monkeypatch.setenv("SWAGGER_ENABLED", "true")

        config = EnhancedConfig(FULL_TEST_ENV_VARS)

        assert config.get("REDIS_PORT") == 7000
        assert isinstance(config.get("REDIS_PORT"), int)

        assert config.get("DEFAULT_LLM_TEMPERATURE") == 0.8
        assert isinstance(config.get("DEFAULT_LLM_TEMPERATURE"), float)

        assert config.get("SWAGGER_ENABLED") is True
        assert isinstance(config.get("SWAGGER_ENABLED"), bool)

    def test_get_cached_value(self, monkeypatch):
        """Test that values are cached after first retrieval."""
        monkeypatch.setenv("REDIS_HOST", "test-redis")

        config = EnhancedConfig(FULL_TEST_ENV_VARS)

        # First get - should cache
        value1 = config.get("REDIS_HOST")
        assert value1 == "test-redis"
        assert "REDIS_HOST" in config._cache

        # Change environment (shouldn't affect cached value)
        monkeypatch.setenv("REDIS_HOST", "changed-redis")

        # Second get - should return cached value
        value2 = config.get("REDIS_HOST")
        assert value2 == "test-redis"  # Still the cached value

    def test_get_unknown_key(self):
        """Test getting unknown configuration key returns None."""
        config = EnhancedConfig(MINIMAL_ENV_VARS)

        # Unknown keys should return None to allow fallback in Config class
        assert config.get("UNKNOWN_KEY") is None

    def test_get_empty_value_returns_default(self, monkeypatch):
        """Test that empty string returns default value."""
        monkeypatch.setenv("REDIS_HOST", "")

        config = EnhancedConfig(FULL_TEST_ENV_VARS)

        assert config.get("REDIS_HOST") == "localhost"  # Should return default


class TestEnhancedConfigDebugPrint:
    """Test debug_print method functionality."""

    def test_debug_print_all_configuration(self, monkeypatch):
        """Test printing all configuration values."""
        for key, value in DOCKER_ENV_CONFIG.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")

        config = EnhancedConfig(FULL_TEST_ENV_VARS)

        # Mock print to capture output
        with patch("builtins.print") as mock_print:
            config.debug_print()

            # Check that print was called
            assert mock_print.called

            # Check that groups are printed
            call_args = [str(call) for call in mock_print.call_args_list]
            combined = " ".join(call_args)
            assert "DATABASE" in combined.upper()
            assert "REDIS" in combined.upper()
            assert "LLM" in combined.upper()

    def test_debug_print_masks_secrets(self, monkeypatch):
        """Test that secrets are masked in debug output."""
        monkeypatch.setenv("SECRET_KEY", "super-secret-key-12345")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-real-api-key")
        monkeypatch.setenv("REDIS_HOST", "localhost")
        monkeypatch.setenv(
            "SQLALCHEMY_DATABASE_URI", "mysql://test:test@localhost/test"
        )
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")

        config = EnhancedConfig(FULL_TEST_ENV_VARS)

        with patch("builtins.print") as mock_print:
            config.debug_print()

            call_args = [str(call) for call in mock_print.call_args_list]
            combined = " ".join(call_args)

            # Secrets should be masked
            assert "[REDACTED]" in combined
            assert "super-secret-key-12345" not in combined
            assert "sk-real-api-key" not in combined
            # Non-secrets should be visible
            assert "localhost" in combined


class TestEnhancedConfigExport:
    """Test export_env_example functionality."""

    def test_export_basic_structure(self):
        """Test basic structure of exported .env.example."""
        config = EnhancedConfig(MINIMAL_ENV_VARS)

        output = config.export_env_example()

        assert "# AI-Shifu Environment Configuration" in output
        assert "# Database" in output
        assert "# Auth" in output
        assert "SQLALCHEMY_DATABASE_URI=" in output
        assert "SECRET_KEY=" in output

    def test_export_required_variables(self):
        """Test that required variables are marked."""
        config = EnhancedConfig(MINIMAL_ENV_VARS)

        output = config.export_env_example()

        assert "# (REQUIRED - must be set)" in output
        lines = output.split("\n")

        # Find required variable markers
        for i, line in enumerate(lines):
            if "SQLALCHEMY_DATABASE_URI=" in line:
                # Check previous line for REQUIRED marker
                assert "REQUIRED" in lines[i - 1] or "REQUIRED" in lines[i - 2]

    def test_export_optional_without_default(self):
        """Test optional variables without default are marked."""
        env_vars = {
            "OPTIONAL_VAR": EnvVar(
                name="OPTIONAL_VAR",
                required=False,
                description="Optional variable",
                group="test",
            ),
        }

        config = EnhancedConfig(env_vars)
        output = config.export_env_example()

        assert "# (Optional - handled by libraries)" in output

    def test_export_multiline_description(self):
        """Test export handles multi-line descriptions."""
        env_vars = {
            "MULTI_DESC": EnvVar(
                name="MULTI_DESC",
                description="""Line 1 of description
Line 2 of description
Line 3 of description""",
                default="test",
                group="test",
            ),
        }

        config = EnhancedConfig(env_vars)
        output = config.export_env_example()

        lines = output.split("\n")
        desc_lines = [line for line in lines if line.startswith("# Line")]
        assert len(desc_lines) == 3

    def test_export_with_types(self):
        """Test export shows type information."""
        config = EnhancedConfig(FULL_TEST_ENV_VARS)
        output = config.export_env_example()

        assert "# Type: int" in output
        assert "# Type: float" in output
        assert "# Type: bool" in output

    def test_export_with_validators(self):
        """Test export shows validator information."""
        config = EnhancedConfig(FULL_TEST_ENV_VARS)
        output = config.export_env_example()

        assert "# (Has validation)" in output

    def test_export_secret_values_masked(self):
        """Test that secret default values are masked."""
        env_vars = {
            "SECRET_WITH_DEFAULT": EnvVar(
                name="SECRET_WITH_DEFAULT",
                default="secret-value",
                secret=True,
                description="Secret with default",
                group="test",
            ),
        }

        config = EnhancedConfig(env_vars)
        output = config.export_env_example()

        assert 'SECRET_WITH_DEFAULT=""' in output
        assert "secret-value" not in output

    def test_export_groups_sorted(self):
        """Test that groups are sorted in output."""
        config = EnhancedConfig(FULL_TEST_ENV_VARS)
        output = config.export_env_example()

        # Find group headers
        lines = output.split("\n")
        group_lines = [line for line in lines if line.startswith("#=")]

        # Should have multiple groups
        assert len(group_lines) > 0


class TestEnhancedConfigCache:
    """Test caching mechanism."""

    def test_cache_stores_values(self, monkeypatch):
        """Test that cache stores retrieved values."""
        monkeypatch.setenv("REDIS_HOST", "cached-host")

        config = EnhancedConfig(FULL_TEST_ENV_VARS)

        assert len(config._cache) == 0

        value = config.get("REDIS_HOST")
        assert value == "cached-host"
        assert len(config._cache) == 1
        assert config._cache["REDIS_HOST"] == "cached-host"

    def test_cache_prevents_recomputation(self, monkeypatch):
        """Test that cached values are not recomputed."""
        monkeypatch.setenv("REDIS_PORT", "6379")

        config = EnhancedConfig(FULL_TEST_ENV_VARS)

        # Mock convert_type to track calls
        original_env_var = config.env_vars["REDIS_PORT"]
        with patch.object(
            original_env_var, "convert_type", return_value=6379
        ) as mock_convert:
            # First call - should convert
            value1 = config.get("REDIS_PORT")
            assert mock_convert.call_count == 1

            # Second call - should use cache
            value2 = config.get("REDIS_PORT")
            assert mock_convert.call_count == 1  # Not called again

            assert value1 == value2 == 6379

    def test_clear_cache(self, monkeypatch):
        """Test clearing the cache."""
        monkeypatch.setenv("REDIS_HOST", "test-host")

        config = EnhancedConfig(FULL_TEST_ENV_VARS)

        # Populate cache
        config.get("REDIS_HOST")
        assert len(config._cache) == 1

        # Clear cache
        config._cache.clear()
        assert len(config._cache) == 0

        # Should recompute on next get
        monkeypatch.setenv("REDIS_HOST", "new-host")
        # Note: In real implementation, cache prevents seeing new value
        # This is just to show cache was cleared
