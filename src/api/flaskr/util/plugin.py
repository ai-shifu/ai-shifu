import importlib
import os
from flask import Flask


def load_plugins_from_dir(app: Flask, plugins_dir: str):
    plugins = []
    app.logger.info("load plugins from: {}".format(plugins_dir))
    for filename in os.listdir(plugins_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            module_full_name = f"{plugins_dir}.{module_name}".replace("/", ".").replace(
                "\\", "."
            )
            module = importlib.import_module(module_full_name)
            if hasattr(module, "Plugin"):
                plugin_class = getattr(module, "Plugin")
                plugins.append(plugin_class())
    return plugins


def load_plugins_from_module(module_name: str):
    module = importlib.import_module(module_name)
    if hasattr(module, "Plugin"):
        plugin_class = getattr(module, "Plugin")
        return plugin_class()
    return None


def load_plugins_from_file(file_name: str):
    plugins_dir = os.path.dirname(file_name)
    for filename in os.listdir(plugins_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            module_full_name = f"plugins.{module_name}"
            module = importlib.import_module(module_full_name)
            if hasattr(module, "Plugin"):
                plugin_class = getattr(module, "Plugin")
                return plugin_class()
    return None
