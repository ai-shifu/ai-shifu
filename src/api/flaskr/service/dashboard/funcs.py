"""Query helpers for the teacher-facing analytics dashboard."""

from __future__ import annotations

from flask import Flask


def dashboard_healthcheck(app: Flask) -> bool:
    """Small helper to verify the dashboard module is loaded."""
    with app.app_context():
        return True
