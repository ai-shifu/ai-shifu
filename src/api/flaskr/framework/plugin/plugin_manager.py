"""Coordinate Flask plugin registration and lifecycle."""

from functools import wraps

from flask import Flask

from .hot_reload import PluginHotReloader


class PluginManager:
    """Coordinate backend plugin discovery and lifecycle events."""

    def __init__(self: object, app: Flask) -> None:
        """Initialize empty plugin registries and lifecycle state for the app."""
        app.logger.info("PluginManager init")
        self.app = app
        self.extension_functions = {}
        self.extensible_generic_functions = {}
        self.hot_reloader = None
        self.plugins = {}
        self.is_enabled = True

    def enable_hot_reload(self: object):
        """Enable the hot reload."""
        if not self.is_enabled:
            return
        if not self.hot_reloader:
            self.hot_reloader = PluginHotReloader(self.app)
            self.hot_reloader.start()

    def disable_hot_reload(self: object):
        """Disable the hot reload."""
        if self.hot_reloader:
            self.hot_reloader.stop()
            self.hot_reloader = None

    def clear_extension(self: object, target_func_name: object):
        """Clear all registered functions for the specified extension point."""
        if target_func_name in self.extension_functions:
            del self.extension_functions[target_func_name]

    def register_extension(self: object, target_func_name: object, func: object):
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
        self: object, func_name: object, result: object, *args: object, **kwargs: object
    ):
        """Execute callbacks registered for a target function."""
        self.app.logger.info("execute_extensions: %s", func_name)
        if not self.is_enabled:
            return result
        if func_name in self.extension_functions:
            for func in self.extension_functions[func_name]:
                result = func(result, *args, **kwargs)
        return result

    def register_extensible_generic(self: object, func_name: object, func: object):
        """Register a generic extensible function."""
        self.app.logger.info(
            "register_extensible_generic: %s -> %s", func_name, func.__name__
        )
        while hasattr(func, "__wrapped__"):
            self.app.logger.warning("func is wrapped %s", func.__name__)
            func = func.__wrapped__
        if func_name not in self.extensible_generic_functions:
            self.extensible_generic_functions[func_name] = []
        self.extensible_generic_functions[func_name].append(func)

    def execute_extensible_generic(
        self: object,
        func_name: object,
        result: object,
        *args: object,
        **kwargs: object,
    ):
        """Run registered generic extension callbacks for a completed generic operation."""
        self.app.logger.info("execute_extensible_generic: %s", func_name)
        if not self.is_enabled:
            return result
        if func_name in self.extensible_generic_functions:
            for runc in self.extensible_generic_functions[func_name]:
                func = runc
                while hasattr(func, "__wrapped__"):
                    self.app.logger.warning("func is wrapped %s", func.__name__)
                    func = func.__wrapped__
                result = func(result, *args, **kwargs)
                if result:
                    yield from result
        return None


class _PluginManagerState:
    """Own the replaceable manager without rebinding module state."""

    def __init__(self: object) -> None:
        self.manager: PluginManager | None = None


_plugin_manager_state = _PluginManagerState()


def get_plugin_manager() -> PluginManager | None:
    """Return the process-local plugin manager, if it has been enabled."""
    return _plugin_manager_state.manager


def set_plugin_manager(manager: PluginManager | None) -> None:
    """Set the process-local plugin manager through its single owner."""
    _plugin_manager_state.manager = manager


def enable_plugin_manager(app: Flask):
    """Enable plugin manager."""
    app.logger.info("enable_plugin_manager")
    set_plugin_manager(PluginManager(app))
    return app


def disable_plugin_manager(app: Flask):
    """Disable plugin manager."""
    app.logger.info("disable_plugin_manager")
    manager = get_plugin_manager()
    if manager:
        manager.disable_hot_reload()
        manager.is_enabled = False
    return app


# extensible decorator
def extension(target_func_name: object):
    """Decorate a function with registered extension callbacks."""

    def decorator(func: object):
        manager = get_plugin_manager()
        if manager is None:
            message = "Plugin manager is not enabled"
            raise RuntimeError(message)
        manager.register_extension(target_func_name, func)
        return func

    return decorator


def extensible_generic_register(func_name: object):
    """Register a generic extension point."""

    def decorator(func: object):
        manager = get_plugin_manager()
        if manager is None:
            message = "Plugin manager is not enabled"
            raise RuntimeError(message)
        manager.register_extensible_generic(func_name, func)
        return func

    return decorator


# extensible decorator
def extensible(func: object):
    """Decorate a function as an extension point."""

    @wraps(func)
    def wrapper(*args: object, **kwargs: object):
        result = func(*args, **kwargs)
        manager = get_plugin_manager()
        if manager is None:
            return result
        return manager.execute_extensions(func.__name__, result, *args, **kwargs)

    return wrapper


# extensible_generic decorator
def extensible_generic(func: object):
    """Decorate a generic function as an extension point."""
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            current_app.logger.info("extensible_generic: %s", func.__name__)
    except ImportError:
        pass

    @wraps(func)
    def wrapper(*args: object, **kwargs: object):
        result = func(*args, **kwargs)
        if result:
            yield from result
        manager = get_plugin_manager()
        if manager is None:
            return
        if func.__name__ in manager.extensible_generic_functions:
            result = manager.execute_extensible_generic(func.__name__, *args, **kwargs)
            if result:
                yield from result

    return wrapper
