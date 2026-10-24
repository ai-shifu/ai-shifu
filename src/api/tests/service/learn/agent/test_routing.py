"""Verify environment-wide runtime selection without shared database fallbacks."""

from __future__ import annotations

import pytest
from flaskr.common import config
from flaskr.service.learn.agent import routing


@pytest.mark.parametrize(
    "raw",
    [True, "true", " TRUE ", "1", "yes", "On"],
)
def test_enabled_deployment_routes_every_identified_course(
    monkeypatch: pytest.MonkeyPatch, raw: object
) -> None:
    monkeypatch.setattr(routing, "get_config", lambda *_args, **_kwargs: raw)
    for course in ("previously-listed", "never-listed", " newly-created "):
        assert routing.uses_agent_engine(course) is True


@pytest.mark.parametrize(
    "raw",
    [False, None, "", "false", " FALSE ", "0", "no", "off", "typo", [], {}, 1],
)
def test_disabled_or_malformed_values_keep_every_course_on_legacy(
    monkeypatch: pytest.MonkeyPatch, raw: object
) -> None:
    monkeypatch.setattr(routing, "get_config", lambda *_args, **_kwargs: raw)
    assert routing.uses_agent_engine("previously-listed") is False
    assert routing.uses_agent_engine("never-listed") is False


@pytest.mark.parametrize("course", ["", "   ", None])
def test_missing_course_identifier_stays_on_legacy(
    monkeypatch: pytest.MonkeyPatch, course: object
) -> None:
    monkeypatch.setattr(routing, "get_config", lambda *_args, **_kwargs: True)
    assert routing.uses_agent_engine(course) is False


def test_routing_reads_only_the_environment_registry() -> None:
    assert routing.get_config is config.get_config
    assert routing.V2_ENABLED_CONFIG_KEY == "FLOW_ENGINE_V2_ENABLED"
    registered = config.ENV_VARS[routing.V2_ENABLED_CONFIG_KEY]
    assert registered.type is bool
    assert registered.default is False
    assert "FLOW_ENGINE_V2_SHIFU_BIDS" not in config.ENV_VARS


@pytest.mark.parametrize("initialized", [False, True])
@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        (None, False),
        ("", False),
        ("false", False),
        ("0", False),
        ("off", False),
        ("typo", False),
        ("true", True),
        (" YES ", True),
        ("1", True),
    ],
)
def test_real_environment_registry_selects_runtime_before_and_after_initialization(
    monkeypatch: pytest.MonkeyPatch,
    initialized: bool,
    environment: str | None,
    expected: bool,
) -> None:
    key = routing.V2_ENABLED_CONFIG_KEY
    monkeypatch.setenv("FLOW_ENGINE_V2_SHIFU_BIDS", "previously-listed")
    if environment is None:
        monkeypatch.delenv(key, raising=False)
    else:
        monkeypatch.setenv(key, environment)
    # Use the real Config.get and parser/cache without starting external services.
    instance = None
    if initialized:
        instance = config.Config.__new__(config.Config)
        instance.enhanced = config.EnhancedConfig(config.ENV_VARS)
        instance.parent = {key: True}  # An unset environment must still win.
    monkeypatch.setattr(config.Config, "_instance", instance)
    assert routing.uses_agent_engine("previously-listed") is expected
    assert routing.uses_agent_engine("never-listed") is expected
