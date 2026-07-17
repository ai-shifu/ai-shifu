"""
Unit tests for EnvVar dataclass.
"""

import pytest
from flaskr.common.config import (
    ENV_VARS,
    EnvVar,
    parse_llm_model_max_output_tokens,
)
from tests.common.fixtures.mock_validators import (
    mock_port_validator,
    mock_email_validator,
    always_fail_validator,
    always_pass_validator,
    range_validator,
)


class TestEnvVarInitialization:
    """Test EnvVar initialization and validation."""

    def test_valid_envvar_with_defaults(self):
        """Test creating EnvVar with default values."""
        env_var = EnvVar(
            name="TEST_VAR",
            default="default_value",
            description="Test variable",
            group="test",
        )

        assert env_var.name == "TEST_VAR"
        assert env_var.default == "default_value"
        assert env_var.required is False
        assert env_var.type is str
        assert env_var.description == "Test variable"
        assert env_var.group == "test"
        assert env_var.secret is False
        assert env_var.validator is None
        assert env_var.depends_on == []

    def test_valid_envvar_required_no_default(self):
        """Test creating required EnvVar without default."""
        env_var = EnvVar(
            name="REQUIRED_VAR",
            required=True,
            description="Required variable",
            secret=True,
        )

        assert env_var.name == "REQUIRED_VAR"
        assert env_var.required is True
        assert env_var.default is None
        assert env_var.secret is True

    def test_valid_envvar_optional_with_default(self):
        """Test creating optional EnvVar with default."""
        env_var = EnvVar(
            name="OPTIONAL_VAR",
            required=False,
            default="optional_default",
            type=str,
        )

        assert env_var.required is False
        assert env_var.default == "optional_default"

    def test_invalid_required_with_default(self):
        """Test that required=True with default raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            EnvVar(
                name="INVALID_VAR",
                required=True,
                default="should_fail",
                description="This should fail",
            )

        assert "marked as required" in str(exc_info.value)
        assert "has a default value" in str(exc_info.value)

    def test_envvar_with_custom_validator(self):
        """Test EnvVar with custom validator function."""
        env_var = EnvVar(
            name="PORT",
            default=8080,
            type=int,
            validator=mock_port_validator,
        )

        assert env_var.validator is not None
        assert env_var.validator(8080) is True
        assert env_var.validator(99999) is False

    def test_envvar_with_dependencies(self):
        """Test EnvVar with dependencies."""
        env_var = EnvVar(
            name="DEPENDENT_VAR",
            depends_on=["VAR1", "VAR2"],
        )

        assert env_var.depends_on == ["VAR1", "VAR2"]


class TestEnvVarTypeConversion:
    """Test type conversion functionality."""

    def test_convert_to_int(self):
        """Test string to int conversion."""
        env_var = EnvVar(name="INT_VAR", type=int, default=100)

        assert env_var.convert_type("123") == 123
        assert env_var.convert_type(456) == 456  # Already int
        assert env_var.convert_type("") == 100  # Empty returns default
        assert env_var.convert_type(None) == 100  # None returns default

    def test_convert_to_float(self):
        """Test string to float conversion."""
        env_var = EnvVar(name="FLOAT_VAR", type=float, default=1.5)

        assert env_var.convert_type("3.14") == 3.14
        assert env_var.convert_type(2.71) == 2.71  # Already float
        assert env_var.convert_type("10") == 10.0
        assert env_var.convert_type("") == 1.5  # Empty returns default

    def test_convert_to_bool(self):
        """Test string to bool conversion."""
        env_var = EnvVar(name="BOOL_VAR", type=bool, default=False)

        # True values
        assert env_var.convert_type("true") is True
        assert env_var.convert_type("True") is True
        assert env_var.convert_type("TRUE") is True
        assert env_var.convert_type("1") is True
        assert env_var.convert_type("yes") is True
        assert env_var.convert_type("on") is True

        # False values
        assert env_var.convert_type("false") is False
        assert env_var.convert_type("False") is False
        assert env_var.convert_type("0") is False
        assert env_var.convert_type("no") is False
        assert env_var.convert_type("off") is False
        assert env_var.convert_type("random") is False

        # Already boolean
        assert env_var.convert_type(True) is True
        assert env_var.convert_type(False) is False

        # Empty/None returns default
        assert env_var.convert_type("") is False
        assert env_var.convert_type(None) is False

    def test_convert_string_remains_string(self):
        """Test that strings remain strings when type is str."""
        env_var = EnvVar(name="STR_VAR", type=str, default="default")

        assert env_var.convert_type("hello") == "hello"
        assert env_var.convert_type(123) == "123"
        assert env_var.convert_type("") == "default"
        assert env_var.convert_type(None) == "default"

    def test_convert_type_with_invalid_input(self):
        """Test type conversion with invalid input."""
        from flaskr.common.config import EnvironmentConfigError

        env_var = EnvVar(name="INT_VAR", type=int, default=0)

        with pytest.raises(EnvironmentConfigError):
            env_var.convert_type("not_a_number")

        with pytest.raises(EnvironmentConfigError):
            env_var.convert_type("12.34.56")


class TestEnvVarValidation:
    """Test validation functionality."""

    def test_validate_with_no_validator(self):
        """Test validation when no validator is set."""
        env_var = EnvVar(name="NO_VALIDATOR")

        assert env_var.validate_value("anything") is True
        assert env_var.validate_value(123) is True
        assert env_var.validate_value(None) is True

    def test_validate_with_port_validator(self):
        """Test validation with port validator."""
        env_var = EnvVar(
            name="PORT",
            type=int,
            validator=mock_port_validator,
        )

        assert env_var.validate_value(80) is True
        assert env_var.validate_value(8080) is True
        assert env_var.validate_value(65535) is True
        assert env_var.validate_value(0) is False
        assert env_var.validate_value(65536) is False
        assert env_var.validate_value(-1) is False

    def test_validate_with_email_validator(self):
        """Test validation with email validator."""
        env_var = EnvVar(
            name="EMAIL",
            type=str,
            validator=mock_email_validator,
        )

        assert env_var.validate_value("test@example.com") is True
        assert env_var.validate_value("user.name@domain.co.uk") is True
        assert env_var.validate_value("invalid.email") is False
        assert env_var.validate_value("@example.com") is False
        assert env_var.validate_value("") is False

    def test_validate_with_always_fail(self):
        """Test validation with always-fail validator."""
        env_var = EnvVar(
            name="FAIL_VAR",
            validator=always_fail_validator,
        )

        assert env_var.validate_value("anything") is False
        assert env_var.validate_value(123) is False

    def test_validate_with_range_validator(self):
        """Test validation with range validator."""
        env_var = EnvVar(
            name="TEMPERATURE",
            type=float,
            validator=range_validator(0.0, 2.0),
        )

        assert env_var.validate_value(0.0) is True
        assert env_var.validate_value(1.0) is True
        assert env_var.validate_value(2.0) is True
        assert env_var.validate_value(-0.1) is False
        assert env_var.validate_value(2.1) is False


class TestLLMModelMaxOutputTokensConfig:
    def test_parse_valid_routed_model_limits(self):
        assert parse_llm_model_max_output_tokens(
            '{"qwen/deepseek-v4-flash":393216,"gemini-3.5-flash":65536}'
        ) == {
            "qwen/deepseek-v4-flash": 393216,
            "gemini-3.5-flash": 65536,
        }

    @pytest.mark.parametrize(
        "value",
        [
            "not-json",
            "[]",
            '{"": 1}',
            '{"qwen/model": 0}',
            '{"qwen/model": -1}',
            '{"qwen/model": true}',
            '{"qwen/model": 1.5}',
            '{"qwen/model": "8192"}',
            '{"qwen/model": 8192, " qwen/model ": 4096}',
        ],
    )
    def test_reject_invalid_routed_model_limits(self, value):
        env_var = ENV_VARS["LLM_MODEL_MAX_OUTPUT_TOKENS"]

        assert env_var.validate_value(value) is False
        with pytest.raises(ValueError):
            parse_llm_model_max_output_tokens(value)


class TestEnvVarMultilineDescription:
    """Test multi-line description support."""

    def test_single_line_description(self):
        """Test EnvVar with single-line description."""
        env_var = EnvVar(
            name="SINGLE_LINE",
            description="This is a single line description",
        )

        assert env_var.description == "This is a single line description"
        assert "\n" not in env_var.description

    def test_multi_line_description(self):
        """Test EnvVar with multi-line description."""
        description = """This is a multi-line description.
Line 2: More details here.
Line 3: Even more information."""

        env_var = EnvVar(
            name="MULTI_LINE",
            description=description,
        )

        assert env_var.description == description
        assert "\n" in env_var.description
        assert env_var.description.count("\n") == 2

    def test_empty_description(self):
        """Test EnvVar with empty description."""
        env_var = EnvVar(name="NO_DESC")

        assert env_var.description == ""


class TestEnvVarSecretHandling:
    """Test secret field handling."""

    def test_secret_field_true(self):
        """Test EnvVar marked as secret."""
        env_var = EnvVar(
            name="API_KEY",
            secret=True,
            description="Secret API key",
        )

        assert env_var.secret is True

    def test_secret_field_false(self):
        """Test EnvVar not marked as secret."""
        env_var = EnvVar(
            name="PUBLIC_VAR",
            secret=False,
            description="Public variable",
        )

        assert env_var.secret is False

    def test_secret_field_default(self):
        """Test default value of secret field."""
        env_var = EnvVar(name="DEFAULT_SECRET")

        assert env_var.secret is False  # Default should be False


class TestEnvVarEdgeCases:
    """Test edge cases and corner scenarios."""

    def test_envvar_with_all_fields(self):
        """Test EnvVar with all possible fields set."""
        env_var = EnvVar(
            name="COMPLETE_VAR",
            required=False,
            default="default",
            type=str,
            description="Complete variable with all fields",
            validator=always_pass_validator,
            secret=True,
            group="complete",
            depends_on=["DEP1", "DEP2"],
        )

        assert env_var.name == "COMPLETE_VAR"
        assert env_var.required is False
        assert env_var.default == "default"
        assert env_var.type is str
        assert env_var.description == "Complete variable with all fields"
        assert env_var.validator is not None
        assert env_var.secret is True
        assert env_var.group == "complete"
        assert env_var.depends_on == ["DEP1", "DEP2"]

    def test_envvar_minimal_fields(self):
        """Test EnvVar with only required field (name)."""
        env_var = EnvVar(name="MINIMAL_VAR")

        assert env_var.name == "MINIMAL_VAR"
        assert env_var.required is False
        assert env_var.default is None
        assert env_var.type is str
        assert env_var.description == ""
        assert env_var.validator is None
        assert env_var.secret is False
        assert env_var.group == "general"
        assert env_var.depends_on == []

    def test_envvar_name_with_special_chars(self):
        """Test EnvVar name with underscores and numbers."""
        env_var = EnvVar(name="TEST_VAR_123_ABC")

        assert env_var.name == "TEST_VAR_123_ABC"

    def test_envvar_group_categorization(self):
        """Test different group categorizations."""
        groups = ["database", "redis", "auth", "llm", "frontend", "monitoring"]

        for group in groups:
            env_var = EnvVar(name=f"VAR_{group.upper()}", group=group)
            assert env_var.group == group
