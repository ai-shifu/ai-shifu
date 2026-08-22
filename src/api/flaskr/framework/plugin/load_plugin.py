"""Load configured Flask plugin modules."""

import importlib
import os
from functools import partial
from inspect import getmembers, isfunction
from pathlib import Path

from flask import Flask

from flaskr.framework.plugin.inject import inject
from flaskr.i18n import TRANSLATIONS_DEFAULT_NAME, load_translations

from .base import BasePlugin
from .plugin_manager import PluginManager

MIGRATION_DIR = "migrations"
SRC_DIR = "src"


def load_plugins_from_dir(
    app: Flask, plugins_dir: str, plugin_manager: PluginManager = None
):
    """Load plugins from dir."""
    plugins = []
    app.logger.info("load modules from: %s", plugins_dir)

    def load_from_directory(directory: object, plugin_manager: PluginManager = None):
        files = [path.name for path in Path(directory).iterdir()]
        plugin_obj = None
        if SRC_DIR in files:
            for filename in [
                path.name for path in (Path(directory) / SRC_DIR).iterdir()
            ]:
                if filename.endswith(".py"):
                    plugin_obj = importlib.import_module(
                        f"{directory}.{SRC_DIR}.{filename[:-3]}".replace(os.sep, ".")
                    )
                    for _name, obj in getmembers(plugin_obj):
                        if (
                            isinstance(obj, type)
                            and issubclass(obj, BasePlugin)
                            and obj is not BasePlugin
                        ):
                            plugin_define = obj()
                            if MIGRATION_DIR in files:
                                plugin_define.migration_dir = str(
                                    Path(directory) / MIGRATION_DIR
                                )
                            plugin_manager.plugins[plugin_define.name] = plugin_define
                            app.logger.info("load plugin: %s", plugin_define.name)
        for filename in files:
            if filename in ("__pycache__", MIGRATION_DIR) or filename.startswith("."):
                continue
            file_path = str(Path(directory) / filename)
            if filename == TRANSLATIONS_DEFAULT_NAME:
                load_translations(app, file_path)
            elif Path(file_path).is_dir():
                load_from_directory(file_path, plugin_manager)
            elif filename.endswith(".py") and filename != "__init__.py":
                module_name = filename[:-3]
                module_full_name = f"{directory}.{module_name}".replace(os.sep, ".")
                module = importlib.import_module(module_full_name)
                for name, obj in getmembers(module, isfunction):
                    if hasattr(obj, "inject"):
                        app.logger.info("set inject for %s", name)
                        wrapped_func = partial(inject(obj), app=app)
                        setattr(module, name, wrapped_func)
                        wrapped_func()

    with app.app_context():
        files = [path.name for path in Path(plugins_dir).iterdir()]
        for file in files:
            if (Path(plugins_dir) / file).is_dir():
                app.logger.info("begin load plugin: %s", file)
                try:
                    load_from_directory(str(Path(plugins_dir) / file), plugin_manager)
                    app.logger.info("load plugin: %s success", file)
                except Exception:
                    app.logger.exception("load plugin: %s error", file)
            else:
                app.logger.warning("skip non-directory file: %s", file)
    return plugins
