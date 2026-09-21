"""Exercise file watcher throttling and plugin lifecycle failure isolation."""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.framework.plugin import hot_reload, plugin_manager


@pytest.fixture
def reloader(monkeypatch: pytest.MonkeyPatch) -> hot_reload.PluginHotReloader:
    monkeypatch.setattr(hot_reload, "Observer", Mock())
    return hot_reload.PluginHotReloader(Flask(__name__))


def test_watcher_lifecycle_watches_plugins_recursively_and_joins_on_stop(
    reloader: hot_reload.PluginHotReloader,
) -> None:
    reloader.start()
    handler, directory = reloader.observer.schedule.call_args.args
    assert isinstance(handler, hot_reload.PluginFileHandler)
    assert handler.reloader is reloader
    assert directory == "flaskr/plugins"
    assert reloader.observer.schedule.call_args.kwargs == {"recursive": True}
    reloader.observer.start.assert_called_once_with()
    reloader.stop()
    reloader.observer.stop.assert_called_once_with()
    reloader.observer.join.assert_called_once_with()


@pytest.mark.parametrize(
    ("path", "is_directory"), [("plugin.py", True), ("plugin.txt", False)]
)
def test_non_source_changes_do_not_reload(path: str, is_directory: bool) -> None:
    reloader = Mock()
    handler = hot_reload.PluginFileHandler(reloader)
    handler.on_modified(SimpleNamespace(src_path=path, is_directory=is_directory))
    reloader.reload_plugin.assert_not_called()


def test_reload_throttling_is_per_file_and_allows_interval_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reloader = Mock()
    handler = hot_reload.PluginFileHandler(reloader)
    clock = Mock(side_effect=[10.0, 10.5, 10.5, 11.0])
    monkeypatch.setattr(hot_reload.time, "time", clock)
    for path in ["one.py", "one.py", "two.py", "one.py"]:
        handler.on_modified(SimpleNamespace(src_path=path, is_directory=False))
    assert [call.args[0] for call in reloader.reload_plugin.call_args_list] == [
        "one.py",
        "two.py",
        "one.py",
    ]


@pytest.mark.parametrize("has_hook", [False, True])
def test_unload_removes_only_target_module_and_extensions(
    reloader: hot_reload.PluginHotReloader,
    monkeypatch: pytest.MonkeyPatch,
    has_hook: bool,
) -> None:
    name = "flaskr.plugins.example"
    module = ModuleType(name)
    hook = Mock()
    if has_hook:
        module.Plugin = Mock(return_value=SimpleNamespace(on_unload=hook))
    manager = plugin_manager.PluginManager(reloader.app)
    manager.extension_functions = {f"{name}.event": [], "other.event": []}
    monkeypatch.setattr(plugin_manager, "get_plugin_manager", lambda: manager)
    monkeypatch.setitem(sys.modules, name, module)
    reloader._unload_plugin("flaskr/plugins/example.py")
    assert name not in sys.modules
    assert manager.extension_functions == {"other.event": []}
    assert hook.call_count == int(has_hook)
    reloader._unload_plugin("flaskr/plugins/example.py")


def test_unload_without_manager_leaves_module_available(
    reloader: hot_reload.PluginHotReloader, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = ModuleType("flaskr.plugins.example")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(plugin_manager, "get_plugin_manager", lambda: None)
    reloader._unload_plugin("flaskr/plugins/example.py")
    assert sys.modules[module.__name__] is module


def test_failing_unload_hook_is_logged_without_losing_module(
    reloader: hot_reload.PluginHotReloader, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = ModuleType("flaskr.plugins.example")
    module.Plugin = Mock(side_effect=RuntimeError("cannot unload"))
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(plugin_manager, "get_plugin_manager", Mock)
    logger = Mock()
    monkeypatch.setattr(reloader.app, "logger", logger)
    reloader._unload_plugin("flaskr/plugins/example.py")
    assert sys.modules[module.__name__] is module
    logger.exception.assert_called_once()


@pytest.mark.parametrize(
    "hooks", [(), ("on_load",), ("on_reload",), ("on_load", "on_reload")]
)
def test_register_invokes_available_hooks_in_lifecycle_order(
    reloader: hot_reload.PluginHotReloader, hooks: tuple[str, ...]
) -> None:
    events = []
    plugin = SimpleNamespace(
        **{name: lambda name=name: events.append(name) for name in hooks}
    )
    module = ModuleType("example")
    module.Plugin = lambda: plugin
    reloader._register_plugin(module)
    assert events == list(hooks)


def test_register_without_class_is_supported(
    reloader: hot_reload.PluginHotReloader,
) -> None:
    module = ModuleType("example")
    reloader._register_plugin(module)


def test_failed_load_hook_does_not_run_reload_hook(
    reloader: hot_reload.PluginHotReloader, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin = SimpleNamespace(
        on_load=Mock(side_effect=RuntimeError("load failed")), on_reload=Mock()
    )
    module = ModuleType("example")
    module.Plugin = lambda: plugin
    logger = Mock()
    monkeypatch.setattr(reloader.app, "logger", logger)
    reloader._register_plugin(module)
    plugin.on_reload.assert_not_called()
    logger.exception.assert_called_once()


@pytest.mark.parametrize("import_fails", [False, True])
def test_reload_coordinates_unload_import_and_registration(
    reloader: hot_reload.PluginHotReloader,
    monkeypatch: pytest.MonkeyPatch,
    import_fails: bool,
) -> None:
    events = []
    module = ModuleType("flaskr.plugins.example")

    def importer(name: str) -> ModuleType:
        events.append(("import", name))
        if import_fails:
            message = "module unavailable"
            raise ImportError(message)
        return module

    monkeypatch.setattr(
        reloader, "_unload_plugin", lambda path: events.append(("unload", path))
    )
    monkeypatch.setattr(hot_reload.importlib, "import_module", importer)
    monkeypatch.setattr(
        hot_reload.importlib, "reload", lambda value: events.append(("reload", value))
    )
    monkeypatch.setattr(
        reloader, "_register_plugin", lambda value: events.append(("register", value))
    )
    reloader.reload_plugin("flaskr/plugins/example.py")
    expected = [("unload", "flaskr/plugins/example.py"), ("import", module.__name__)]
    if not import_fails:
        expected.extend([("reload", module), ("register", module)])
    assert events == expected
