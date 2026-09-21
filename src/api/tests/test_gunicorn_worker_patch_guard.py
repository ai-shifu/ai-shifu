"""Monkey-patching must match the gunicorn worker class.

The production deployment runs ``-k gthread``; the config file used to call
``monkey.patch_all()`` unconditionally (written for a gevent worker),
producing a gthread/gevent hybrid whose hub crashes silently interrupted
in-flight DB exchanges. The guard patches only when the command line
actually selects the gevent worker.
"""

import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize(
    ("argv", "should_patch"),
    [
        (["gunicorn", "-k", "gevent", "app:app"], True),
        (["gunicorn", "--worker-class", "gevent"], True),
        (["gunicorn", "--worker-class=gevent"], True),
        (["gunicorn", "-kgevent"], True),
        (["gunicorn", "-k", "gunicorn.workers.ggevent.GeventWorker"], True),
        (["gunicorn", "--worker-class=gunicorn.workers.ggevent.GeventWorker"], True),
        (["gunicorn", "-k", "egg:gunicorn#gevent"], True),
        (
            [
                "gunicorn",
                "-k",
                "gthread",
                "--threads",
                "8",
                "-w",
                "4",
                "app:app",
            ],
            False,
        ),
        (["gunicorn", "--worker-class=gthread"], False),
        (["gunicorn", "app:app"], False),
        (["gunicorn", "-k"], False),
    ],
)
def test_worker_class_controls_actual_preload_patching(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], should_patch: bool
) -> None:
    patch_all = Mock()
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setenv("AI_SHIFU_PRELOAD_MASTER", "0")
    # Load the complete deployed source without patching this pytest process.
    monkeypatch.setitem(
        sys.modules,
        "gevent",
        SimpleNamespace(monkey=SimpleNamespace(patch_all=patch_all)),
    )

    config = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "gunicorn.conf.py")
    )

    if should_patch:
        patch_all.assert_called_once_with()
    else:
        patch_all.assert_not_called()
    assert os.environ["AI_SHIFU_PRELOAD_MASTER"] == "1"
    assert config["preload_app"] is True
    assert callable(config["post_fork"])


def test_observer_skips_unpatched_processes(monkeypatch: object) -> None:
    from flaskr.common.gevent_hub_observer import install_hub_error_observer
    from gevent import monkey

    monkeypatch.setattr(monkey, "is_module_patched", lambda _name: False)

    class _Logger:
        def error(self, *args: object, **kwargs: object) -> None:
            _ = (args, kwargs)
            message = "must not log during a skipped install"
            raise AssertionError(message)

    assert install_hub_error_observer(_Logger()) is False
