"""Trusted interactive administrator setup and recovery commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click
from flaskr.service.common.models import AppError

if TYPE_CHECKING:
    from flask import Flask


def register_installation_commands(console: click.Group, app: Flask) -> None:
    """Register local-console capabilities without exposing a recovery API."""

    @console.command("prepare-installation")
    @click.option(
        "--repair-development",
        is_flag=True,
        help="Repair known development migration residue before upgrading.",
    )
    def prepare_installation(repair_development: bool) -> None:
        """Apply migrations while preserving fresh-installation provenance."""
        from flaskr.service.user.installation import prepare_installation_database

        if repair_development:
            from scripts.repair_dev_migration_state import main as repair

            # Keep repair and upgrade in this same cached Flask process. A
            # separate repair process can run plugin migrations before the
            # next process captures its empty-schema provenance.
            if repair() != 0:
                message = "Development migration repair failed."
                raise click.ClickException(message)
        prepare_installation_database(app)
        click.echo("Database migrations completed. Open /admin to continue.")

    @console.command("setup-code")
    @click.option(
        "--origin",
        default="http://localhost:8080",
        show_default=True,
        help="Browser origin: HTTPS, or HTTP on a loopback hostname/address.",
    )
    def setup_code(origin: str) -> None:
        """Display a single-use setup code on demand, outside ordinary logs."""
        from flaskr.service.user.installation import issue_setup_token

        try:
            token = issue_setup_token(app, origin=origin)
        except AppError as error:
            raise click.ClickException(str(error)) from error
        click.echo("One-time administrator setup code (expires in 20 minutes):")
        click.echo(token)
        click.echo(
            "Paste it into /setup on that origin. Reissuing invalidates this code."
        )

    @console.command("create-admin")
    @click.option("--username", prompt="Administrator username")
    def create_admin(username: str) -> None:
        """Create the first local administrator without a browser or mail provider."""
        from flaskr.service.user.installation import create_admin_from_console

        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        try:
            create_admin_from_console(app, username=username, password=password)
        except AppError as error:
            raise click.ClickException(str(error)) from error
        click.echo("Local administrator created. Sign in at /admin-login.")

    @console.command("reset-admin-password")
    @click.option("--username", prompt="Administrator username")
    def reset_admin_password(username: str) -> None:
        """Reset a local administrator password and revoke the old sessions."""
        from flaskr.service.user.local_accounts import reset_local_admin_password

        password = click.prompt(
            "New password", hide_input=True, confirmation_prompt=True
        )
        try:
            reset_local_admin_password(app, username=username, new_password=password)
        except AppError as error:
            raise click.ClickException(str(error)) from error
        click.echo("Administrator password changed; previous sessions were revoked.")
