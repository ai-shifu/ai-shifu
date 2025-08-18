"""
Integration tests for the complete configuration system.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from flask import Flask
from flaskr.common.config import (
    Config,
    EnhancedConfig,
    EnvVar,
    ENV_VARS,
    EnvironmentConfigError,
    get_config,
)
from tests.common.fixtures.config_data import (
    DOCKER_ENV_CONFIG,
    PRODUCTION_ENV_CONFIG,
)


class TestFullConfigurationFlow:
    """Test complete configuration flow from environment to Flask."""

    def test_complete_initialization_flow(self, monkeypatch):
        """Test complete initialization from environment variables to Flask app."""
        # Set up production-like environment
        for key, value in PRODUCTION_ENV_CONFIG.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "prod-code")

        # Create Flask app
        app = Flask(__name__)

        # Initialize configuration
        config = Config(app.config, app)

        # Replace Flask config with our enhanced config
        app.config = config

        # Verify all layers work correctly
        # 1. Direct access
        assert (
            config["SQLALCHEMY_DATABASE_URI"]
            == PRODUCTION_ENV_CONFIG["SQLALCHEMY_DATABASE_URI"]
        )

        # 2. Typed access
        assert config.get_int("REDIS_PORT") == 6379
        assert config.get_bool("SWAGGER_ENABLED") is False
        assert config.get_float("DEFAULT_LLM_TEMPERATURE") == 0.3

        # 3. Flask app access
        assert app.config["SECRET_KEY"] == PRODUCTION_ENV_CONFIG["SECRET_KEY"]

        # 4. Global function access
        assert get_config("REDIS_HOST") == "redis.production.internal"

    def test_docker_environment_setup(self, monkeypatch):
        """Test configuration with Docker environment."""
        # Set up Docker environment
        for key, value in DOCKER_ENV_CONFIG.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "docker-code")

        app = Flask(__name__)
        config = Config(app.config, app)
        app.config = config

        # Verify Docker-specific settings
        assert "ai-shifu-mysql" in config["SQLALCHEMY_DATABASE_URI"]
        assert config["REDIS_HOST"] == "ai-shifu-redis"
        assert (
            config.get_bool("SWAGGER_ENABLED") is True
        )  # Usually enabled in Docker dev


class TestEnvironmentVariableInterpolation:
    """Test environment variable interpolation in configuration."""

    def test_interpolation_in_config_values(self, monkeypatch):
        """Test that ${VAR} patterns are interpolated."""
        # Set up base variables
        monkeypatch.setenv("DB_HOST", "test-db-host")
        monkeypatch.setenv("DB_USER", "test-user")
        monkeypatch.setenv("DB_PASS", "test-pass")

        # Set interpolated value
        monkeypatch.setenv(
            "SQLALCHEMY_DATABASE_URI",
            "mysql://${DB_USER}:${DB_PASS}@${DB_HOST}:3306/test?charset=utf8mb4",
        )
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        app = Flask(__name__)
        config = Config(app.config, app)

        # Should interpolate variables
        db_uri = config["SQLALCHEMY_DATABASE_URI"]
        assert "test-user:test-pass@test-db-host" in db_uri
        assert "${" not in db_uri  # No uninterpolated variables

    def test_missing_interpolation_variable(self, monkeypatch):
        """Test behavior when interpolated variable is missing."""
        # Set value with missing variable
        monkeypatch.setenv(
            "SQLALCHEMY_DATABASE_URI", "mysql://user:pass@${MISSING_HOST}:3306/test"
        )
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        app = Flask(__name__)
        config = Config(app.config, app)

        # Should keep original placeholder if variable not found
        db_uri = config["SQLALCHEMY_DATABASE_URI"]
        assert "${MISSING_HOST}" in db_uri


class TestConfigurationValidation:
    """Test configuration validation scenarios."""

    def test_missing_all_llm_keys_fails(self, monkeypatch):
        """Test that missing all LLM API keys fails validation."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        # Don't set any LLM keys

        app = Flask(__name__)
        app.logger = MagicMock()

        with pytest.raises(EnvironmentConfigError) as exc_info:
            Config(app.config, app)

        assert "At least one LLM API key must be configured" in str(exc_info.value)

    def test_at_least_one_llm_key_succeeds(self, monkeypatch):
        """Test that having at least one LLM key succeeds."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")

        # Test with different LLM keys
        llm_keys = [
            "OPENAI_API_KEY",
            "ERNIE_API_KEY",
            "ARK_API_KEY",
            "SILICON_API_KEY",
            "GLM_API_KEY",
            "DEEPSEEK_API_KEY",
            "QWEN_API_KEY",
            "BIGMODEL_API_KEY",
        ]

        app = Flask(__name__)
        app.logger = MagicMock()

        for llm_key in llm_keys:
            # Clear all LLM keys
            for key in llm_keys:
                monkeypatch.delenv(key, raising=False)

            # Set only one LLM key
            monkeypatch.setenv(llm_key, f"test-{llm_key.lower()}")

            # Should succeed with just this one key
            config = Config(app.config, app)
            assert config is not None

    def test_invalid_type_conversion_uses_default(self, monkeypatch):
        """Test that invalid type conversion falls back to default."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("REDIS_PORT", "invalid-port")  # Invalid integer

        app = Flask(__name__)
        config = Config(app.config, app)

        # Should use default value when conversion fails
        assert config.get_int("REDIS_PORT") == 6379  # Default value


class TestConfigurationExport:
    """Test configuration export functionality."""

    def test_export_env_example_file(self):
        """Test exporting configuration as .env.example."""
        enhanced_config = EnhancedConfig(ENV_VARS)

        # Export configuration
        output = enhanced_config.export_env_example()

        # Verify structure
        assert "# AI-Shifu Environment Configuration" in output
        assert "SQLALCHEMY_DATABASE_URI=" in output
        assert "SECRET_KEY=" in output
        assert "# (REQUIRED - must be set)" in output

        # Verify multi-line descriptions are formatted correctly
        lines = output.split("\n")
        for i, line in enumerate(lines):
            if "DEFAULT_LLM_MODEL=" in line:
                # Check that multi-line description appears before
                assert any(
                    "Supported models:" in lines[j] for j in range(max(0, i - 10), i)
                )

    def test_export_groups_secrets(self):
        """Test that export properly handles secret values."""
        enhanced_config = EnhancedConfig(ENV_VARS)

        output = enhanced_config.export_env_example()

        # Secret values should be empty in export
        lines = output.split("\n")
        for line in lines:
            if "SECRET_KEY=" in line:
                assert line == 'SECRET_KEY=""'
            elif "OPENAI_API_KEY=" in line:
                assert line == 'OPENAI_API_KEY=""'


class TestConfigurationCaching:
    """Test configuration caching behavior."""

    def test_cache_improves_performance(self, monkeypatch):
        """Test that caching improves performance."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("REDIS_PORT", "6379")

        app = Flask(__name__)
        config = Config(app.config, app)

        # Clear cache
        config.enhanced._cache.clear()

        # First access - will perform type conversion
        with patch.object(
            ENV_VARS["REDIS_PORT"], "convert_type", return_value=6379
        ) as mock_convert:
            value1 = config["REDIS_PORT"]
            assert mock_convert.call_count == 1

            # Second access - should use cache
            value2 = config["REDIS_PORT"]
            assert mock_convert.call_count == 1  # Not called again

            assert value1 == value2 == 6379

    def test_cache_cleared_on_update(self, monkeypatch):
        """Test that cache is cleared when values are updated."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("REDIS_HOST", "original")

        app = Flask(__name__)
        config = Config(app.config, app)

        # Access to populate cache
        value1 = config["REDIS_HOST"]
        assert value1 == "original"
        assert "REDIS_HOST" in config.enhanced._cache

        # Update value
        config["REDIS_HOST"] = "updated"

        # Cache should be cleared
        assert "REDIS_HOST" not in config.enhanced._cache

        # Next access should get new value from environment
        assert os.environ["REDIS_HOST"] == "updated"


class TestMultiEnvironmentSupport:
    """Test support for multiple environments."""

    def test_switch_between_environments(self, monkeypatch):
        """Test switching between different environment configurations."""
        app = Flask(__name__)
        app.logger = MagicMock()

        # Start with Docker environment
        for key, value in DOCKER_ENV_CONFIG.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "docker-code")

        config1 = Config(app.config, app)
        assert "ai-shifu-mysql" in config1["SQLALCHEMY_DATABASE_URI"]

        # Clear instance for new environment
        import flaskr.common.config as config_module

        config_module.__INSTANCE__ = None

        # Switch to production environment
        for key, value in PRODUCTION_ENV_CONFIG.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "prod-code")

        # Clear cache to pick up new values
        config_module.__ENHANCED_CONFIG__._cache.clear()
        config_module.__ENHANCED_CONFIG__._validated = False

        config2 = Config(app.config, app)
        assert "prod-db" in config2["SQLALCHEMY_DATABASE_URI"]


class TestErrorHandling:
    """Test error handling in configuration system."""

    def test_detailed_error_messages(self, monkeypatch):
        """Test that error messages are detailed and helpful."""
        # Missing required variables
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        app = Flask(__name__)
        app.logger = MagicMock()

        with pytest.raises(EnvironmentConfigError) as exc_info:
            Config(app.config, app)

        error_msg = str(exc_info.value)
        # Should list all missing required variables
        assert "SQLALCHEMY_DATABASE_URI" in error_msg
        assert "SECRET_KEY" in error_msg
        assert "UNIVERSAL_VERIFICATION_CODE" in error_msg
        # Should include descriptions
        assert "database" in error_msg.lower() or "MySQL" in error_msg

    def test_validation_error_details(self, monkeypatch):
        """Test that validation errors provide details."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("REDIS_PORT", "99999")  # Invalid port
        monkeypatch.setenv("DEFAULT_LLM_TEMPERATURE", "5.0")  # Out of range

        app = Flask(__name__)
        app.logger = MagicMock()

        with pytest.raises(EnvironmentConfigError) as exc_info:
            Config(app.config, app)

        error_msg = str(exc_info.value)
        assert "Invalid environment variable values" in error_msg
        assert "REDIS_PORT" in error_msg
        assert "DEFAULT_LLM_TEMPERATURE" in error_msg


class TestBackwardCompatibility:
    """Test that backward compatibility is properly removed."""

    def test_no_direct_environ_access(self, monkeypatch):
        """Test that get_config supports direct os.environ access when not initialized."""
        # Clear global instance to test uninitialized state
        import flaskr.common.config as config_module

        original_instance = config_module.__INSTANCE__
        config_module.__INSTANCE__ = None

        try:
            # Test with a known ENV_VAR key - should get from environment or default
            monkeypatch.setenv("REDIS_HOST", "env-redis-host")
            value = get_config("REDIS_HOST")
            assert value == "env-redis-host"

            # Test with unknown key in environment - should get from environment
            monkeypatch.setenv("CUSTOM_KEY", "custom-value")
            value = get_config("CUSTOM_KEY")
            assert value == "custom-value"

            # Test with unknown key not in environment - should return default
            value = get_config("UNKNOWN_KEY", "default-value")
            assert value == "default-value"

            # Test with known ENV_VAR key not in environment - should return default from ENV_VARS
            monkeypatch.delenv("REDIS_HOST", raising=False)
            value = get_config("REDIS_HOST")
            assert value == "localhost"  # Default value from ENV_VARS
        finally:
            config_module.__INSTANCE__ = original_instance

    def test_required_means_no_default(self):
        """Test that required=True prevents having defaults."""
        with pytest.raises(ValueError) as exc_info:
            EnvVar(name="TEST", required=True, default="should-fail")

        assert "marked as required" in str(exc_info.value)
        assert "has a default value" in str(exc_info.value)
