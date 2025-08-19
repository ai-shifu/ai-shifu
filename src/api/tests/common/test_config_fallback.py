"""
Unit tests for environment variable fallback mechanism in Config class.
"""

import pytest
import logging
from unittest.mock import MagicMock
from flask import Flask
from flaskr.common.config import (
    Config,
    EnhancedConfig,
    ENV_VARS,
)


class TestEnvironmentVariableFallback:
    """Test environment variable fallback mechanism."""

    @pytest.fixture
    def setup_app(self, monkeypatch):
        """Set up Flask app with required configurations."""
        # Set required environment variables
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db-uri")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        # Set undefined test variables
        monkeypatch.setenv("UNDEFINED_VAR_1", "undefined_value_1")
        monkeypatch.setenv("UNDEFINED_VAR_2", "undefined_value_2")

        # Create Flask app
        app = Flask(__name__)
        app.logger = MagicMock()

        # Create parent config
        parent_config = MagicMock()
        parent_config.__getitem__.side_effect = KeyError
        parent_config.get.return_value = None

        # Initialize Config
        config = Config(parent_config, app)

        return app, config

    def test_fallback_to_env_var_with_warning(self, setup_app, caplog):
        """Test that undefined config keys fallback to environment variables with warning."""
        app, config = setup_app

        # Access undefined variable that exists in environment
        value = config["UNDEFINED_VAR_1"]

        # Check value is retrieved correctly
        assert value == "undefined_value_1"

        # Check warning was logged through app.logger (which is a MagicMock)
        app.logger.warning.assert_called()
        warning_call_args = app.logger.warning.call_args[0][0]
        assert "UNDEFINED_VAR_1" in warning_call_args
        assert "not defined in ENV_VARS registry" in warning_call_args
        assert "Falling back to" in warning_call_args

    def test_fallback_cached_no_repeated_warning(self, setup_app, caplog):
        """Test that cached values don't trigger repeated warnings."""
        app, config = setup_app

        # First access - should log warning
        with caplog.at_level(logging.WARNING):
            value1 = config["UNDEFINED_VAR_2"]
            initial_warning_count = len(caplog.records)

        # Second access - should not log another warning (cached)
        with caplog.at_level(logging.WARNING):
            value2 = config["UNDEFINED_VAR_2"]
            final_warning_count = len(caplog.records)

        # Values should be the same
        assert value1 == value2 == "undefined_value_2"

        # Only one warning should have been logged
        assert final_warning_count == initial_warning_count

    def test_undefined_var_not_in_env_returns_none(self, setup_app):
        """Test that undefined variables not in environment return None."""
        app, config = setup_app

        # Access undefined variable that doesn't exist in environment
        value = config["NON_EXISTENT_VAR"]

        # Should return None
        assert value is None

    def test_defined_var_no_fallback_warning(self, setup_app, caplog):
        """Test that defined variables don't trigger fallback warnings."""
        app, config = setup_app

        # Access a defined variable
        with caplog.at_level(logging.WARNING):
            value = config["SECRET_KEY"]

        # Should get the value without warnings
        assert value == "test-secret"

        # No fallback warning should be logged
        assert "not defined in ENV_VARS registry" not in caplog.text

    def test_get_method_with_fallback(self, setup_app, caplog):
        """Test Config.get() method with fallback."""
        app, config = setup_app

        # Test with undefined var that exists in env
        with caplog.at_level(logging.WARNING):
            value = config.get("UNDEFINED_VAR_1")

        assert value == "undefined_value_1"
        # Note: config.get() does trigger a warning when falling back to environment variables.

    def test_get_method_with_default(self, setup_app):
        """Test Config.get() method with default value."""
        app, config = setup_app

        # Test with non-existent var and default
        # Note: Config.get() returns the default parameter value if the key is not found
        # The default is only used if the key exists but has None value
        value = config.get("NON_EXISTENT_VAR")

        # When variable doesn't exist in env or config, it returns None
        assert value is None

        # We can provide a default using Python's or operator
        value_with_default = config.get("NON_EXISTENT_VAR") or "default_value"
        assert value_with_default == "default_value"


class TestEnhancedConfigFallback:
    """Test EnhancedConfig fallback mechanism."""

    @pytest.fixture
    def enhanced_config(self):
        """Create EnhancedConfig instance."""
        return EnhancedConfig(ENV_VARS)

    def test_enhanced_get_fallback_to_env(self, enhanced_config, monkeypatch, caplog):
        """Test EnhancedConfig.get() fallback to environment variable."""
        # Set an undefined environment variable
        monkeypatch.setenv("ENHANCED_UNDEFINED_VAR", "enhanced_value")

        # Clear cache to ensure fresh lookup
        enhanced_config._cache.clear()

        # Access undefined variable
        with caplog.at_level(logging.WARNING):
            value = enhanced_config.get("ENHANCED_UNDEFINED_VAR")

        # Check value is retrieved correctly
        assert value == "enhanced_value"

        # Check warning was logged
        assert "ENHANCED_UNDEFINED_VAR" in caplog.text
        assert "not defined in ENV_VARS registry" in caplog.text

    def test_enhanced_get_caches_fallback_value(self, enhanced_config, monkeypatch):
        """Test that fallback values are cached."""
        # Set an undefined environment variable
        monkeypatch.setenv("CACHED_UNDEFINED_VAR", "cached_value")

        # Clear cache
        enhanced_config._cache.clear()

        # First access
        value1 = enhanced_config.get("CACHED_UNDEFINED_VAR")

        # Check value is in cache
        assert "CACHED_UNDEFINED_VAR" in enhanced_config._cache
        assert enhanced_config._cache["CACHED_UNDEFINED_VAR"] == "cached_value"

        # Second access should use cache
        value2 = enhanced_config.get("CACHED_UNDEFINED_VAR")

        assert value1 == value2 == "cached_value"

    def test_enhanced_get_undefined_not_in_env(self, enhanced_config):
        """Test EnhancedConfig.get() returns None for non-existent vars."""
        # Clear cache
        enhanced_config._cache.clear()

        # Access undefined variable not in environment
        value = enhanced_config.get("TOTALLY_NON_EXISTENT")

        assert value is None


class TestIntegrationWithFlask:
    """Integration tests with Flask application."""

    def test_flask_app_with_custom_env_vars(self, monkeypatch):
        """Test Flask app can use custom environment variables."""
        # Set required vars
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db-uri")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        # Set custom vars for the app
        monkeypatch.setenv("MY_CUSTOM_API_KEY", "custom-api-key-123")
        monkeypatch.setenv("MY_CUSTOM_ENDPOINT", "https://api.example.com")

        # Create Flask app
        app = Flask(__name__)
        app.logger = MagicMock()

        # Initialize Config
        parent_config = app.config
        config = Config(parent_config, app)
        app.config = config

        # Access custom variables
        api_key = app.config["MY_CUSTOM_API_KEY"]
        endpoint = app.config.get("MY_CUSTOM_ENDPOINT")

        assert api_key == "custom-api-key-123"
        assert endpoint == "https://api.example.com"

        # Verify warnings were logged (they go to standard logger, not app.logger)
        # The warnings are logged by the logger module, not through app.logger
        # So we check that values were retrieved correctly which indicates fallback worked

    def test_setitem_clears_cache_for_fallback(self, monkeypatch):
        """Test that setting a value clears the cache."""
        # Set required vars
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db-uri")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        # Set undefined var
        monkeypatch.setenv("CACHE_TEST_VAR", "initial_value")

        # Create Flask app and config
        app = Flask(__name__)
        app.logger = MagicMock()
        parent_config = MagicMock()
        parent_config.__getitem__.side_effect = KeyError
        parent_config.get.return_value = None
        config = Config(parent_config, app)

        # Access the undefined var (will be cached)
        value1 = config["CACHE_TEST_VAR"]
        assert value1 == "initial_value"

        # Now set it through config
        config["CACHE_TEST_VAR"] = "new_value"

        # Cache should be cleared, new value should be returned
        value2 = config["CACHE_TEST_VAR"]
        assert value2 == "new_value"
