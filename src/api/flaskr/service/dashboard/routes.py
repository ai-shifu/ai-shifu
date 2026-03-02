"""Dashboard routes (teacher-facing analytics)."""

from __future__ import annotations

from flask import Flask, request

from flaskr.framework.plugin.inject import inject
from flaskr.route.common import make_common_response
from flaskr.service.dashboard.funcs import build_dashboard_entry


@inject
def register_dashboard_routes(app: Flask, path_prefix: str = "/api/dashboard") -> None:
    """Register dashboard routes."""
    app.logger.info("register dashboard routes %s", path_prefix)

    @app.route(path_prefix + "/entry", methods=["GET"])
    def dashboard_entry_api():
        user_id = request.user.user_id
        page_index_raw = request.args.get("page_index", "1")
        page_size_raw = request.args.get("page_size", "20")
        try:
            page_index = int(page_index_raw)
            page_size = int(page_size_raw)
        except ValueError:
            page_index = 1
            page_size = 20
        return make_common_response(
            build_dashboard_entry(
                app,
                user_id,
                start_date=request.args.get("start_date"),
                end_date=request.args.get("end_date"),
                keyword=request.args.get("keyword"),
                page_index=page_index,
                page_size=page_size,
            )
        )

    return None
