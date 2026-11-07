"""Probe real worker-owned file events without services or listening sockets."""

import os
import runpy
import signal
import sys
import tempfile
import threading
import traceback
from pathlib import Path
from threading import Event

from flask import Flask
from flaskr.framework.plugin import hot_reload
from flaskr.framework.plugin.plugin_manager import PluginManager, set_plugin_manager
from watchdog.observers import Observer

API_ROOT = Path(__file__).resolve().parents[3]


def check_worker_watcher() -> None:
    """Keep observers out of the master and receive real changes in its child."""
    observer_class = Observer
    if sys.platform == "darwin":
        # Linux retains native inotify. macOS's native FSEvents run loop cannot
        # restart after fork, so use watchdog's real portable observer there.
        from watchdog.observers.polling import PollingObserver

        observer_class = PollingObserver

    observer_owners = []

    class OwnedObserver(observer_class):
        """Record construction while retaining watchdog's real implementation."""

        def __init__(self) -> None:
            observer_owners.append(os.getpid())
            super().__init__(timeout=0.02)

    hot_reload.Observer = OwnedObserver
    app = Flask("threaded-plugin-watcher")
    app.config["ENV"] = "development"
    manager = PluginManager(app)
    set_plugin_manager(manager)
    config = runpy.run_path(str(API_ROOT / "gunicorn.conf.py"))
    with tempfile.TemporaryDirectory(prefix="plugin-threaded-fork-") as directory:
        os.chdir(directory)
        plugin_dir = Path("flaskr/plugins")
        plugin_dir.mkdir(parents=True)
        plugin_file = plugin_dir / "watcher_probe.py"
        plugin_file.write_text("value = 0\n", encoding="utf-8")
        master_threads = set(threading.enumerate())
        try:
            manager.enable_hot_reload()
            assert not observer_owners, "the preload master constructed an observer"
            assert manager.hot_reloader is None, "the preload master retained a watcher"
            assert set(threading.enumerate()) == master_threads
        except BaseException:
            manager.disable_hot_reload()
            raise

        child_pid = os.fork()
        if child_pid == 0:
            # Bound the child independently so a regression leaves no orphan.
            signal.signal(signal.SIGALRM, signal.SIG_DFL)
            signal.alarm(10)
            try:
                os.environ.pop("AI_SHIFU_PRELOAD_MASTER")
                config["post_worker_init"](object())
                reloader = manager.hot_reloader
                assert isinstance(reloader, hot_reload.PluginHotReloader)
                assert observer_owners == [os.getpid()]
                assert reloader.observer.is_alive()
                assert all(emitter.is_alive() for emitter in reloader.observer.emitters)
                config["post_worker_init"](object())
                assert observer_owners == [os.getpid()], (
                    "worker duplicated its observer"
                )

                file_seen = Event()
                event_owners = []

                def record_reload(path: str) -> None:
                    if Path(path).name == plugin_file.name:
                        event_owners.append(os.getpid())
                        file_seen.set()

                reloader.reload_plugin = record_reload
                plugin_file.write_text(
                    "value = 'changed in worker'\n", encoding="utf-8"
                )
                assert file_seen.wait(timeout=3), "worker missed a real file event"
                assert set(event_owners) == {os.getpid()}
                manager.disable_hot_reload()
                assert not reloader.observer.is_alive()
                print("worker plugin watcher ok", flush=True)
            except BaseException:
                traceback.print_exc()
                os._exit(1)
            os._exit(0)

        _, status = os.waitpid(child_pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0, "plugin watcher worker failed"
        assert not observer_owners, "master started an observer after forking"
        assert manager.hot_reloader is None


if __name__ == "__main__":
    check_worker_watcher()
