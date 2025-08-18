"""
Unit tests for environment variable trimming functionality.
"""

import pytest
from flaskr.common.config import EnhancedConfig, EnvVar


class TestEnvironmentVariableTrimming:
    """Test that environment variables are properly trimmed of whitespace."""

    def test_trim_string_values(self, monkeypatch):
        """Test that string values are trimmed during get."""
        monkeypatch.setenv("TEST_STRING", "  value with spaces  ")

        env_vars = {
            "TEST_STRING": EnvVar(
                name="TEST_STRING",
                default="default",
                description="Test string",
            )
        }

        config = EnhancedConfig(env_vars)
        value = config.get("TEST_STRING")

        assert value == "value with spaces"
        assert value != "  value with spaces  "

    def test_trim_integer_values(self, monkeypatch):
        """Test that integer values are trimmed before conversion."""
        monkeypatch.setenv("TEST_INT", "  42  ")

        env_vars = {
            "TEST_INT": EnvVar(
                name="TEST_INT",
                type=int,
                default=0,
                description="Test integer",
            )
        }

        config = EnhancedConfig(env_vars)
        value = config.get("TEST_INT")

        assert value == 42
        assert isinstance(value, int)

    def test_trim_boolean_values(self, monkeypatch):
        """Test that boolean values are trimmed before conversion."""
        monkeypatch.setenv("TEST_BOOL", "  true  ")

        env_vars = {
            "TEST_BOOL": EnvVar(
                name="TEST_BOOL",
                type=bool,
                default=False,
                description="Test boolean",
            )
        }

        config = EnhancedConfig(env_vars)
        value = config.get("TEST_BOOL")

        assert value is True

    def test_trim_float_values(self, monkeypatch):
        """Test that float values are trimmed before conversion."""
        monkeypatch.setenv("TEST_FLOAT", "  3.14  ")

        env_vars = {
            "TEST_FLOAT": EnvVar(
                name="TEST_FLOAT",
                type=float,
                default=0.0,
                description="Test float",
            )
        }

        config = EnhancedConfig(env_vars)
        value = config.get("TEST_FLOAT")

        assert value == 3.14
        assert isinstance(value, float)

    def test_whitespace_only_uses_default(self, monkeypatch):
        """Test that whitespace-only values use default."""
        monkeypatch.setenv("TEST_WHITESPACE", "   ")

        env_vars = {
            "TEST_WHITESPACE": EnvVar(
                name="TEST_WHITESPACE",
                default="default_value",
                description="Test whitespace",
            )
        }

        config = EnhancedConfig(env_vars)
        value = config.get("TEST_WHITESPACE")

        assert value == "default_value"

    def test_trim_in_validation(self, monkeypatch):
        """Test that values are trimmed during validation."""
        # Set required variables with whitespace
        monkeypatch.setenv("REQUIRED_VAR", "  required_value  ")
        monkeypatch.setenv("OPENAI_API_KEY", "  test-key  ")

        env_vars = {
            "REQUIRED_VAR": EnvVar(
                name="REQUIRED_VAR",
                required=True,
                description="Required variable",
            ),
            "OPENAI_API_KEY": EnvVar(
                name="OPENAI_API_KEY",
                default="",
                description="API key",
            ),
        }

        config = EnhancedConfig(env_vars)

        # Should validate successfully with trimmed values
        config.validate_environment()
        assert config._validated is True

    def test_trim_list_values(self, monkeypatch):
        """Test that list values handle whitespace correctly."""
        monkeypatch.setenv("TEST_LIST", "  item1 , item2 , item3  ")

        env_vars = {
            "TEST_LIST": EnvVar(
                name="TEST_LIST",
                type=list,
                default=[],
                description="Test list",
            )
        }

        config = EnhancedConfig(env_vars)
        value = config.get("TEST_LIST")

        # List items should be trimmed individually
        assert value == ["item1", "item2", "item3"]

    def test_trim_with_interpolation(self, monkeypatch):
        """Test that trimming works with variable interpolation."""
        monkeypatch.setenv("BASE_VALUE", "  base  ")
        monkeypatch.setenv("INTERPOLATED", "  prefix_${BASE_VALUE}_suffix  ")

        env_vars = {
            "BASE_VALUE": EnvVar(
                name="BASE_VALUE",
                default="",
                description="Base value",
            ),
            "INTERPOLATED": EnvVar(
                name="INTERPOLATED",
                default="",
                description="Interpolated value",
            ),
        }

        config = EnhancedConfig(env_vars)

        # Get base value first (it will be trimmed)
        base = config.get("BASE_VALUE")
        assert base == "base"

        # Get interpolated value (should be trimmed and interpolated)
        interpolated = config.get("INTERPOLATED")
        # The interpolation happens with the raw environment value
        # So it becomes "prefix_  base  _suffix" which is then returned as-is
        assert interpolated == "prefix_  base  _suffix"

    def test_required_with_whitespace_only_fails(self, monkeypatch):
        """Test that required variables with only whitespace fail validation."""
        monkeypatch.setenv("REQUIRED_VAR", "   ")  # Only whitespace
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        env_vars = {
            "REQUIRED_VAR": EnvVar(
                name="REQUIRED_VAR",
                required=True,
                description="Required variable",
            ),
            "OPENAI_API_KEY": EnvVar(
                name="OPENAI_API_KEY",
                default="",
                description="API key",
            ),
        }

        config = EnhancedConfig(env_vars)

        # Should fail validation because whitespace-only is treated as empty
        with pytest.raises(Exception) as exc_info:
            config.validate_environment()

        assert "Missing required environment variables" in str(exc_info.value)
        assert "REQUIRED_VAR" in str(exc_info.value)

    def test_convert_type_method_trims(self):
        """Test that EnvVar.convert_type method trims values."""
        env_var = EnvVar(
            name="TEST",
            type=int,
            default=0,
            description="Test",
        )

        # Test with whitespace
        result = env_var.convert_type("  42  ")
        assert result == 42

        # Test whitespace-only returns default
        result = env_var.convert_type("   ")
        assert result == 0

        # Test None returns default
        result = env_var.convert_type(None)
        assert result == 0
