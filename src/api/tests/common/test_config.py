"""
Unit tests for Config class (Flask integration).
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from flask import Flask
from flaskr.common.config import (
    Config,
    EnvironmentConfigError,
    get_config,
    __ENHANCED_CONFIG__,
)
from tests.common.fixtures.config_data import DOCKER_ENV_CONFIG


class TestConfigInitialization:
    """Test Config class initialization."""

    def test_init_with_valid_flask_app(self, monkeypatch):
        """Test initialization with valid Flask app."""
        # Set up required environment variables
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db-uri")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        # Create Flask app
        app = Flask(__name__)
        app.logger = MagicMock()

        # Create parent config
        parent_config = MagicMock()

        # Initialize Config
        config = Config(parent_config, app)

        assert config.parent == parent_config
        assert config.app == app
        assert config.enhanced == __ENHANCED_CONFIG__

        # Verify logger was called
        app.logger.info.assert_called_with(
            "Environment configuration validated successfully"
        )

    def test_init_with_missing_required_vars(self, monkeypatch):
        """Test initialization fails with missing required variables."""
        # Don't set required variables
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URI", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)

        app = Flask(__name__)
        app.logger = MagicMock()
        parent_config = MagicMock()

        with pytest.raises(EnvironmentConfigError):
            Config(parent_config, app)

        # Verify error was logged
        app.logger.error.assert_called()

    def test_global_instance_set(self, monkeypatch):
        """Test that global instance is set on initialization."""
        # Set up environment
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        app = Flask(__name__)
        app.logger = MagicMock()
        parent_config = MagicMock()

        # Clear global instance
        import flaskr.common.config as config_module

        config_module.__INSTANCE__ = None

        config = Config(parent_config, app)

        # Check global instance is set
        assert config_module.__INSTANCE__ == config


class TestConfigGetItem:
    """Test __getitem__ functionality."""

    def test_getitem_from_enhanced_config(self, monkeypatch):
        """Test getting value from enhanced config."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("REDIS_HOST", "test-redis")

        app = Flask(__name__)
        app.logger = MagicMock()
        parent_config = MagicMock()

        config = Config(parent_config, app)

        # Should get from enhanced config
        assert config["REDIS_HOST"] == "test-redis"

    def test_getitem_fallback_to_parent(self, monkeypatch):
        """Test falling back to parent config for unknown keys."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        app = Flask(__name__)
        app.logger = MagicMock()
        parent_config = MagicMock()
        parent_config.__getitem__.return_value = "parent-value"

        config = Config(parent_config, app)

        # Try to get unknown key (not in ENV_VARS)
        with patch.object(
            config.enhanced, "get", side_effect=EnvironmentConfigError("Unknown")
        ):
            value = config["UNKNOWN_KEY"]
            assert value == "parent-value"
            parent_config.__getitem__.assert_called_with("UNKNOWN_KEY")

    def test_getitem_returns_none_for_missing(self, monkeypatch):
        """Test returning None for missing keys."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        app = Flask(__name__)
        app.logger = MagicMock()
        parent_config = MagicMock()
        parent_config.__getitem__.side_effect = KeyError("not found")

        config = Config(parent_config, app)

        # Should return None instead of raising KeyError
        with patch.object(
            config.enhanced, "get", side_effect=EnvironmentConfigError("Unknown")
        ):
            value = config["MISSING_KEY"]
            assert value is None


class TestConfigSetItem:
    """Test __setitem__ functionality."""

    def test_setitem_updates_parent_and_environ(self, monkeypatch):
        """Test setting value updates parent config and environment."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        app = Flask(__name__)
        app.logger = MagicMock()
        parent_config = MagicMock()

        config = Config(parent_config, app)

        # Set a new value
        config["NEW_VALUE"] = "test-value"

        # Should update parent
        parent_config.__setitem__.assert_called_with("NEW_VALUE", "test-value")

        # Should update environment
        assert os.environ["NEW_VALUE"] == "test-value"

    def test_setitem_clears_cache(self, monkeypatch):
        """Test setting value clears the cache."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("REDIS_HOST", "original-host")

        app = Flask(__name__)
        app.logger = MagicMock()
        parent_config = MagicMock()

        config = Config(parent_config, app)

        # Get value to populate cache
        _ = config["REDIS_HOST"]
        assert "REDIS_HOST" in config.enhanced._cache

        # Update value
        config["REDIS_HOST"] = "new-host"

        # Cache should be cleared
        assert "REDIS_HOST" not in config.enhanced._cache


class TestConfigGetMethods:
    """Test typed get methods."""

    def test_get_str(self, monkeypatch):
        """Test get_str method."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("REDIS_HOST", "test-redis")

        app = Flask(__name__)
        app.logger = MagicMock()
        config = Config(MagicMock(), app)

        assert config.get_str("REDIS_HOST") == "test-redis"
        assert isinstance(config.get_str("REDIS_HOST"), str)

    def test_get_int(self, monkeypatch):
        """Test get_int method."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("REDIS_PORT", "7000")

        app = Flask(__name__)
        app.logger = MagicMock()
        config = Config(MagicMock(), app)

        assert config.get_int("REDIS_PORT") == 7000
        assert isinstance(config.get_int("REDIS_PORT"), int)

    def test_get_bool(self, monkeypatch):
        """Test get_bool method."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("SWAGGER_ENABLED", "true")

        app = Flask(__name__)
        app.logger = MagicMock()
        config = Config(MagicMock(), app)

        assert config.get_bool("SWAGGER_ENABLED") is True
        assert isinstance(config.get_bool("SWAGGER_ENABLED"), bool)

    def test_get_float(self, monkeypatch):
        """Test get_float method."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("DEFAULT_LLM_TEMPERATURE", "0.8")

        app = Flask(__name__)
        app.logger = MagicMock()
        config = Config(MagicMock(), app)

        assert config.get_float("DEFAULT_LLM_TEMPERATURE") == 0.8
        assert isinstance(config.get_float("DEFAULT_LLM_TEMPERATURE"), float)

    def test_get_list(self, monkeypatch):
        """Test get_list method."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("NEXT_PUBLIC_LOGIN_METHODS_ENABLED", "phone,email,oauth")

        app = Flask(__name__)
        app.logger = MagicMock()
        config = Config(MagicMock(), app)

        methods = config.get_list("NEXT_PUBLIC_LOGIN_METHODS_ENABLED")
        assert methods == ["phone", "email", "oauth"]
        assert isinstance(methods, list)


class TestConfigGetAttr:
    """Test __getattr__ functionality."""

    def test_getattr_from_enhanced_config(self, monkeypatch):
        """Test getting attribute from enhanced config."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("REDIS_HOST", "attr-redis")

        app = Flask(__name__)
        app.logger = MagicMock()
        parent_config = MagicMock()

        config = Config(parent_config, app)

        # Should get from enhanced config
        assert config.REDIS_HOST == "attr-redis"

    def test_getattr_fallback_to_parent(self, monkeypatch):
        """Test falling back to parent for unknown attributes."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        app = Flask(__name__)
        app.logger = MagicMock()
        parent_config = MagicMock()
        parent_config.__getattr__.return_value = "parent-attr"

        config = Config(parent_config, app)

        # Try to get unknown attribute
        with patch.object(config.enhanced, "get", side_effect=Exception("Unknown")):
            value = config.UNKNOWN_ATTR
            assert value == "parent-attr"
            parent_config.__getattr__.assert_called_with("UNKNOWN_ATTR")


class TestConfigSetDefault:
    """Test setdefault method."""

    def test_setdefault_existing_value(self, monkeypatch):
        """Test setdefault with existing value."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("REDIS_HOST", "existing-host")

        app = Flask(__name__)
        app.logger = MagicMock()
        parent_config = MagicMock()

        config = Config(parent_config, app)

        # Should return existing value
        result = config.setdefault("REDIS_HOST", "default-host")
        assert result == "existing-host"

        # Parent setdefault should not be called
        parent_config.setdefault.assert_not_called()

    def test_setdefault_missing_value(self, monkeypatch):
        """Test setdefault with missing value."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        app = Flask(__name__)
        app.logger = MagicMock()
        parent_config = MagicMock()
        parent_config.setdefault.return_value = "default-value"

        config = Config(parent_config, app)

        # Should call parent setdefault
        with patch.object(config.enhanced, "get", return_value=None):
            result = config.setdefault("MISSING_KEY", "default-value")
            assert result == "default-value"
            parent_config.setdefault.assert_called_with("MISSING_KEY", "default-value")


class TestConfigCall:
    """Test __call__ functionality."""

    def test_call_delegates_to_parent(self, monkeypatch):
        """Test that __call__ delegates to parent config."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        app = Flask(__name__)
        app.logger = MagicMock()
        parent_config = MagicMock()
        parent_config.__call__.return_value = "call-result"

        config = Config(parent_config, app)

        # Call config as function
        result = config("arg1", "arg2", key="value")

        assert result == "call-result"
        parent_config.__call__.assert_called_with("arg1", "arg2", key="value")


class TestGetConfigFunction:
    """Test the global get_config function."""

    def test_get_config_with_initialized_instance(self, monkeypatch):
        """Test get_config when instance is initialized."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("REDIS_HOST", "global-redis")

        app = Flask(__name__)
        app.logger = MagicMock()

        # Initialize Config (sets global instance)
        _ = Config(MagicMock(), app)

        # Use get_config function
        value = get_config("REDIS_HOST")
        assert value == "global-redis"

    def test_get_config_without_initialized_instance(self, monkeypatch):
        """Test get_config works before initialization by reading from environment."""
        # Clear global instance
        import flaskr.common.config as config_module

        original_instance = config_module.__INSTANCE__
        config_module.__INSTANCE__ = None

        try:
            # Test with a known ENV_VAR key - should get from environment or default
            monkeypatch.setenv("REDIS_HOST", "env-redis-host")
            value = get_config("REDIS_HOST")
            assert value == "env-redis-host"
            
            # Test with unknown key - should get from environment
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
            # Restore original instance
            config_module.__INSTANCE__ = original_instance


class TestConfigIntegrationWithFlask:
    """Test Config integration with Flask application."""

    def test_config_with_real_flask_app(self, monkeypatch):
        """Test Config with a real Flask application."""
        # Set up comprehensive environment
        for key, value in DOCKER_ENV_CONFIG.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")

        # Create real Flask app
        app = Flask(__name__)

        # Initialize Config
        config = Config(app.config, app)

        # Test that we can access config values
        assert config["REDIS_HOST"] == "ai-shifu-redis"
        assert config.get_int("REDIS_PORT") == 6379
        assert config.get_bool("SWAGGER_ENABLED") is True

        # Test that Flask app has access to config
        app.config = config
        assert app.config["SECRET_KEY"] == "docker-secret-key-123456"

    def test_config_priority_enhanced_over_parent(self, monkeypatch):
        """Test that enhanced config takes priority over parent."""
        monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "test-db")
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "123456")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("REDIS_HOST", "enhanced-redis")

        app = Flask(__name__)
        app.logger = MagicMock()

        # Set different value in parent config
        parent_config = MagicMock()
        parent_config.__getitem__.return_value = "parent-redis"

        config = Config(parent_config, app)

        # Enhanced config should take priority
        assert config["REDIS_HOST"] == "enhanced-redis"

        # Parent should not be called for known keys
        parent_config.__getitem__.assert_not_called()
