from flask import Flask
import click
from .import_user import import_user


def enable_commands(app: Flask):
    @app.cli.group()
    def console():
        """AI Shifu Console management commands."""
        pass

    @console.command(name="import_user")
    @click.argument("mobile")
    @click.argument("course_id")
    @click.argument("discount_code")
    @click.argument("user_nick_name")
    def import_user_command(mobile, course_id, discount_code, user_nick_name):
        """Import user and enable course"""
        import_user(app, mobile, course_id, discount_code, user_nick_name)
