"""Monkey-patching must match the gunicorn worker class.

The production deployment runs ``-k gthread``; the config file used to call
``monkey.patch_all()`` unconditionally (written for a gevent worker),
producing a gthread/gevent hybrid whose hub crashes silently interrupted
in-flight DB exchanges. The guard patches only when the command line
actually selects the gevent worker.
"""

import pathlib


def _load_detector():
    conf_path = pathlib.Path(__file__).resolve().parents[1] / "gunicorn.conf.py"
    source = conf_path.read_text()
    # Execute only the detector function, not the module (which would
    # monkey-patch or set env flags as a side effect).
    namespace = {}
    marker = "def _gevent_worker_requested"
    start = source.index(marker)
    end = source.index("\nif _gevent_worker_requested", start)
    exec(source[start:end], namespace)  # noqa: S102 - own config source
    return namespace["_gevent_worker_requested"]


def test_worker_class_detection():
    detect = _load_detector()

    assert detect(["gunicorn", "-k", "gevent", "app:app"]) is True
    assert detect(["gunicorn", "--worker-class", "gevent"]) is True
    assert detect(["gunicorn", "--worker-class=gevent"]) is True
    assert detect(["gunicorn", "-kgevent"]) is True
    assert detect(["gunicorn", "-k", "gunicorn.workers.ggevent.GeventWorker"]) is True
    assert (
        detect(["gunicorn", "--worker-class=gunicorn.workers.ggevent.GeventWorker"])
        is True
    )
    assert detect(["gunicorn", "-k", "egg:gunicorn#gevent"]) is True

    # The production command line - MUST NOT patch.
    assert (
        detect(
            [
                "gunicorn",
                "-k",
                "gthread",
                "--threads",
                "8",
                "-w",
                "4",
                "app:app",
            ]
        )
        is False
    )
    assert detect(["gunicorn", "--worker-class=gthread"]) is False
    assert detect(["gunicorn", "app:app"]) is False


def test_observer_skips_unpatched_processes(monkeypatch: object):
    from flaskr.common.gevent_hub_observer import install_hub_error_observer
    from gevent import monkey

    monkeypatch.setattr(monkey, "is_module_patched", lambda _name: False)

    class _Logger:
        def error(self, *args: object, **kwargs: object):
            _ = (args, kwargs)
            message = "must not log during a skipped install"
            raise AssertionError(message)

    assert install_hub_error_observer(_Logger()) is False
