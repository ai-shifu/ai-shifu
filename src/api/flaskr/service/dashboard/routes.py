"""Dashboard routes (teacher-facing analytics)."""

from __future__ import annotations

from flask import Flask, request

from flaskr.framework.plugin.inject import inject
from flaskr.route.common import make_common_response
from flaskr.service.common.models import raise_param_error
from flaskr.service.dashboard.funcs import (
    build_dashboard_course_follow_up_detail,
    build_dashboard_course_follow_ups,
    build_dashboard_course_detail,
    build_dashboard_course_learners,
    build_dashboard_course_ratings,
    build_dashboard_entry,
)


def _get_timezone_name() -> str | None:
    timezone_name = (request.args.get("timezone", "") or "").strip()
    if timezone_name and len(timezone_name) > 100:
        raise_param_error("timezone")
    return timezone_name or None


def _get_pagination_args() -> tuple[int, int]:
    page_index_raw = request.args.get("page_index", "1")
    page_size_raw = request.args.get("page_size", "20")
    try:
        page_index = int(page_index_raw)
    except ValueError:
        raise_param_error("page_index")
    try:
        page_size = int(page_size_raw)
    except ValueError:
        raise_param_error("page_size")
    return page_index, page_size


@inject
def register_dashboard_routes(app: Flask, path_prefix: str = "/api/dashboard") -> None:
    """Register dashboard routes."""
    app.logger.info("register dashboard routes %s", path_prefix)

    @app.route(path_prefix + "/entry", methods=["GET"])
    def dashboard_entry_api():
        user_id = request.user.user_id
        page_index, page_size = _get_pagination_args()
        timezone_name = _get_timezone_name()
        return make_common_response(
            build_dashboard_entry(
                app,
                user_id,
                start_date=request.args.get("start_date"),
                end_date=request.args.get("end_date"),
                keyword=request.args.get("keyword"),
                page_index=page_index,
                page_size=page_size,
                timezone_name=timezone_name,
            )
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/detail", methods=["GET"])
    def dashboard_course_detail_api(shifu_bid: str):
        user_id = request.user.user_id
        return make_common_response(
            build_dashboard_course_detail(
                app,
                user_id,
                shifu_bid,
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/learners", methods=["GET"])
    def dashboard_course_learners_api(shifu_bid: str):
        user_id = request.user.user_id
        page_index, page_size = _get_pagination_args()
        return make_common_response(
            build_dashboard_course_learners(
                app,
                user_id,
                shifu_bid,
                page_index=page_index,
                page_size=page_size,
                keyword=request.args.get("keyword"),
                learning_status=request.args.get("learning_status"),
                last_learning_start_time=request.args.get("last_learning_start_time"),
                last_learning_end_time=request.args.get("last_learning_end_time"),
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/follow-ups", methods=["GET"])
    def dashboard_course_follow_ups_api(shifu_bid: str):
        user_id = request.user.user_id
        page_index, page_size = _get_pagination_args()
        return make_common_response(
            build_dashboard_course_follow_ups(
                app,
                user_id,
                shifu_bid,
                page_index=page_index,
                page_size=page_size,
                keyword=request.args.get("keyword"),
                user_bid=request.args.get("user_bid"),
                chapter_keyword=request.args.get("chapter_keyword"),
                start_time=request.args.get("start_time"),
                end_time=request.args.get("end_time"),
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(path_prefix + "/shifus/<shifu_bid>/ratings", methods=["GET"])
    def dashboard_course_ratings_api(shifu_bid: str):
        user_id = request.user.user_id
        page_index, page_size = _get_pagination_args()
        return make_common_response(
            build_dashboard_course_ratings(
                app,
                user_id,
                shifu_bid,
                page_index=page_index,
                page_size=page_size,
                keyword=request.args.get("keyword"),
                chapter_keyword=request.args.get("chapter_keyword"),
                score=request.args.get("score"),
                has_comment=request.args.get("has_comment"),
                start_time=request.args.get("start_time"),
                end_time=request.args.get("end_time"),
                timezone_name=_get_timezone_name(),
            )
        )

    @app.route(
        path_prefix + "/shifus/<shifu_bid>/follow-ups/<generated_block_bid>/detail",
        methods=["GET"],
    )
    def dashboard_course_follow_up_detail_api(
        shifu_bid: str,
        generated_block_bid: str,
    ):
        user_id = request.user.user_id
        return make_common_response(
            build_dashboard_course_follow_up_detail(
                app,
                user_id,
                shifu_bid,
                generated_block_bid,
                timezone_name=_get_timezone_name(),
            )
        )

    return None
