"""Start development file watchers only in initialized Gunicorn workers."""

import runpy
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.framework.plugin.plugin_manager import PluginManager


@pytest.mark.parametrize("environment", ["development", "production", "testing"])
@pytest.mark.parametrize("manager_present", [False, True])
def test_post_worker_init_starts_only_development_plugin_manager(
    monkeypatch: pytest.MonkeyPatch, environment: str, manager_present: bool
) -> None:
    app = Flask("gunicorn-plugin-startup")
    app.config["ENV"] = environment
    manager = PluginManager(app)
    reloader = Mock()
    factory = Mock(return_value=reloader)
    monkeypatch.setattr(
        "flaskr.framework.plugin.plugin_manager.PluginHotReloader", factory
    )
    monkeypatch.setattr(
        "flaskr.framework.plugin.plugin_manager.get_plugin_manager",
        lambda: manager if manager_present else None,
    )
    monkeypatch.setattr(sys, "argv", ["gunicorn", "-k", "gthread", "app:app"])
    monkeypatch.setenv("AI_SHIFU_PRELOAD_MASTER", "1")
    monkeypatch.setattr("flaskr.metrics_runtime.prepare_metrics_directory", Mock())
    config = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "gunicorn.conf.py")
    )
    factory.assert_not_called()

    # Gunicorn clears the preload role in post_fork, then initializes the
    # gevent hub and WSGI app before calling post_worker_init.
    monkeypatch.delenv("AI_SHIFU_PRELOAD_MASTER")
    config["post_worker_init"](Mock())
    config["post_worker_init"](Mock())

    if manager_present and environment == "development":
        factory.assert_called_once_with(app)
        reloader.start.assert_called_once_with()
    else:
        factory.assert_not_called()
