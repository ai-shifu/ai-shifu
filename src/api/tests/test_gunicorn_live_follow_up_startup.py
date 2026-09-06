"""Keep Live startup preparation inside initialized Gunicorn workers."""

import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask


@pytest.mark.parametrize("preparation_fails", [False, True])
def test_post_fork_initializes_live_after_resetting_resources(
    monkeypatch: pytest.MonkeyPatch, preparation_fails: bool
) -> None:
    app = Flask("gunicorn-live-startup")
    engine = Mock()
    init_tracing = Mock()

    def prepare(flask_app: Flask) -> None:
        assert flask_app is app
        assert "AI_SHIFU_PRELOAD_MASTER" not in os.environ
        engine.dispose.assert_called_once_with(close=False)
        init_tracing.assert_called_once_with(app)
        if preparation_fails:
            raise RuntimeError

    init_live = Mock(side_effect=prepare)
    isolated_imports = {
        "app": SimpleNamespace(app=app),
        "flaskr.dao": SimpleNamespace(db=SimpleNamespace(engines={"default": engine})),
        "flaskr.common.gevent_hub_observer": SimpleNamespace(
            install_hub_error_observer=Mock()
        ),
        "flaskr.api.langfuse": SimpleNamespace(init_langfuse=init_tracing),
        "langfuse._client.resource_manager": SimpleNamespace(
            LangfuseResourceManager=SimpleNamespace(_instances={})
        ),
        "opentelemetry": SimpleNamespace(trace=SimpleNamespace()),
        "opentelemetry.util._once": SimpleNamespace(Once=Mock()),
        "flaskr.service.learn.live_follow_up_routes": SimpleNamespace(
            init_live_follow_up_readiness=init_live
        ),
    }
    for name, module in isolated_imports.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(sys, "argv", ["gunicorn", "-k", "gthread", "app:app"])
    # Register the environment mutation with monkeypatch for test cleanup.
    monkeypatch.setenv("AI_SHIFU_PRELOAD_MASTER", "1")
    config = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "gunicorn.conf.py")
    )
    assert config["preload_app"] is True
    init_live.assert_not_called()

    worker = SimpleNamespace(log=Mock())
    config["post_fork"](object(), worker)
    init_live.assert_called_once_with(app)
    worker.log.exception.assert_not_called()
    assert worker.log.warning.call_count == int(preparation_fails)
