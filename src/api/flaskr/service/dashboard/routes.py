"""Dashboard routes (teacher-facing analytics)."""

from __future__ import annotations

from flask import Flask

from flaskr.framework.plugin.inject import inject


@inject
def register_dashboard_routes(app: Flask, path_prefix: str = "/api/dashboard") -> None:
    """Register dashboard routes."""
    app.logger.info("register dashboard routes %s", path_prefix)
    # Endpoints will be added incrementally for v1.
    return None
