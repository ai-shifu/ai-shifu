"""Run the real plugin watcher lifecycle without services or listening sockets."""

from gevent import monkey

monkey.patch_all()

import os  # noqa: E402
import signal  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
from pathlib import Path  # noqa: E402
from types import TracebackType  # noqa: E402

import gevent  # noqa: E402
from flask import Flask  # noqa: E402
from gevent.event import Event  # noqa: E402
from watchdog.observers import Observer  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from flaskr.framework.plugin import hot_reload  # noqa: E402
from flaskr.framework.plugin.plugin_manager import PluginManager  # noqa: E402


def check_worker_watcher() -> None:
    """Fork before creating an observer, then require file events and hub progress."""
    observer_class = Observer
    if sys.platform == "darwin":
        # FSEvents runs a blocking C run loop that gevent cannot monkey-patch.
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
    app = Flask("gevent-plugin-watcher")
    app.config["ENV"] = "development"
    app.extensions["serving_http"] = True
    manager = PluginManager(app)
    hub_errors = []
    hub = gevent.get_hub()
    previous_handler = hub.handle_error

    def record_hub_error(
        context: object,
        kind: type[BaseException],
        value: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        hub_errors.append((kind.__name__, str(value)))
        previous_handler(context, kind, value, traceback)

    hub.handle_error = record_hub_error

    with tempfile.TemporaryDirectory(prefix="plugin-gevent-fork-") as directory:
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
            # A blocking native watcher can freeze cooperative deadlines.
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
                gevent.spawn_later(0.02, timer_seen.set)
                plugin_file.write_text(
                    "value = 'changed in worker'\n", encoding="utf-8"
                )
                assert timer_seen.wait(timeout=3), "the worker hub timer stalled"
                assert file_seen.wait(timeout=3), (
                    "the worker did not receive a real file event"
                )
                assert event_owners
                assert set(event_owners) == {os.getpid()}
                manager.disable_hot_reload()
                gevent.sleep(0)
                assert not hub_errors, f"worker hub callback errors: {hub_errors}"
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
        assert not hub_errors, f"master hub callback errors: {hub_errors}"


if __name__ == "__main__":
    check_worker_watcher()
