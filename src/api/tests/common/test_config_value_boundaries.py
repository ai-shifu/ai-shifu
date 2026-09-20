"""Protect optional configuration conversion and operator export contracts."""

from decimal import Decimal

import pytest
from flaskr.common import config


@pytest.mark.parametrize(
    ("kind", "value", "expected"),
    [
        (bool, 0, False),
        (bool, 2, True),
        (float, "1.25", 1.25),
        (Decimal, "0.000001", Decimal("0.000001")),
        (list, ("a", "b"), ["a", "b"]),
        (str, 123, "123"),
    ],
)
def test_environment_values_preserve_declared_type(
    kind: type, value: object, expected: object
) -> None:
    assert config.EnvVar("BOUNDARY_SETTING", type=kind).convert_type(value) == expected


@pytest.mark.parametrize(
    ("kind", "value", "message"),
    [
        (float, "not-a-number", "Invalid float"),
        (float, [], "Invalid float"),
        (Decimal, "not-a-number", "Invalid decimal"),
    ],
)
def test_bad_numeric_settings_raise_config_error(
    kind: type, value: object, message: str
) -> None:
    with pytest.raises(config.EnvironmentConfigError, match=message):
        config.EnvVar("BOUNDARY_SETTING", type=kind).convert_type(value)


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        (None, True),
        ("", True),
        ({"voice": 3}, True),
        ('{"voice":"4"}', True),
        ('{"voice":"not-int"}', False),
        ('{"voice":null}', False),
        ('{"voice":[]}', False),
        ("broken", False),
        ("[]", False),
        ("true", False),
    ],
)
def test_rpm_map_validation_rejects_unusable_limits(value: object, valid: bool) -> None:
    assert config._is_valid_rpm_limits_json(value) is valid


@pytest.mark.parametrize(
    ("accessor", "value", "expected"),
    [
        ("get_int", None, 0),
        ("get_int", "bad", 0),
        ("get_int", "12", 12),
        ("get_float", None, 0.0),
        ("get_float", "bad", 0.0),
        ("get_float", "1.25", 1.25),
        ("get_bool", "yes", True),
        ("get_bool", "off", False),
        ("get_bool", 4, True),
        ("get_bool", None, False),
        ("get_list", None, []),
        ("get_list", " a, ,b ", ["a", "b"]),
        ("get_list", 4, []),
        ("get_list", ["a"], ["a"]),
    ],
)
def test_typed_accessors_have_stable_fallbacks(
    accessor: str, value: object, expected: object
) -> None:
    settings = config.EnhancedConfig({})
    settings._cache["VALUE"] = value
    assert getattr(settings, accessor)("VALUE") == expected


def test_invalid_llm_limits_return_false_without_leaking_parser_error() -> None:
    assert not config._is_valid_llm_model_max_output_tokens_json('{"model":false}')
    assert config._is_valid_llm_model_max_output_tokens_json('{"model":1024}')


def test_required_env_export_excludes_optional_and_runtime_secret_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_API_SECRET", "runtime-private-value")
    settings = config.EnhancedConfig(
        {
            "TEST_API_SECRET": config.EnvVar(
                "TEST_API_SECRET", required=True, secret=True
            ),
            "OPTIONAL": config.EnvVar("OPTIONAL", default="optional"),
            "NAMES": config.EnvVar("NAMES", type=list, default=["a", "b"]),
            "LIST_TEXT": config.EnvVar("LIST_TEXT", type=list, default="a,b"),
        }
    )
    required = settings.export_env_example_filtered("required")
    assert 'TEST_API_SECRET=""' in required
    assert "runtime-private-value" not in required
    assert "OPTIONAL=" not in required
    assert "END OF REQUIRED VARIABLES" in required
    complete = settings.export_env_example()
    assert 'NAMES="a,b"' in complete
    assert 'LIST_TEXT="a,b"' in complete
    assert 'OPTIONAL="optional"' in complete
    assert "runtime-private-value" not in complete


def test_uninitialized_optional_secret_uses_callsite_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.Config, "_instance", None)
    monkeypatch.setitem(
        config.ENV_VARS, "OPTIONAL_TEST_SECRET", config.EnvVar("OPTIONAL_TEST_SECRET")
    )
    monkeypatch.delenv("OPTIONAL_TEST_SECRET", raising=False)
    assert config.get_config("OPTIONAL_TEST_SECRET", "fallback") == "fallback"


def test_unknown_redis_derived_prefix_is_empty_without_explicit_suffix() -> None:
    assert config.get_redis_derived_prefix("UNREGISTERED_REDIS_PREFIX") == ""
