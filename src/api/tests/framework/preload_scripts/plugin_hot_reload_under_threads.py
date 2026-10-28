"""Run the real plugin watcher lifecycle without services or listening sockets."""

import os
import signal
import sys
import tempfile
import threading
from pathlib import Path
from threading import Event, Timer

from flask import Flask
from watchdog.observers import Observer

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from flaskr.framework.plugin import hot_reload
from flaskr.framework.plugin.plugin_manager import PluginManager


def check_worker_watcher() -> None:
    """Fork before creating an observer, then require file events and timer progress."""
    observer_class = Observer
    if sys.platform == "darwin":
        # Use a fork-safe portable observer on macOS.
        # Linux CI retains its native InotifyObserver; macOS uses watchdog's
        # real polling implementation to exercise the same Thread lifecycle.
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
    app.extensions["serving_http"] = True
    manager = PluginManager(app)
    with tempfile.TemporaryDirectory(prefix="plugin-threaded-fork-") as directory:
        os.chdir(directory)
        plugin_dir = Path("flaskr/plugins")
        plugin_dir.mkdir(parents=True)
        plugin_file = plugin_dir / "watcher_probe.py"
        plugin_file.write_text("value = 0\n", encoding="utf-8")
        os.environ["AI_SHIFU_PRELOAD_MASTER"] = "1"
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
            # Bound the child independently of its watcher threads.
            # Bound the child independently so a regression leaves no orphan.
            signal.signal(signal.SIGALRM, signal.SIG_DFL)
            signal.alarm(10)
            try:
                os.environ.pop("AI_SHIFU_PRELOAD_MASTER")
                manager.enable_hot_reload()
                reloader = manager.hot_reloader
                assert isinstance(reloader, hot_reload.PluginHotReloader)
                assert observer_owners == [os.getpid()]
                assert reloader.observer.is_alive()
                assert all(emitter.is_alive() for emitter in reloader.observer.emitters)
                manager.enable_hot_reload()
                assert observer_owners == [os.getpid()], (
                    "worker initialization duplicated its observer"
                )

                file_seen = Event()
                timer_seen = Event()
                event_owners = []

                def record_reload(path: str) -> None:
                    # Observe the real application's file-handler callback
                    # without importing the temporary fixture as a plugin.
                    if Path(path).name == plugin_file.name:
                        event_owners.append(os.getpid())
                        file_seen.set()

                reloader.reload_plugin = record_reload
                Timer(0.02, timer_seen.set).start()
                plugin_file.write_text(
                    "value = 'changed in worker'\n", encoding="utf-8"
                )
                assert timer_seen.wait(timeout=3), "the worker timer stalled"
                assert file_seen.wait(timeout=3), (
                    "the worker did not receive a real file event"
                )
                assert event_owners
                assert set(event_owners) == {os.getpid()}
                manager.disable_hot_reload()
                print("worker plugin watcher ok", flush=True)
            except BaseException:
                import traceback

                traceback.print_exc()
                os._exit(1)
            os._exit(0)

        _, status = os.waitpid(child_pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0, (
            "the plugin watcher worker failed"
        )
        assert not observer_owners, "the master started an observer after forking"
        assert manager.hot_reloader is None


if __name__ == "__main__":
    check_worker_watcher()
