"""
Unit tests for SECRET_KEY validator functionality.
"""

import pytest
from flaskr.common.config import (
    EnhancedConfig,
    EnvVar,
    EnvironmentConfigError,
    ENV_VARS,
)


class TestSecretKeyValidator:
    """Test SECRET_KEY validation functionality."""

    def test_secret_key_valid_values(self):
        """Test that valid SECRET_KEY values pass validation."""
        # Get the actual SECRET_KEY EnvVar from ENV_VARS
        secret_key_env = ENV_VARS["SECRET_KEY"]

        valid_values = [
            "valid_secret_key_123",
            "a",  # Single character is valid
            "  valid_with_spaces  ",  # Valid with surrounding spaces
            "super-secret-key-with-special-chars!@#$%",
            "x" * 100,  # Long key
            "12345678901234567890123456789012",  # 32 characters (recommended minimum)
        ]

        for value in valid_values:
            assert (
                secret_key_env.validator(value) is True
            ), f"Failed for value: {repr(value)}"

    def test_secret_key_invalid_values(self):
        """Test that invalid SECRET_KEY values fail validation."""
        # Get the actual SECRET_KEY EnvVar from ENV_VARS
        secret_key_env = ENV_VARS["SECRET_KEY"]

        invalid_values = [
            "",  # Empty string
            "   ",  # Only spaces
            "\t",  # Only tab
            "\n",  # Only newline
            "\t\n ",  # Mixed whitespace
            None,  # None value
        ]

        for value in invalid_values:
            assert (
                secret_key_env.validator(value) is False
            ), f"Should have failed for value: {repr(value)}"

    def test_secret_key_required_field(self):
        """Test that SECRET_KEY is marked as required."""
        secret_key_env = ENV_VARS["SECRET_KEY"]
        assert secret_key_env.required is True

    def test_secret_key_is_secret(self):
        """Test that SECRET_KEY is marked as secret."""
        secret_key_env = ENV_VARS["SECRET_KEY"]
        assert secret_key_env.secret is True

    def test_environment_validation_with_empty_secret_key(self, monkeypatch):
        """Test that environment validation fails with empty SECRET_KEY."""
        # Set required environment variables
        monkeypatch.setenv(
            "SQLALCHEMY_DATABASE_URI", "mysql://test:test@localhost/test"
        )
        monkeypatch.setenv("SECRET_KEY", "")  # Empty SECRET_KEY
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        config = EnhancedConfig(ENV_VARS)

        with pytest.raises(EnvironmentConfigError) as exc_info:
            config.validate_environment()

        error_msg = str(exc_info.value)
        # Should fail because validator returns False for empty string
        assert (
            "Invalid environment variable values" in error_msg
            or "Missing required environment variables" in error_msg
        )
        assert "SECRET_KEY" in error_msg

    def test_environment_validation_with_whitespace_secret_key(self, monkeypatch):
        """Test that environment validation fails with whitespace-only SECRET_KEY."""
        # Set required environment variables
        monkeypatch.setenv(
            "SQLALCHEMY_DATABASE_URI", "mysql://test:test@localhost/test"
        )
        monkeypatch.setenv("SECRET_KEY", "   ")  # Whitespace-only SECRET_KEY
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        config = EnhancedConfig(ENV_VARS)

        with pytest.raises(EnvironmentConfigError) as exc_info:
            config.validate_environment()

        error_msg = str(exc_info.value)
        # After trimming, it becomes empty and should fail required check
        assert "Missing required environment variables" in error_msg
        assert "SECRET_KEY" in error_msg

    def test_environment_validation_with_valid_secret_key(self, monkeypatch):
        """Test that environment validation passes with valid SECRET_KEY."""
        # Set required environment variables
        monkeypatch.setenv(
            "SQLALCHEMY_DATABASE_URI", "mysql://test:test@localhost/test"
        )
        monkeypatch.setenv("SECRET_KEY", "valid-secret-key-12345")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        config = EnhancedConfig(ENV_VARS)

        # Should not raise any exception
        config.validate_environment()
        assert config._validated is True

    def test_secret_key_with_special_characters(self, monkeypatch):
        """Test that SECRET_KEY with special characters works correctly."""
        # Set required environment variables
        monkeypatch.setenv(
            "SQLALCHEMY_DATABASE_URI", "mysql://test:test@localhost/test"
        )
        monkeypatch.setenv("SECRET_KEY", "!@#$%^&*()_+-=[]{}|;:,.<>?/~`")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        config = EnhancedConfig(ENV_VARS)

        # Should validate successfully
        config.validate_environment()

        # Should get the correct value
        secret_value = config.get("SECRET_KEY")
        assert secret_value == "!@#$%^&*()_+-=[]{}|;:,.<>?/~`"

    def test_secret_key_trimming_during_get(self, monkeypatch):
        """Test that SECRET_KEY is trimmed during get operation."""
        # Set SECRET_KEY with surrounding whitespace
        monkeypatch.setenv("SECRET_KEY", "  secret_with_spaces  ")
        monkeypatch.setenv(
            "SQLALCHEMY_DATABASE_URI", "mysql://test:test@localhost/test"
        )
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        config = EnhancedConfig(ENV_VARS)

        # Get the value
        secret_value = config.get("SECRET_KEY")

        # Should be trimmed
        assert secret_value == "secret_with_spaces"
        assert secret_value != "  secret_with_spaces  "

    def test_custom_secret_key_validator(self):
        """Test creating a custom EnvVar with SECRET_KEY-like validator."""
        custom_env_vars = {
            "CUSTOM_SECRET": EnvVar(
                name="CUSTOM_SECRET",
                required=True,
                secret=True,
                description="Custom secret key",
                group="auth",
                validator=lambda value: bool(value and str(value).strip()),
            )
        }

        custom_secret = custom_env_vars["CUSTOM_SECRET"]

        # Test validator behavior
        assert custom_secret.validator("valid") is True
        assert custom_secret.validator("") is False
        assert custom_secret.validator("   ") is False
        assert custom_secret.validator(None) is False
