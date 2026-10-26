"""Exercise plugin discovery and operator commands without network or DDL."""

import importlib
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask, current_app
from flaskr.framework.plugin.base import BasePlugin
from flaskr.framework.plugin.inject import inject
from flaskr.framework.plugin.plugin_manager import PluginManager

commands = importlib.import_module("flaskr.framework.plugin.enable_plugin")
loader = importlib.import_module("flaskr.framework.plugin.load_plugin")


@pytest.fixture
def plugin_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Flask:
    monkeypatch.chdir(tmp_path)
    app = Flask(__name__)
    manager = PluginManager(app)
    monkeypatch.setattr(commands, "get_plugin_manager", lambda: manager)
    commands.enable_plugins(app)
    app.extensions["test_plugin_manager"] = manager
    return app


def test_cli_registration_requires_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(commands, "get_plugin_manager", lambda: None)
    with pytest.raises(RuntimeError, match="Plugin manager is not enabled"):
        commands.enable_plugins(Flask(__name__))


@pytest.mark.parametrize("exists", [False, True])
def test_add_clones_only_missing_plugin(
    plugin_app: Flask, monkeypatch: pytest.MonkeyPatch, exists: bool
) -> None:
    destination = Path("flaskr/plugins/example")
    if exists:
        destination.mkdir(parents=True)
    clone = Mock()
    monkeypatch.setattr(commands.shutil, "which", lambda name: f"/tools/{name}")
    monkeypatch.setattr(commands.subprocess, "run", clone)
    result = plugin_app.test_cli_runner().invoke(
        args=["plugin", "add", "https://example.invalid/example.git"]
    )
    assert result.exit_code == 0
    if exists:
        clone.assert_not_called()
    else:
        clone.assert_called_once_with(
            [
                "/tools/git",
                "clone",
                "https://example.invalid/example.git",
                str(destination),
            ],
            check=False,
        )


def test_add_reports_missing_git(
    plugin_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commands.shutil, "which", lambda _: None)
    result = plugin_app.test_cli_runner().invoke(
        args=["plugin", "add", "https://example.invalid/example.git"]
    )
    assert result.exit_code == 1
    assert "git is not available on PATH" in result.output


@pytest.mark.parametrize("exists", [False, True])
def test_delete_removes_only_named_plugin(plugin_app: Flask, exists: bool) -> None:
    target = Path("flaskr/plugins/example")
    other = Path("flaskr/plugins/other")
    other.mkdir(parents=True)
    if exists:
        target.mkdir()
        (target / "module.py").write_text("", encoding="utf-8")
    result = plugin_app.test_cli_runner().invoke(args=["plugin", "delete", "example"])
    assert result.exit_code == 0
    assert not target.exists()
    assert other.is_dir()


def test_list_tolerates_cache_and_non_directory_files(plugin_app: Flask) -> None:
    directory = Path("flaskr/plugins")
    (directory / "example").mkdir(parents=True)
    (directory / "__pycache__").mkdir()
    (directory / "README.md").write_text("plugins", encoding="utf-8")
    result = plugin_app.test_cli_runner().invoke(args=["plugin", "list"])
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("operation", "name", "expected"),
    [
        ("upgrade", None, 2),
        ("upgrade", "one-plugin", 1),
        ("upgrade", "missing", 0),
        ("history", "one-plugin", 1),
        ("history", "missing", 0),
        ("migrate", "one-plugin", 1),
        ("migrate", "missing", 0),
    ],
)
def test_migration_commands_select_plugin_and_isolate_version_tables(
    plugin_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    name: str | None,
    expected: int,
) -> None:
    manager = plugin_app.extensions["test_plugin_manager"]
    for plugin_name, directory in [
        ("one-plugin", "migrations/one"),
        ("two-plugin", "migrations/two"),
        ("missing-directory", "missing"),
        ("no-migrations", None),
    ]:
        if directory and directory.startswith("migrations/"):
            Path(directory).mkdir(parents=True)
        manager.plugins[plugin_name] = SimpleNamespace(
            name=plugin_name, migration_dir=directory
        )
    action = Mock()
    monkeypatch.setattr(
        commands.command, "revision" if operation == "migrate" else operation, action
    )
    args = ["plugin", "db", operation] + ([name] if name else [])
    result = plugin_app.test_cli_runner().invoke(args=args)
    assert result.exit_code == 0, result.output
    assert action.call_count == expected
    for call, suffix in zip(action.call_args_list, ["one", "two"], strict=False):
        config = call.args[0]
        assert config.get_main_option("script_location") == f"migrations/{suffix}"
        assert (
            config.get_main_option("version_locations")
            == f"migrations/{suffix}/versions"
        )
        assert (
            config.get_main_option("version_table")
            == f"alembic_version_plugin_{suffix}_plugin"
        )
        if operation == "upgrade":
            assert call.args[1] == "head"
        elif operation == "migrate":
            assert call.kwargs == {
                "autogenerate": True,
                "message": f"Auto-generated migration for {suffix}-plugin",
            }
    if operation != "upgrade" and name == "missing":
        assert "plugin not found: missing" in result.output


def test_discovery_registers_plugin_migrations_translations_and_injected_callbacks(
    plugin_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_root = Path("plugins/example")
    for directory in (
        "src",
        "migrations",
        "__pycache__",
        ".hidden",
        loader.TRANSLATIONS_DEFAULT_NAME,
    ):
        (plugin_root / directory).mkdir(parents=True)
    (plugin_root / "src" / "entry.py").write_text("", encoding="utf-8")
    (plugin_root / "src" / "notes.txt").write_text("", encoding="utf-8")
    (plugin_root / "__init__.py").write_text("", encoding="utf-8")
    (plugin_root / "callbacks.py").write_text("", encoding="utf-8")
    Path("plugins/README.md").write_text("", encoding="utf-8")
    plugin_module = ModuleType("plugins.example.src.entry")
    callback_module = ModuleType("plugins.example.callbacks")
    calls = []

    class ExamplePlugin(BasePlugin):
        pass

    @inject
    def register(*, app: Flask) -> None:
        assert current_app._get_current_object() is app
        calls.append(app)

    plugin_module.ExamplePlugin = ExamplePlugin
    callback_module.register = register
    modules = {
        plugin_module.__name__: plugin_module,
        callback_module.__name__: callback_module,
    }
    importer = Mock(side_effect=modules.__getitem__)
    monkeypatch.setattr(loader.importlib, "import_module", importer)
    translations = Mock()
    monkeypatch.setattr(loader, "load_translations", translations)
    manager = plugin_app.extensions["test_plugin_manager"]
    loader.load_plugins_from_dir(plugin_app, "plugins", manager)
    assert list(manager.plugins) == ["ExamplePlugin"]
    assert (
        manager.plugins["ExamplePlugin"].migration_dir == "plugins/example/migrations"
    )
    assert calls == [plugin_app]
    translations.assert_called_once_with(
        plugin_app, str(plugin_root / loader.TRANSLATIONS_DEFAULT_NAME)
    )
    assert {call.args[0] for call in importer.call_args_list} == set(modules)


def test_discovery_logs_one_broken_plugin_and_keeps_loading_others(
    plugin_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("broken", "working"):
        directory = Path("plugins") / name
        directory.mkdir(parents=True)
        (directory / "entry.py").write_text("", encoding="utf-8")
    visited = []

    def importer(name: str) -> ModuleType:
        visited.append(name)
        if ".broken." in name:
            message = "invalid plugin"
            raise ImportError(message)
        return ModuleType(name)

    monkeypatch.setattr(loader.importlib, "import_module", importer)
    logger = Mock()
    monkeypatch.setattr(plugin_app, "logger", logger)
    loader.load_plugins_from_dir(
        plugin_app, "plugins", plugin_app.extensions["test_plugin_manager"]
    )
    assert set(visited) == {"plugins.broken.entry", "plugins.working.entry"}
    logger.exception.assert_called_once()
