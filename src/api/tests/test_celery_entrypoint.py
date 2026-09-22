"""Verify the worker and beat entrypoint exports the shared Celery application."""

import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ENTRYPOINT = Path(__file__).resolve().parents[1] / "celery_app.py"


def test_celery_entrypoint_exports_shared_factory_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    celery_app = object()
    factory = Mock(return_value=celery_app)
    monkeypatch.setitem(
        sys.modules,
        "flaskr.common.celery_app",
        SimpleNamespace(get_celery_app=factory),
    )

    loaded = runpy.run_path(str(ENTRYPOINT))

    factory.assert_called_once_with()
    assert loaded["celery_app"] is celery_app


def test_celery_entrypoint_propagates_worker_initialization_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("worker initialization failed")
    factory = Mock(side_effect=failure)
    monkeypatch.setitem(
        sys.modules,
        "flaskr.common.celery_app",
        SimpleNamespace(get_celery_app=factory),
    )

    with pytest.raises(RuntimeError, match="worker initialization failed") as caught:
        runpy.run_path(str(ENTRYPOINT))

    assert caught.value is failure
    factory.assert_called_once_with()
