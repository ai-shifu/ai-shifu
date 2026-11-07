"""Coordinate Flask plugin registration and lifecycle."""

import os
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from flask import Flask

from .hot_reload import PluginHotReloader

P = ParamSpec("P")
R = TypeVar("R")


class PluginManager:
    """Coordinate backend plugin discovery and lifecycle events."""

    def __init__(self, app: Flask) -> None:
        """Initialize empty plugin registries and lifecycle state for the app."""
        app.logger.info("PluginManager init")
        self.app = app
        self.extension_functions = {}
        self.hot_reloader = None
        self.plugins = {}
        self.is_enabled = True

    def enable_hot_reload(self) -> None:
        """Start file watching in the process that will serve the app."""
        # Do not create observer threads or file descriptors in a preloaded
        # master: workers must construct and own their watchers after fork.
        if not self.is_enabled or os.environ.get("AI_SHIFU_PRELOAD_MASTER") == "1":
            return
        if not self.hot_reloader:
            self.hot_reloader = PluginHotReloader(self.app)
            self.hot_reloader.start()

    def disable_hot_reload(self) -> None:
        """Disable the hot reload."""
        if self.hot_reloader:
            self.hot_reloader.stop()
            self.hot_reloader = None

    def clear_extension(self, target_func_name: object) -> None:
        """Clear all registered functions for the specified extension point."""
        if target_func_name in self.extension_functions:
            del self.extension_functions[target_func_name]

    def register_extension(self, target_func_name: object, func: object) -> None:
        """Register an extension callback for a target function."""
        self.app.logger.info(
            "register_extension: %s -> %s", target_func_name, func.__name__
        )
        while hasattr(func, "__wrapped__"):
            self.app.logger.warning("func is wrapped %s", func.__name__)
            func = func.__wrapped__
        if target_func_name not in self.extension_functions:
            self.extension_functions[target_func_name] = []
        self.extension_functions[target_func_name].append(func)

    def execute_extensions(
        self, func_name: object, result: object, *args: object, **kwargs: object
    ) -> object:
        """Execute callbacks registered for a target function."""
        self.app.logger.info("execute_extensions: %s", func_name)
        if not self.is_enabled:
            return result
        if func_name in self.extension_functions:
            for func in self.extension_functions[func_name]:
                result = func(result, *args, **kwargs)
        return result


class _PluginManagerState:
    """Own the replaceable manager without rebinding module state."""

    def __init__(self) -> None:
        self.manager: PluginManager | None = None


_plugin_manager_state = _PluginManagerState()


def get_plugin_manager() -> PluginManager | None:
    """Return the process-local plugin manager, if it has been enabled."""
    return _plugin_manager_state.manager


def set_plugin_manager(manager: PluginManager | None) -> None:
    """Set the process-local plugin manager through its single owner."""
    _plugin_manager_state.manager = manager


def enable_plugin_manager(app: Flask) -> Flask:
    """Enable plugin manager."""
    app.logger.info("enable_plugin_manager")
    set_plugin_manager(PluginManager(app))
    return app


def disable_plugin_manager(app: Flask) -> Flask:
    """Disable plugin manager."""
    app.logger.info("disable_plugin_manager")
    manager = get_plugin_manager()
    if manager:
        manager.disable_hot_reload()
        manager.is_enabled = False
    return app


# extensible decorator
def extension(target_func_name: object) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a function with registered extension callbacks."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        manager = get_plugin_manager()
        if manager is None:
            message = "Plugin manager is not enabled"
            raise RuntimeError(message)
        manager.register_extension(target_func_name, func)
        return func

    return decorator


# extensible decorator
def extensible(func: Callable[P, R]) -> Callable[P, R]:
    """Decorate a function as an extension point."""

    @wraps(func)
    def wrapper(*args: object, **kwargs: object) -> R:
        result = func(*args, **kwargs)
        manager = get_plugin_manager()
        if manager is None:
            return result
        return manager.execute_extensions(func.__name__, result, *args, **kwargs)

    return wrapper
