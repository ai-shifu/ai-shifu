"""Dashboard routes (teacher-facing analytics)."""

from __future__ import annotations

from flask import Flask, request

from flaskr.framework.plugin.inject import inject
from flaskr.route.common import make_common_response
from flaskr.service.dashboard.funcs import (
    load_published_outlines,
    require_shifu_view_permission,
)


@inject
def register_dashboard_routes(app: Flask, path_prefix: str = "/api/dashboard") -> None:
    """Register dashboard routes."""
    app.logger.info("register dashboard routes %s", path_prefix)

    @app.route(path_prefix + "/shifus/<shifu_bid>/outlines", methods=["GET"])
    def dashboard_outlines_api(shifu_bid: str):
        user_id = request.user.user_id
        require_shifu_view_permission(app, user_id, shifu_bid)
        return make_common_response(load_published_outlines(app, shifu_bid))

    return None
