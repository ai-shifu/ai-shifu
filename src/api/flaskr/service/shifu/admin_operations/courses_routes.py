"""Register operator course-administration routes.

Service calls resolve through the route module so its patch targets stay effective.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import request
from flaskr.common.http import make_common_response
from flaskr.service.common.models import raise_param_error
from flaskr.service.shifu.admin_operations.route_helpers import (
    _normalize_contact_type,
    _normalize_contacts,
    _normalize_query_text,
    _parse_boolean_query_param,
    _parse_datetime_filter,
    _parse_positive_query_int,
    _require_operator,
    _validate_contacts,
    _validate_datetime_range,
)

if TYPE_CHECKING:
    from flask import Flask


def register_admin_operations_course_list_routes(app: Flask, path_prefix: str) -> None:
    """Register the operator course list route."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(path_prefix + "/admin/operations/courses", methods=["GET"])
    def admin_operations_courses() -> str:
        """Operator course list.

        ---
        tags:
            - Course
        parameters:
            - name: page_index
              type: integer
              required: false
              description: Page index, defaults to 1 when omitted
            - name: page_size
              type: integer
              required: false
              description: Page size, defaults to 20 when omitted
            - name: course_query
              type: string
              required: false
              description: Matches course ID exactly or course name fuzzily
            - name: shifu_bid
              type: string
              required: false
              description: Deprecated exact course ID filter
            - name: course_name
              type: string
              required: false
              description: Deprecated fuzzy course name filter
            - name: creator_keyword
              type: string
              required: false
              description: Exact match on user bid, phone, or email
            - name: course_status
              type: string
              required: false
              description: published or unpublished
            - name: start_time
              type: string
              required: false
              description: Course created start date (YYYY-MM-DD)
            - name: end_time
              type: string
              required: false
              description: Course created end date (YYYY-MM-DD)
            - name: updated_start_time
              type: string
              required: false
              description: Course updated start date (YYYY-MM-DD)
            - name: updated_end_time
              type: string
              required: false
              description: Course updated end date (YYYY-MM-DD)
            - name: quick_filter
              type: string
              required: false
              description: draft, published, created_last_7d, learning_active_30d, paid_order_30d
        responses:
            200:
                description: List operator-visible courses
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/AdminOperationCourseListDTO"
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page_index"),
            field_name="page_index",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )

        filters = {
            "course_query": _normalize_query_text(request.args.get("course_query")),
            "shifu_bid": _normalize_query_text(request.args.get("shifu_bid")),
            "course_name": _normalize_query_text(request.args.get("course_name")),
            "course_status": _normalize_query_text(request.args.get("course_status")),
            "quick_filter": _normalize_query_text(request.args.get("quick_filter")),
            "creator_keyword": _normalize_query_text(
                request.args.get("creator_keyword")
            ),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
            "updated_start_time": _parse_datetime_filter(
                request.args.get("updated_start_time", ""),
                field_name="updated_start_time",
                is_end=False,
            ),
            "updated_end_time": _parse_datetime_filter(
                request.args.get("updated_end_time", ""),
                field_name="updated_end_time",
                is_end=True,
            ),
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        _validate_datetime_range(
            filters["updated_start_time"],
            filters["updated_end_time"],
            field_name="updated_start_time",
        )
        return make_common_response(
            ops_route.list_operator_courses(app, page_index, page_size, filters)
        )


def register_admin_operations_course_overview_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register the operator course overview route."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(path_prefix + "/admin/operations/courses/overview", methods=["GET"])
    def admin_operations_course_overview() -> str:
        """Operator course overview.

        ---
        tags:
            - Course
        responses:
            200:
                description: Operator-visible course overview metrics
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/AdminOperationCourseOverviewDTO"
        """
        _require_operator()
        return make_common_response(ops_route.get_operator_course_overview(app))


def register_admin_operations_course_detail_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register operator course prompt, detail, and chapter routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/prompt",
        methods=["GET"],
    )
    def admin_operation_course_prompt(shifu_bid: str) -> str:
        """Get operator course prompt."""
        _require_operator()
        return make_common_response(
            ops_route.get_operator_course_prompt(app, shifu_bid=shifu_bid)
        )

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/detail", methods=["GET"]
    )
    def admin_operation_course_detail(shifu_bid: str) -> str:
        """Get operator course detail.

        ---
        tags:
            - Shifu
        parameters:
            - name: shifu_bid
              in: path
              type: string
              required: true
              description: Course shifu bid
        responses:
            200:
                description: Operator course detail
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/AdminOperationCourseDetailDTO"
        """
        _require_operator()
        return make_common_response(
            ops_route.get_operator_course_detail(
                app,
                shifu_bid=shifu_bid,
            )
        )

    @app.route(
        path_prefix
        + "/admin/operations/courses/<shifu_bid>/chapters/<outline_item_bid>/detail",
        methods=["GET"],
    )
    def admin_operation_course_chapter_detail(
        shifu_bid: str, outline_item_bid: str
    ) -> str:
        """Get operator course chapter detail.

        ---
        tags:
            - Shifu
        parameters:
            - name: shifu_bid
              in: path
              type: string
              required: true
              description: Course shifu bid
            - name: outline_item_bid
              in: path
              type: string
              required: true
              description: Outline item bid
        responses:
            200:
                description: Operator course chapter detail
                content:
                    application/json:
                        schema:
                            properties:
                                code:
                                    type: integer
                                message:
                                    type: string
                                data:
                                    $ref: "#/components/schemas/AdminOperationCourseChapterDetailDTO"
        """
        _require_operator()
        return make_common_response(
            ops_route.get_operator_course_chapter_detail(
                app,
                shifu_bid=shifu_bid,
                outline_item_bid=outline_item_bid,
            )
        )


def register_admin_operations_course_user_routes(app: Flask, path_prefix: str) -> None:
    """Register the operator course learner list route."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/users", methods=["GET"]
    )
    def admin_operation_course_users(shifu_bid: str) -> str:
        """Get operator course users.

        ---
        tags:
            - Shifu
        parameters:
            - name: shifu_bid
              in: path
              type: string
              required: true
              description: Course shifu bid
            - name: page
              in: query
              type: integer
              required: false
              description: Page index
            - name: page_size
              in: query
              type: integer
              required: false
              description: Page size
            - name: keyword
              in: query
              type: string
              required: false
              description: User keyword
            - name: user_role
              in: query
              type: string
              required: false
              description: User role filter
            - name: learning_status
              in: query
              type: string
              required: false
              description: Learning status filter
            - name: payment_status
              in: query
              type: string
              required: false
              description: Payment status filter
        responses:
            200:
                description: Operator course user list
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page"),
            field_name="page",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": request.args.get("keyword", ""),
            "user_role": request.args.get("user_role", ""),
            "learning_status": request.args.get("learning_status", ""),
            "payment_status": request.args.get("payment_status", ""),
        }
        return make_common_response(
            ops_route.get_operator_course_users(
                app,
                shifu_bid=shifu_bid,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )


def register_admin_operations_course_credit_usage_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register operator course credit usage routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/credit-usages",
        methods=["GET"],
    )
    def admin_operation_course_credit_usages(shifu_bid: str) -> str:
        """Get operator course credit usage list.

        ---
        tags:
            - Shifu
        parameters:
            - name: shifu_bid
              in: path
              type: string
              required: true
              description: Course shifu bid
            - name: page
              in: query
              type: integer
              required: false
              description: Page index
            - name: page_size
              in: query
              type: integer
              required: false
              description: Page size
            - name: keyword
              in: query
              type: string
              required: false
              description: User keyword
            - name: mode
              in: query
              type: string
              required: false
              description: Credit usage mode filter
            - name: usage_scene
              in: query
              type: string
              required: false
              description: Credit usage scene filter
            - name: view
              in: query
              type: string
              required: false
              description: Credit usage view mode, grouped or raw
            - name: start_time
              in: query
              type: string
              required: false
              description: Inclusive filter start time
            - name: end_time
              in: query
              type: string
              required: false
              description: Inclusive filter end time
        responses:
            200:
                description: Operator course credit usage list
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page"),
            field_name="page",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": request.args.get("keyword", ""),
            "mode": request.args.get("mode", ""),
            "usage_scene": request.args.get("usage_scene", ""),
            "view": request.args.get("view", ""),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            ops_route.get_operator_course_credit_usages(
                app,
                shifu_bid=shifu_bid,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
            )
        )

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/credit-usages/details",
        methods=["GET"],
    )
    def admin_operation_course_credit_usage_details(shifu_bid: str) -> str:
        """Get operator course credit usage detail list.

        ---
        tags:
            - Shifu
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page"),
            field_name="page",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=10,
        )
        return make_common_response(
            ops_route.get_operator_course_credit_usage_details(
                app,
                shifu_bid=shifu_bid,
                page_index=page_index,
                page_size=page_size,
                filters={
                    "user_bid": request.args.get("user_bid", ""),
                    "outline_item_bid": request.args.get("outline_item_bid", ""),
                    "usage_scene": request.args.get("usage_scene", ""),
                    "mode": request.args.get("mode", ""),
                },
            )
        )


def register_admin_operations_course_rating_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register the operator course rating route."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/ratings",
        methods=["GET"],
    )
    def admin_operation_course_ratings(shifu_bid: str) -> str:
        """Get operator course rating list.

        ---
        tags:
            - Shifu
        parameters:
            - name: shifu_bid
              in: path
              type: string
              required: true
              description: Course shifu bid
            - name: page
              in: query
              type: integer
              required: false
              description: Page index
            - name: page_size
              in: query
              type: integer
              required: false
              description: Page size
            - name: keyword
              in: query
              type: string
              required: false
              description: User keyword
            - name: chapter_keyword
              in: query
              type: string
              required: false
              description: Chapter or lesson keyword
            - name: score
              in: query
              type: string
              required: false
              description: Rating score filter
            - name: mode
              in: query
              type: string
              required: false
              description: Rating mode filter
            - name: has_comment
              in: query
              type: string
              required: false
              description: Whether to only return rows with comments
            - name: sort_by
              in: query
              type: string
              required: false
              description: Rating sort option
            - name: start_time
              in: query
              type: string
              required: false
              description: Inclusive filter start time
            - name: end_time
              in: query
              type: string
              required: false
              description: Inclusive filter end time
            - name: include_summary
              in: query
              type: boolean
              required: false
              description: Whether to include expensive summary metrics. Defaults to true. When false, summary fields are returned as defaults while total and page_count still reflect the filtered result.
        responses:
            200:
                description: Operator course rating list
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page"),
            field_name="page",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": request.args.get("keyword", ""),
            "chapter_keyword": request.args.get("chapter_keyword", ""),
            "score": request.args.get("score", ""),
            "mode": request.args.get("mode", ""),
            "has_comment": request.args.get("has_comment", ""),
            "sort_by": request.args.get("sort_by", ""),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        include_summary = _parse_boolean_query_param(
            request.args.get("include_summary", None),
            field_name="include_summary",
            default=True,
        )
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            ops_route.get_operator_course_ratings(
                app,
                shifu_bid=shifu_bid,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
                include_summary=include_summary,
            )
        )


def register_admin_operations_course_follow_up_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register operator course follow-up routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/follow-ups",
        methods=["GET"],
    )
    def admin_operation_course_follow_ups(shifu_bid: str) -> str:
        """Get operator course follow-up list.

        ---
        tags:
            - Shifu
        parameters:
            - name: shifu_bid
              in: path
              type: string
              required: true
              description: Course shifu bid
            - name: page
              in: query
              type: integer
              required: false
              description: Page index
            - name: page_size
              in: query
              type: integer
              required: false
              description: Page size
            - name: keyword
              in: query
              type: string
              required: false
              description: User keyword
            - name: chapter_keyword
              in: query
              type: string
              required: false
              description: Chapter or lesson keyword
            - name: source_status
              in: query
              type: string
              required: false
              description: Original output source status filter (resolved or missing)
            - name: start_time
              in: query
              type: string
              required: false
              description: Inclusive filter start time
            - name: end_time
              in: query
              type: string
              required: false
              description: Inclusive filter end time
            - name: include_summary
              in: query
              type: boolean
              required: false
              description: Whether to include expensive summary metrics
        responses:
            200:
                description: Operator course follow-up list
        """
        _require_operator()
        page_index = _parse_positive_query_int(
            request.args.get("page"),
            field_name="page",
            default=1,
        )
        page_size = _parse_positive_query_int(
            request.args.get("page_size"),
            field_name="page_size",
            default=20,
        )
        filters = {
            "keyword": request.args.get("keyword", ""),
            "chapter_keyword": request.args.get("chapter_keyword", ""),
            "source_status": request.args.get("source_status", ""),
            "start_time": _parse_datetime_filter(
                request.args.get("start_time", ""),
                field_name="start_time",
                is_end=False,
            ),
            "end_time": _parse_datetime_filter(
                request.args.get("end_time", ""),
                field_name="end_time",
                is_end=True,
            ),
        }
        include_summary = _parse_boolean_query_param(
            request.args.get("include_summary", None),
            field_name="include_summary",
            default=True,
        )
        _validate_datetime_range(
            filters["start_time"],
            filters["end_time"],
            field_name="start_time",
        )
        return make_common_response(
            ops_route.get_operator_course_follow_ups(
                app,
                shifu_bid=shifu_bid,
                page_index=page_index,
                page_size=page_size,
                filters=filters,
                include_summary=include_summary,
            )
        )

    @app.route(
        path_prefix
        + "/admin/operations/courses/<shifu_bid>/follow-ups/<generated_block_bid>/detail",
        methods=["GET"],
    )
    def admin_operation_course_follow_up_detail(
        shifu_bid: str,
        generated_block_bid: str,
    ) -> str:
        """Get operator course follow-up detail.

        ---
        tags:
            - Shifu
        parameters:
            - name: shifu_bid
              in: path
              type: string
              required: true
              description: Course shifu bid
            - name: generated_block_bid
              in: path
              type: string
              required: true
              description: Follow-up generated block bid
        responses:
            200:
                description: Operator course follow-up detail
        """
        _require_operator()
        return make_common_response(
            ops_route.get_operator_course_follow_up_detail(
                app,
                shifu_bid=shifu_bid,
                generated_block_bid=generated_block_bid,
            )
        )


def register_admin_operations_course_ownership_routes(
    app: Flask, path_prefix: str
) -> None:
    """Register operator course copy and creator-transfer routes."""
    from flaskr.service.shifu.admin_operations import route as ops_route

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/copy",
        methods=["POST"],
    )
    def admin_copy_course(shifu_bid: str) -> str:
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("payload")
        contact_type = _normalize_contact_type(payload.get("contact_type", ""))
        allowed_methods = ops_route._get_login_methods_enabled()
        if contact_type not in {"phone", "email"}:
            raise_param_error("contact_type")
        if allowed_methods and contact_type not in allowed_methods:
            raise_param_error("contact_type")

        identifiers = _validate_contacts(
            contact_type,
            _normalize_contacts(payload.get("identifier", "")),
        )
        if len(identifiers) != 1:
            raise_param_error("contact")

        return make_common_response(
            ops_route.copy_operator_course(
                app,
                shifu_bid=shifu_bid,
                contact_type=contact_type,
                identifier=identifiers[0],
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
                new_course_name=str(payload.get("new_course_name", "") or ""),
            )
        )

    @app.route(
        path_prefix + "/admin/operations/courses/<shifu_bid>/transfer-creator",
        methods=["POST"],
    )
    def admin_transfer_course_creator(shifu_bid: str) -> str:
        _require_operator()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("payload")
        contact_type = _normalize_contact_type(payload.get("contact_type", ""))
        allowed_methods = ops_route._get_login_methods_enabled()
        if contact_type not in {"phone", "email"}:
            raise_param_error("contact_type")
        if allowed_methods and contact_type not in allowed_methods:
            raise_param_error("contact_type")

        identifiers = _validate_contacts(
            contact_type,
            _normalize_contacts(payload.get("identifier", "")),
        )
        if len(identifiers) != 1:
            raise_param_error("contact")

        return make_common_response(
            ops_route.transfer_operator_course_creator(
                app,
                shifu_bid=shifu_bid,
                contact_type=contact_type,
                identifier=identifiers[0],
                operator_user_bid=str(getattr(request.user, "user_id", "") or ""),
            )
        )
