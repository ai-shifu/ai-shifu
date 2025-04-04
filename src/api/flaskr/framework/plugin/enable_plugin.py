import os
from flask import Flask
import subprocess
import shutil
import click
from flask.cli import with_appcontext
from alembic import command
from alembic.config import Config
from .plugin_manager import plugin_manager


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
            return
        subprocess.run(["git", "clone", repo_url, dest_dir])

    @plugin.command(name="delete")
    @click.argument("repo_name")
    def delete(repo_name):
        """Delete a plugin by its repository name."""
        dest_dir = os.path.join("flaskr", "plugins", repo_name)
        if not os.path.exists(dest_dir):
            return
        shutil.rmtree(dest_dir)

    @plugin.command(name="list")
    def list():
        """List all plugins."""
        plugins_dir = os.path.join("flaskr", "plugins")
        plugins = [
            name
            for name in os.listdir(plugins_dir)
            if os.path.isdir(os.path.join(plugins_dir, name))
        ]
        for plugin in plugins:
            if plugin == "__pycache__":
                continue

    def get_plugin_migrations():
        """get plugin migrations"""
        plugins = []
        app.logger.info(
            f"plugin_manager.plugins: {len(plugin_manager.plugins.values())}"
        )
        for plugin in plugin_manager.plugins.values():
            app.logger.info(
                f"plugin: {plugin.name}, migration_dir: {plugin.migration_dir}"
            )
            if plugin.migration_dir and os.path.exists(plugin.migration_dir):
                plugins.append(plugin)
        return plugins

    @plugin.group(name="db")
    def plugin_db():
        """the plugin database management commands"""
        pass

    def get_version_table_name(plugin_name: str) -> str:
        """get version table name"""
        return f"alembic_version_plugin_{plugin_name.replace('-', '_')}"

    def get_alembic_config(plugin, version_table: str = None) -> Config:
        """get alembic config"""
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", plugin.migration_dir)
        alembic_cfg.set_main_option(
            "version_locations", plugin.migration_dir + "/versions"
        )

        # set plugin version table
        if version_table:
            app.logger.info(f"set version_table: {version_table}")
            alembic_cfg.set_main_option("version_table", version_table)

        return alembic_cfg

    def get_plugin_include_object(plugin_name: str):
        """generate plugin model filter function"""

        def include_object(object, name, type_, reflected, compare_to):
            if type_ == "table":
                return object.__module__.startswith(f"flaskr.plugins.{plugin_name}")
            return True

        return include_object

    @plugin_db.command(name="upgrade")
    @click.argument("plugin_name", required=False)
    @with_appcontext
    def upgrade(plugin_name):
        """upgrade the plugin database to the latest version"""
        plugins = get_plugin_migrations()

        for plugin in plugins:
            if plugin_name and plugin.name != plugin_name:
                continue

            click.echo(f"upgrading the plugin: {plugin.name}")

            version_table = get_version_table_name(plugin.name)
            alembic_cfg = get_alembic_config(plugin, version_table)
            command.upgrade(alembic_cfg, "head")

    @plugin_db.command(name="history")
    @click.argument("plugin_name")
    @with_appcontext
    def history(plugin_name):
        """view the migration history of the plugin"""
        plugins = get_plugin_migrations()
        for plugin in plugins:
            if plugin.name == plugin_name:
                click.echo(f"the migration history of the plugin: {plugin.name}")
                version_table = get_version_table_name(plugin.name)
                alembic_cfg = get_alembic_config(plugin, version_table)
                command.history(alembic_cfg)
                return

        click.echo(f"plugin not found: {plugin_name}")

    @plugin_db.command(name="migrate")
    @click.argument("plugin_name")
    @with_appcontext
    def migrate(plugin_name):
        """migrate the plugin database to the latest version"""
        plugins = get_plugin_migrations()
        for plugin in plugins:
            app.logger.info(f"plugin: {plugin.name}")
            if plugin.name == plugin_name:
                click.echo(f"migrating the plugin: {plugin.name}")
                version_table = get_version_table_name(plugin.name)
                alembic_cfg = get_alembic_config(plugin, version_table)
                command.revision(
                    alembic_cfg,
                    autogenerate=True,
                    message=f"Auto-generated migration for {plugin.name}",
                )

                return

        click.echo(f"plugin not found: {plugin_name}")
