from flask import Flask

# 在模块的开头声明 plugin_manager
plugin_manager = None


class PluginManager:
    def __init__(self, app: Flask):
        self.app = app
        self.extension_functions = {}

    def register_extension(self, target_func_name, func):
        self.app.logger.info(f"register_extension: {target_func_name} -> {func}")
        if target_func_name not in self.extension_functions:
            self.extension_functions[target_func_name] = []
        self.extension_functions[target_func_name].append(func)

    def execute_extensions(self, func_name, result, *args, **kwargs):
        self.app.logger.info(f"execute_extensions: {func_name}")
        if func_name in self.extension_functions:
            for func in self.extension_functions[func_name]:
                result = func(result, *args, **kwargs)
        return result


def enable_plugin_manager(app: Flask):
    app.logger.info("enable_plugin_manager")
    global plugin_manager
    plugin_manager = PluginManager(app)
    return app


def extensible(func):
    def wrapper(*args, **kwargs):
        global plugin_manager
        result = func(*args, **kwargs)
        result = plugin_manager.execute_extensions(
            func.__name__, result, *args, **kwargs
        )
        return result

    return wrapper


def extension(target_func_name):
    def decorator(func):
        plugin_manager.register_extension(target_func_name, func)
        return func

    return decorator
