import importlib
import os
from flask import Flask
from inspect import isfunction, getmembers
from functools import wraps, partial


def inject(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        app = kwargs.get("app")
        if app:
            with app.app_context():
                return func(*args, **kwargs)
        return func(*args, **kwargs)

    wrapper.inject = True  # 设置标志属性
    return wrapper


def load_plugins_from_dir(app: Flask, plugins_dir: str):
    plugins = []
    app.logger.info("load plugins from: {}".format(plugins_dir))

    def load_from_directory(directory):
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if os.path.isdir(file_path):
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
                # get function with @inject
                for name, obj in getmembers(module, isfunction):
                    if hasattr(obj, "inject"):
                        app.logger.info(f"set inject for {name}")
                        # use partial to pass app parameter
                        wrapped_func = partial(inject(obj), app=app)
                        setattr(module, name, wrapped_func)
                        wrapped_func()

    with app.app_context():
        load_from_directory(plugins_dir)

    return plugins
