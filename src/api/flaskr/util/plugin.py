import importlib
import os
from flask import Flask
from inspect import isfunction, getmembers
from functools import wraps, partial
import subprocess
import shutil
import click


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


def enable_plugins(app: Flask):
    @app.cli.group()
    def plugin():
        """Plugin management commands."""
        pass

    @plugin.command(name="add")
    @click.argument("repo_url")
    def add(repo_url):
        """Add a plugin by cloning the repository."""
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        dest_dir = os.path.join("flaskr", "plugins", repo_name)
        if os.path.exists(dest_dir):
            print(f"Plugin {repo_name} already exists.")
            return
        subprocess.run(["git", "clone", repo_url, dest_dir])
        print(f"Plugin {repo_name} added.")

    @plugin.command(name="delete")
    @click.argument("repo_name")
    def delete(repo_name):
        """Delete a plugin by its repository name."""
        dest_dir = os.path.join("flaskr", "plugins", repo_name)
        if not os.path.exists(dest_dir):
            print(f"Plugin {repo_name} does not exist.")
            return
        shutil.rmtree(dest_dir)
        print(f"Plugin {repo_name} deleted.")

    @plugin.command(name="list")
    def list():
        """List all plugins."""
        plugins_dir = os.path.join("flaskr", "plugins")
        plugins = [
            name
            for name in os.listdir(plugins_dir)
            if os.path.isdir(os.path.join(plugins_dir, name))
        ]
        print("Installed plugins:")
        for plugin in plugins:
            if plugin == "__pycache__":
                continue
            print(f"- {plugin}")

    return plugin
