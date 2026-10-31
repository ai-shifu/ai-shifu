"""Start development file watchers only in initialized Gunicorn workers."""

import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.framework.plugin.plugin_manager import PluginManager


@pytest.mark.parametrize("environment", ["development", "production", "testing"])
@pytest.mark.parametrize("manager_state", ["absent", "disabled", "enabled"])
def test_post_worker_init_starts_only_enabled_development_manager(
    monkeypatch: pytest.MonkeyPatch, environment: str, manager_state: str
) -> None:
    app = Flask("gunicorn-plugin-startup")
    app.config["ENV"] = environment
    manager = PluginManager(app)
    manager.is_enabled = manager_state == "enabled"
    factory = Mock()
    monkeypatch.setattr(
        "flaskr.framework.plugin.plugin_manager.PluginHotReloader", factory
    )
    monkeypatch.setattr(
        "flaskr.framework.plugin.plugin_manager.get_plugin_manager",
        lambda: None if manager_state == "absent" else manager,
    )
    # Register the config's environment mutation for automatic test cleanup.
    monkeypatch.setenv("AI_SHIFU_PRELOAD_MASTER", "1")
    config = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "gunicorn.conf.py")
    )

    # Gunicorn clears this marker in post_fork, loads the worker's WSGI app,
    # and then invokes post_worker_init.
    monkeypatch.delenv("AI_SHIFU_PRELOAD_MASTER")
    config["post_worker_init"](Mock())
    config["post_worker_init"](Mock())

    if manager_state == "enabled" and environment == "development":
        factory.assert_called_once_with(app)
        factory.return_value.start.assert_called_once_with()
    else:
        factory.assert_not_called()
