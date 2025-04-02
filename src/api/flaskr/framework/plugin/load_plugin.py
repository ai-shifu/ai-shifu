import importlib
import os
from flask import Flask
from inspect import isfunction, getmembers
from functools import partial
from flaskr.framework.plugin.inject import inject
from flaskr.i18n import load_translations, TRANSLATIONS_DEFAULT_NAME
from .plugin_manager import PluginManager
from .base import BasePlugin

MIGRATION_DIR = "migrations"
SRC_DIR = "src"


def load_plugins_from_dir(
    app: Flask, plugins_dir: str, plugin_manager: PluginManager = None
):
    plugins = []
    app.logger.info("load modules from: {}".format(plugins_dir))

    def load_from_directory(directory, plugin_manager: PluginManager = None):
        files = os.listdir(directory)
        plugin_obj = None
        if SRC_DIR in files:
            for filename in os.listdir(os.path.join(directory, SRC_DIR)):
                if filename.endswith(".py"):
                    plugin_obj = importlib.import_module(
                        f"{directory}.{SRC_DIR}.{filename[:-3]}".replace(os.sep, ".")
                    )
                    for name, obj in getmembers(plugin_obj):
                        if (
                            isinstance(obj, type)
                            and issubclass(obj, BasePlugin)
                            and obj is not BasePlugin
                        ):
                            plugin_define = obj()
                            if MIGRATION_DIR in files:
                                plugin_define.migration_dir = os.path.join(
                                    directory, MIGRATION_DIR
                                )
                            plugin_manager.plugins[plugin_define.name] = plugin_define
                            app.logger.info(f"load plugin: {plugin_define.name}")
        for filename in files:
            if filename in ("__pycache__", MIGRATION_DIR) or filename.startswith("."):
                continue
            file_path = os.path.join(directory, filename)
            if filename == TRANSLATIONS_DEFAULT_NAME:
                load_translations(app, file_path)
            elif os.path.isdir(file_path):
                load_from_directory(file_path, plugin_manager)
            elif filename.endswith(".py") and filename != "__init__.py":
                module_name = filename[:-3]
                module_full_name = f"{directory}.{module_name}".replace(os.sep, ".")
                module = importlib.import_module(module_full_name)
                for name, obj in getmembers(module, isfunction):
                    if hasattr(obj, "inject"):
                        app.logger.info(f"set inject for {name}")
                        wrapped_func = partial(inject(obj), app=app)
                        setattr(module, name, wrapped_func)
                        wrapped_func()

    with app.app_context():
        load_from_directory(plugins_dir, plugin_manager)
    return plugins
