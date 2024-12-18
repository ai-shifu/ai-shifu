import importlib
import os
from flask import Flask
from inspect import isfunction, getmembers
from functools import partial
from flaskr.framework.plugin.inject import inject
from flaskr.i18n import load_translations, TRANSLATIONS_DEFAULT_NAME


def load_plugins_from_dir(app: Flask, plugins_dir: str):
    plugins = []
    app.logger.info("load plugins from: {}".format(plugins_dir))

    def load_from_directory(directory):
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if filename != "__pycache__" and filename[0] != ".":
                if filename == TRANSLATIONS_DEFAULT_NAME:
                    load_translations(app, file_path)
                elif os.path.isdir(file_path):
                    load_from_directory(file_path)
                elif filename.endswith(".py") and filename != "__init__.py":
                    module_name = filename[:-3]
                    module_full_name = f"{directory}.{module_name}".replace(
                        "/", "."
                    ).replace("\\", ".")
                    module = importlib.import_module(module_full_name)
                    if hasattr(module, "Plugin"):
                        plugin_class = getattr(module, "Plugin")
                        plugins.append(plugin_class())
                    for name, obj in getmembers(module, isfunction):
                        if hasattr(obj, "inject"):
                            app.logger.info(f"set inject for {name}")
                            wrapped_func = partial(inject(obj), app=app)
                            setattr(module, name, wrapped_func)
                            wrapped_func()

    with app.app_context():
        load_from_directory(plugins_dir)
    return plugins
