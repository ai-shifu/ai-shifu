"""Dashboard routes (teacher-facing analytics)."""

from __future__ import annotations

from flask import Flask, request

from flaskr.framework.plugin.inject import inject
from flaskr.route.common import make_common_response
from flaskr.service.dashboard.funcs import (
    build_dashboard_overview,
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

    @app.route(path_prefix + "/shifus/<shifu_bid>/overview", methods=["GET"])
    def dashboard_overview_api(shifu_bid: str):
        user_id = request.user.user_id
        require_shifu_view_permission(app, user_id, shifu_bid)
        return make_common_response(
            build_dashboard_overview(
                app,
                shifu_bid,
                start_date=request.args.get("start_date"),
                end_date=request.args.get("end_date"),
                include_trial=request.args.get("include_trial") == "true",
                include_guest=request.args.get("include_guest") == "true",
            )
        )

    return None
