"""Verify application factory ownership and reuse."""


def test_create_app_reuses_the_owned_application(app: object) -> None:
    from app import create_app

    assert create_app() is app
    assert app.extensions["serving_http"] is True


def test_owned_strict_app_cannot_be_upgraded_by_a_later_development_import(
    app: object, monkeypatch: object
) -> None:
    import pytest
    from app import create_app

    monkeypatch.setitem(app.extensions, "development_verification_codes", value=False)
    with pytest.raises(RuntimeError, match="fresh dedicated startup"):
        create_app(development_verification_codes=True)
    assert create_app() is app
    assert app.extensions["development_verification_codes"] is False


def test_development_entry_grants_capability_and_registers_runtime_hooks(
    app: object, monkeypatch: object
) -> None:
    import os
    import runpy
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import Mock

    import flaskr.command
    import flaskr.framework.plugin.enable_plugin

    factory = Mock(return_value=app)
    application = SimpleNamespace(create_app=factory, app=None)
    plugins = Mock()
    commands = Mock()
    monkeypatch.setitem(sys.modules, "app", application)
    monkeypatch.setattr(flaskr.command, "enable_commands", commands)
    monkeypatch.setattr(
        flaskr.framework.plugin.enable_plugin, "enable_plugins", plugins
    )
    previous = os.environ.get("SKIP_APP_AUTOCREATE")
    result = runpy.run_path(str(Path(__file__).parents[1] / "development_app.py"))
    factory.assert_called_once_with(development_verification_codes=True)
    assert application.app is result["app"] is app
    assert os.environ.get("SKIP_APP_AUTOCREATE") == previous
    plugins.assert_called_once_with(app)
    commands.assert_called_once_with(app)


def test_ordinary_factory_ignores_environment_capability_flags(
    monkeypatch: object,
) -> None:
    from types import SimpleNamespace

    import app as application
    import flaskr.common
    import pytest

    class StopInitializationError(Exception):
        pass

    observed = []

    def stop_after_startup_capability(_parent: object, flask_app: object) -> None:
        observed.append(flask_app.extensions["development_verification_codes"])
        raise StopInitializationError

    monkeypatch.setattr(application, "_application_state", SimpleNamespace(app=None))
    monkeypatch.setattr(flaskr.common, "Config", stop_after_startup_capability)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("development_verification_codes", "True")
    monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "configured-test-code")
    with pytest.raises(StopInitializationError):
        application.create_app()
    assert observed == [False]


def test_deployment_examples_keep_default_startup_strict() -> None:
    from pathlib import Path

    import yaml
    from flaskr.common.config import ENV_VARS

    root = Path(__file__).resolve().parents[3]
    assert ENV_VARS["UNIVERSAL_VERIFICATION_CODE"].default == ""
    assert ENV_VARS["UNIVERSAL_VERIFICATION_CODE"].example is None
    assert (
        'UNIVERSAL_VERIFICATION_CODE=""'
        in (root / "docker/.env.example.full").read_text()
    )
    for name in ("docker-compose.yml", "docker-compose.latest.yml"):
        config = yaml.safe_load((root / "docker" / name).read_text())
        api = config["services"]["ai-shifu-api"]
        assert "app:app" in " ".join(api["entrypoint"])
        assert not api.get("environment", {}).get("UNIVERSAL_VERIFICATION_CODE")
    for name, entry in (
        ("docker-compose.dev.yml", "development_app:app"),
        ("docker-compose.runtime-harness.yml", "runtime_app:app"),
    ):
        config = yaml.safe_load((root / "docker" / name).read_text())
        api = config["services"]["ai-shifu-api-dev"]
        assert entry in " ".join(api["command"])
    assert '"app:app"' in (root / "src/api/Dockerfile").read_text()
