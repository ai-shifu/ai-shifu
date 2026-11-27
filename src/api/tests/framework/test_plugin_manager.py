"""Exercise plugin callback ordering, lifecycle, and application isolation."""

from collections.abc import Iterator
from functools import wraps
from unittest.mock import Mock

import pytest
from flask import Flask, current_app, has_app_context
from flaskr.framework.plugin import plugin_manager as manager_module
from flaskr.framework.plugin.base import BasePlugin
from flaskr.framework.plugin.inject import inject
from flaskr.framework.plugin.plugin_manager import (
    PluginManager,
    disable_plugin_manager,
    enable_plugin_manager,
    extensible,
    extension,
    get_plugin_manager,
    set_plugin_manager,
)


@pytest.fixture
def manager() -> Iterator[PluginManager]:
    previous = get_plugin_manager()
    instance = PluginManager(Flask(__name__))
    set_plugin_manager(instance)
    try:
        yield instance
    finally:
        set_plugin_manager(previous)


def test_extensions_transform_results_in_registration_order(
    manager: PluginManager,
) -> None:
    calls = []

    @extensible
    def price(amount: int, *, discount: int) -> int:
        return amount - discount

    @extension("price")
    def double(result: int, amount: int, *, discount: int) -> int:
        calls.append(("double", result, amount, discount))
        return result * 2

    @extension("price")
    def add_fee(result: int, amount: int, *, discount: int) -> int:
        calls.append(("fee", result, amount, discount))
        return result + 3

    assert price(10, discount=2) == 19
    assert calls == [("double", 8, 10, 2), ("fee", 16, 10, 2)]
    manager.clear_extension("price")
    manager.clear_extension("missing")
    assert price(10, discount=2) == 8


def test_disabled_manager_does_not_invoke_extensions(manager: PluginManager) -> None:
    callback = Mock(__name__="callback")
    manager.register_extension("price", callback)
    manager.is_enabled = False
    assert manager.execute_extensions("price", 7) == 7
    callback.assert_not_called()


def test_extensible_preserves_metadata_and_works_without_manager(
    manager: PluginManager,
) -> None:
    _ = manager

    @extensible
    def plain(value: int) -> int:
        """Return a public callback result."""
        return value + 1

    set_plugin_manager(None)
    assert plain(4) == 5
    assert plain.__name__ == "plain"
    assert plain.__doc__ == "Return a public callback result."


def test_registration_requires_enabled_manager(manager: PluginManager) -> None:
    _ = manager
    set_plugin_manager(None)
    with pytest.raises(RuntimeError, match="Plugin manager is not enabled"):
        extension("example")(lambda result: result)


def test_registration_unwraps_decorators_to_avoid_recursive_dispatch(
    manager: PluginManager,
) -> None:
    def original(result: int) -> list[int]:
        return [result + 1]

    @wraps(original)
    def wrapper(result: int) -> list[int]:
        pytest.fail(f"registration must invoke the original callback for {result}")

    manager.register_extension("example", wrapper)
    assert manager.execute_extensions("example", 3) == [4]


def test_hot_reload_starts_once_and_stops_on_disable(
    manager: PluginManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    reloader = Mock()
    factory = Mock(return_value=reloader)
    monkeypatch.setattr(manager_module, "PluginHotReloader", factory)
    manager.enable_hot_reload()
    manager.enable_hot_reload()
    factory.assert_called_once_with(manager.app)
    reloader.start.assert_called_once_with()
    assert disable_plugin_manager(manager.app) is manager.app
    reloader.stop.assert_called_once_with()
    manager.disable_hot_reload()
    manager.enable_hot_reload()
    assert manager.hot_reloader is None
    assert not manager.is_enabled
    assert factory.call_count == 1


@pytest.mark.parametrize("preload_role", [None, "0", "1"])
def test_hot_reload_constructs_observer_only_outside_preload_master(
    manager: PluginManager, monkeypatch: pytest.MonkeyPatch, preload_role: str | None
) -> None:
    if preload_role is None:
        monkeypatch.delenv("AI_SHIFU_PRELOAD_MASTER", raising=False)
    else:
        monkeypatch.setenv("AI_SHIFU_PRELOAD_MASTER", preload_role)
    factory = Mock()
    monkeypatch.setattr(manager_module, "PluginHotReloader", factory)

    manager.enable_hot_reload()

    if preload_role == "1":
        factory.assert_not_called()
        assert manager.hot_reloader is None
    else:
        factory.assert_called_once_with(manager.app)
        factory.return_value.start.assert_called_once_with()


def test_enable_replaces_manager_and_disable_without_manager_is_safe(
    manager: PluginManager,
) -> None:
    app = manager.app
    set_plugin_manager(None)
    assert disable_plugin_manager(app) is app
    assert enable_plugin_manager(app) is app
    replacement = get_plugin_manager()
    assert replacement is not manager
    assert replacement.app is app
    assert replacement.is_enabled


@pytest.mark.parametrize("provide_app", [False, True])
def test_inject_restores_application_context_after_callback(provide_app: bool) -> None:
    app = Flask(__name__)

    @inject
    def callback(value: str, **kwargs: object) -> str:
        assert has_app_context() is provide_app
        if provide_app:
            assert current_app._get_current_object() is kwargs["app"]
        return value.upper()

    assert callback("result", **({"app": app} if provide_app else {})) == "RESULT"
    assert callback.inject
    assert callback.__name__ == "callback"
    assert not has_app_context()


def test_inject_unwinds_context_when_callback_fails() -> None:
    @inject
    def callback(**kwargs: object) -> None:
        assert current_app._get_current_object() is kwargs["app"]
        message = "callback failed"
        raise ValueError(message)

    with pytest.raises(ValueError, match="callback failed"):
        callback(app=Flask(__name__))
    assert not has_app_context()


@pytest.mark.parametrize("migration_dir", [None, "plugin/migrations"])
def test_base_plugin_migrates_only_when_configured(
    monkeypatch: pytest.MonkeyPatch, migration_dir: str | None
) -> None:
    from alembic import command

    upgrade = Mock()
    monkeypatch.setattr(command, "upgrade", upgrade)
    plugin = BasePlugin()
    assert plugin.name == "BasePlugin"
    assert plugin.migration_dir is None
    plugin.migration_dir = migration_dir
    plugin.on_load()
    plugin.on_unload()
    plugin.on_reload()
    if migration_dir:
        config, revision = upgrade.call_args.args
        assert revision == "head"
        assert config.get_main_option("script_location") == migration_dir
        assert (
            config.get_main_option("version_locations") == f"{migration_dir}/versions"
        )
    else:
        upgrade.assert_not_called()
