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
    engines = {"default": Mock(), "analytics": Mock()}
    resources = SimpleNamespace(_instances={"master-client": object()})
    worker_once = object()
    once_factory = Mock(return_value=worker_once)
    tracing = SimpleNamespace(
        _TRACER_PROVIDER=object(), _TRACER_PROVIDER_SET_ONCE=object()
    )
    install_observer = Mock()

    def rebuild_tracing(flask_app: Flask) -> None:
        assert flask_app is app
        assert resources._instances == {}
        assert tracing._TRACER_PROVIDER is None
        assert tracing._TRACER_PROVIDER_SET_ONCE is worker_once

    init_tracing = Mock(side_effect=rebuild_tracing)

    def prepare(flask_app: Flask) -> None:
        assert flask_app is app
        assert "AI_SHIFU_PRELOAD_MASTER" not in os.environ
        for engine in engines.values():
            engine.dispose.assert_called_once_with(close=False)
        install_observer.assert_called_once_with(app.logger)
        init_tracing.assert_called_once_with(app)
        if preparation_fails:
            raise RuntimeError

    init_live = Mock(side_effect=prepare)
    isolated_imports = {
        "app": SimpleNamespace(app=app),
        "flaskr.dao": SimpleNamespace(db=SimpleNamespace(engines=engines)),
        "flaskr.common.gevent_hub_observer": SimpleNamespace(
            install_hub_error_observer=install_observer
        ),
        "flaskr.api.langfuse": SimpleNamespace(init_langfuse=init_tracing),
        "langfuse._client.resource_manager": SimpleNamespace(
            LangfuseResourceManager=resources
        ),
        "opentelemetry": SimpleNamespace(trace=tracing),
        "opentelemetry.util._once": SimpleNamespace(Once=once_factory),
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
    init_tracing.assert_not_called()
    install_observer.assert_not_called()
    once_factory.assert_not_called()
    assert resources._instances

    worker = SimpleNamespace(log=Mock())
    config["post_fork"](object(), worker)
    init_live.assert_called_once_with(app)
    once_factory.assert_called_once_with()
    worker.log.exception.assert_not_called()
    assert worker.log.warning.call_count == int(preparation_fails)
