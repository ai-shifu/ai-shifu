import shutil
import subprocess
from pathlib import Path

import click
from alembic import command
from alembic.config import Config
from flask import Flask
from flask.cli import with_appcontext

from .plugin_manager import plugin_manager


def enable_plugins(app: Flask):
    @app.cli.group()
    def plugin():
        """Plugin management commands."""

    @plugin.command(name="add")
    @click.argument("repo_url")
    def add(repo_url):
        """Add a plugin by cloning the repository."""
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        dest_dir = str(Path("flaskr") / "plugins" / repo_name)
        if Path(dest_dir).exists():
            return
        git_executable = shutil.which("git")
        if git_executable is None:
            raise click.ClickException("git is not available on PATH")
        # The repository URL is supplied by the operator running this CLI command.
        subprocess.run([git_executable, "clone", repo_url, dest_dir], check=False)  # noqa: S603

    @plugin.command(name="delete")
    @click.argument("repo_name")
    def delete(repo_name):
        """Delete a plugin by its repository name."""
        dest_dir = str(Path("flaskr") / "plugins" / repo_name)
        if not Path(dest_dir).exists():
            return
        shutil.rmtree(dest_dir)

    @plugin.command(name="list")
    def list_plugins():
        """List all plugins."""
        plugins_dir = str(Path("flaskr") / "plugins")
        plugins = [path.name for path in Path(plugins_dir).iterdir() if path.is_dir()]
        for plugin in plugins:
            if plugin == "__pycache__":
                continue

    def get_plugin_migrations():
        """Get plugin migrations."""
        plugins = []
        app.logger.info(
            f"plugin_manager.plugins: {len(plugin_manager.plugins.values())}"
        )
        for plugin in plugin_manager.plugins.values():
            app.logger.info(
                f"plugin: {plugin.name}, migration_dir: {plugin.migration_dir}"
            )
            if plugin.migration_dir and Path(plugin.migration_dir).exists():
                plugins.append(plugin)
        return plugins

    @plugin.group(name="db")
    def plugin_db():
        """Manage the plugin database."""

    def get_version_table_name(plugin_name: str) -> str:
        """Get version table name."""
        return f"alembic_version_plugin_{plugin_name.replace('-', '_')}"

    def get_alembic_config(plugin, version_table: str | None = None) -> Config:
        """Get alembic config."""
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
        """Generate plugin model filter function."""

        def include_object(object, name, type_, reflected, compare_to):
            if type_ == "table":
                return object.__module__.startswith(f"flaskr.plugins.{plugin_name}")
            return True

        return include_object

    @plugin_db.command(name="upgrade")
    @click.argument("plugin_name", required=False)
    @with_appcontext
    def upgrade(plugin_name):
        """Upgrade the plugin database to the latest version."""
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
        """View the migration history of the plugin."""
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
        """Migrate the plugin database to the latest version."""
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
