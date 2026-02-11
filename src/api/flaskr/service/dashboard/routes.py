"""Dashboard routes (teacher-facing analytics)."""

from __future__ import annotations

from flask import Flask, request

from flaskr.framework.plugin.inject import inject
from flaskr.route.common import make_common_response
from flaskr.service.dashboard.funcs import (
    build_dashboard_entry,
    build_dashboard_learner_detail,
    build_dashboard_overview,
    load_published_outlines,
    list_dashboard_learners,
    list_dashboard_followups,
    require_shifu_view_permission,
)


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

    @app.route(path_prefix + "/shifus/<shifu_bid>/learners", methods=["GET"])
    def dashboard_learners_api(shifu_bid: str):
        user_id = request.user.user_id
        require_shifu_view_permission(app, user_id, shifu_bid)
        page_index_raw = request.args.get("page_index", "1")
        page_size_raw = request.args.get("page_size", "20")
        try:
            page_index = int(page_index_raw)
            page_size = int(page_size_raw)
        except ValueError:
            page_index = 1
            page_size = 20
        return make_common_response(
            list_dashboard_learners(
                app,
                shifu_bid,
                page_index=page_index,
                page_size=page_size,
                keyword=request.args.get("keyword"),
                sort=request.args.get("sort"),
            )
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/learners/<user_bid>", methods=["GET"])
    def dashboard_learner_detail_api(shifu_bid: str, user_bid: str):
        user_id = request.user.user_id
        require_shifu_view_permission(app, user_id, shifu_bid)
        return make_common_response(
            build_dashboard_learner_detail(app, shifu_bid, user_bid)
        )

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/learners/<user_bid>/followups",
        methods=["GET"],
    )
    def dashboard_learner_followups_api(shifu_bid: str, user_bid: str):
        user_id = request.user.user_id
        require_shifu_view_permission(app, user_id, shifu_bid)
        page_index_raw = request.args.get("page_index", "1")
        page_size_raw = request.args.get("page_size", "20")
        try:
            page_index = int(page_index_raw)
            page_size = int(page_size_raw)
        except ValueError:
            page_index = 1
            page_size = 20
        return make_common_response(
            list_dashboard_followups(
                app,
                shifu_bid,
                user_bid,
                outline_item_bid=request.args.get("outline_item_bid"),
                start_time=request.args.get("start_time"),
                end_time=request.args.get("end_time"),
                page_index=page_index,
                page_size=page_size,
            )
        )

    return None
