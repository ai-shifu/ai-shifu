"""Worker memory must stay bounded under the preloaded gthread deployment."""

import gc
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

CONFIG = Path(__file__).resolve().parents[1] / "gunicorn.conf.py"


def _load(monkeypatch: pytest.MonkeyPatch, cdll: object) -> dict:
    monkeypatch.setattr(sys, "argv", ["gunicorn", "-k", "gthread", "app:app"])
    monkeypatch.setenv("AI_SHIFU_PRELOAD_MASTER", "0")
    monkeypatch.setattr("flaskr.metrics_runtime.prepare_metrics_directory", Mock())
    monkeypatch.setattr("ctypes.CDLL", cdll)
    return runpy.run_path(str(CONFIG))


def test_master_caps_malloc_arenas_before_workers_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MALLOC_ARENA_MAX", raising=False)
    libc = SimpleNamespace(mallopt=Mock(return_value=1))
    cdll = Mock(return_value=libc)
    config = _load(monkeypatch, cdll)
    cdll.assert_called_once_with("libc.so.6")
    libc.mallopt.assert_called_once_with(-8, 2)
    assert config["preload_app"] is True


def test_explicit_arena_setting_and_non_glibc_hosts_are_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MALLOC_ARENA_MAX", "4")
    cdll = Mock()
    config = _load(monkeypatch, cdll)
    cdll.assert_not_called()
    monkeypatch.delenv("MALLOC_ARENA_MAX")
    monkeypatch.setattr("ctypes.CDLL", Mock(side_effect=OSError))
    assert config["_limit_malloc_arenas"]() is False


def test_workers_inherit_frozen_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MALLOC_ARENA_MAX", "2")
    config = _load(monkeypatch, Mock())
    # Recycling would strand gthread workers behind open lesson streams and leave
    # a Prometheus counter file per retired worker; the causes are bounded instead.
    assert "max_requests" not in config
    freeze = Mock()
    monkeypatch.setattr(gc, "freeze", freeze)
    config["pre_fork"](object(), object())
    freeze.assert_called_once_with()


def test_litellm_logging_pool_stays_small() -> None:
    import flaskr.api.llm  # noqa: F401 - sets the default before importing litellm
    from litellm.litellm_core_utils.thread_pool_executor import executor

    assert executor._max_workers <= 4
