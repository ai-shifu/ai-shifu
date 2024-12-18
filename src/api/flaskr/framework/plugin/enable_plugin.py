import os
from flask import Flask
import subprocess
import shutil
import click


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
